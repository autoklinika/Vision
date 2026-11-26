"""Backend ownership outside the WebGUI/API process, including the idle state."""
import threading

from vision_api.access import ReportUnavailable
from vision_api.station_owner import StationOwner
from vision_modules.ecu_library_backend import ECULibraryService
from vision_runtime import VisionRuntimeCoordinator
from .inspection import InspectionOwner, InspectionRejected
from .draft_editor import DraftEditor, DraftConflict, EDITOR_LOCK_TIMEOUT
from .luxonis import LuxonisMonitor
from .nero import NeroMonitor
from .nero_diagnostics import projection
from .nero_history import FaultHistory, HistorySampler
from .nero_clear import result as clear_result, validate_result as validate_clear_result
from .nero_clear_coordinator import eligible as nero_eligible, envelope as nero_clear_envelope, valid_actor, valid_intent
from .luxonis_ir import IRRejected, controllable, validate_request


class CoreHost:
    """Own station data and retain an optional actual inspection coordinator.

    An idle station is a real backend state, not a synthetic inspection. No
    Workflow, Journal, profile approval, evidence or hardware operation is
    created at startup. A trusted backend composition can attach an already
    constructed coordinator once its real declaration and inputs exist.
    Neither attachment nor cleanup is exposed by the private read protocol.
    """

    def __init__(self, library_root, *, composition=None, session_root=None, diagnostics=None, catalog_dir=None, review_authority=None, composition_factory=None, luxonis_directory=None, luxonis_ir=None, luxonis_ir_interlock=None, nero_directory=None, nero_history_directory=None, nero_clear_transport=None, nero_clear_interlock=None):
        self.library = ECULibraryService(library_root, catalog_dir=catalog_dir)
        if review_authority is not None:
            from .reference_review import ReviewAuthority
            if not isinstance(review_authority,ReviewAuthority):
                raise ValueError("explicit review authority required")
        self._review_authority = review_authority
        if composition_factory is not None:
            if composition is not None or not callable(composition_factory):
                raise ValueError("one explicit composition source required")
            composition=composition_factory(self.library)
        self._reader = StationOwner(self.library)
        self.library_reader = self._reader.library_reader
        self._lifecycle_lock = threading.RLock()
        self._runtime = None
        self._view_id = None
        self._draft_editor = DraftEditor(self)
        self._luxonis = LuxonisMonitor(luxonis_directory)
        self._nero = NeroMonitor(nero_directory)
        self._luxonis_ir = luxonis_ir
        self._luxonis_ir_interlock = luxonis_ir_interlock
        self._inspection = InspectionOwner(self, composition=composition, session_root=session_root, diagnostics=diagnostics)
        self._nero_history = None
        self._nero_clear_transport = nero_clear_transport
        self._nero_clear_interlock = nero_clear_interlock
        if nero_clear_transport is not None and (nero_history_directory is None or nero_clear_interlock is None):
            raise ValueError("NERO clear requires durable history and separate idle interlock")
        if nero_history_directory is not None:
            if nero_directory is None:
                raise ValueError("NERO history requires its observer")
            self._nero_history = HistorySampler(FaultHistory(nero_history_directory),
                self._nero, lambda: self.station_report()["instanceId"])

    def close_nero_history(self):
        if self._nero_history is not None:
            sampler, self._nero_history = self._nero_history, None
            sampler.close()

    def nero_diagnostics_report(self):
        r=self.nero_report()
        history=self._nero_history is not None and self._nero_history.available
        return projection(r,history_available=history,
            clear_available=bool(history and self._nero_clear_transport is not None
                                 and self.station_report()["state"]=="NO_ACTIVE_SESSION" and nero_eligible(r)))

    def nero_history_report(self, source="ALL", status="ALL", before=0):
        if self._nero_history is None:
            raise ReportUnavailable()
        return self._nero_history.history.page(self.station_report()["instanceId"],source,status,before)


    def nero_clear_history_report(self, source="ALL", before=0):
        if self._nero_history is None:
            raise ReportUnavailable()
        return self._nero_history.history.attempts(self.station_report()["instanceId"],source,before)

    def clear_nero(self, *, operator, **intent):
        import time
        if not valid_intent(intent) or not valid_actor(operator):
            raise ValueError("invalid NERO clear request")
        instance,operation,scope=(intent[k] for k in ("instanceId","operationId","scope"))
        def reply(status,reason,**kwargs):
            return nero_clear_envelope(instance,clear_result(operation,scope,status,reason,**kwargs))
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            return reply("REJECTED","BUSY")
        try:
            if self.station_report()["instanceId"]!=instance:
                return reply("REJECTED","INTERLOCK")
            if self._nero_history is None or not self._nero_history.available:
                return reply("REJECTED","HISTORY_UNAVAILABLE")
            history=self._nero_history.history
            # Refresh observed episodes before reserving and linking the attempt.
            r=self.nero_report()
            history.observe(r)
            prior=history.begin_clear(operation,scope,operator,time.time())
            if prior is not None:
                return nero_clear_envelope(instance,prior)
            def rejected(reason):
                return clear_result(operation,scope,"REJECTED",reason)
            v=rejected("NOT_COMMISSIONED")
            if self._nero_clear_transport is not None:
                v=rejected("INTERLOCK")
                if (self.station_report()["state"]=="NO_ACTIVE_SESSION"
                        and not self._inspection._poisoned and not self._inspection._marker_exists()
                        and nero_eligible(r)):
                    try:
                        other=self._nero_clear_interlock()
                    except Exception:
                        other={}
                    if other.get("coreConnection")=="CONNECTED" and other.get("state")=="NO_ACTIVE_SESSION":
                        try:
                            v=self._nero_clear_transport.change(operation,scope)
                            if not validate_clear_result(v) or v["operationId"]!=operation or v["scope"]!=scope:
                                raise ValueError("invalid driver response")
                        except Exception:
                            v=clear_result(operation,scope,"UNVERIFIED","TRANSPORT_UNAVAILABLE",invoked=None)
            history.finish_clear(operation,v,time.time())
            return nero_clear_envelope(instance,v)
        finally:
            self._lifecycle_lock.release()

    def attach_runtime(self, runtime):
        if not isinstance(runtime, VisionRuntimeCoordinator):
            raise ValueError("an existing Vision Runtime coordinator is required")
        with self._lifecycle_lock:
            if self._inspection.owned_id is not None:
                raise ValueError("owned inspection cannot be replaced")
            view_id = self._reader.bind_core(runtime.engine)
            self._runtime, self._view_id = runtime, view_id
            return view_id

    def clear_runtime(self, expected_view_id):
        """Retired cleanup cannot detach a newer inspection.

        Read bindings keep their engine alive and reject a concurrent cutover.
        The actual runtime composition closes its retired journal only after
        completing its own work; this read adapter never closes an engine.
        """
        with self._lifecycle_lock:
            if self._view_id != expected_view_id or self._runtime is None:
                return False
            if not self._reader.clear_core(expected_view_id):
                return False
            self._runtime, self._view_id = None, None
            return True

    def station_report(self):
        report = self._reader.station_report()
        # This is emitted by the live independent Core process. The API proxy
        # trusts it only after a successful, validated same-UID socket exchange.
        # Connection is independent of whether a specimen inspection exists.
        report["coreConnection"] = "CONNECTED"
        return report

    def nero_report(self):
        return self._nero.report(self.station_report()["instanceId"])

    def luxonis_report(self, *, preview=False):
        station=self.station_report()
        report=self._luxonis.report(station["instanceId"],preview=preview,
            idle=station["state"]=="NO_ACTIVE_SESSION")
        if self._luxonis_ir is not None:
            report["irControlAvailable"]=controllable(report)
        return report

    def luxonis_ir(self, **intent):
        if not validate_request(intent):
            raise ValueError("invalid IR command")
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            raise IRRejected()
        try:
            r=self.luxonis_report()
            if (self._luxonis_ir is None or r["instanceId"]!=intent["instanceId"]
                    or not controllable(r) or self._inspection._poisoned
                    or self._inspection._marker_exists()):
                raise IRRejected()
            # DEV does not own PROD sessions. A separately configured,
            # read-only production interlock must also report idle.
            if self._luxonis_ir_interlock is not None:
                other=self._luxonis_ir_interlock()
                if other["coreConnection"]!="CONNECTED" or other["state"]!="NO_ACTIVE_SESSION":
                    raise IRRejected()
            return self._luxonis_ir.change(intent["instanceId"],intent["channel"],intent["enabled"])
        finally:
            self._lifecycle_lock.release()

    def session_report(self):
        return self._reader.session_report()

    def events_report(self, *, view, after, through):
        return self._reader.events_report(view=view, after=after, through=through)

    # Do not queue operational requests behind a long library/editor operation.
    # The bound applies only to admission, never to execution already admitted.
    def inspection_report(self):
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            raise ReportUnavailable()
        try:
            return self._inspection.report()
        finally:
            self._lifecycle_lock.release()

    def start_inspection(self, **intent):
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            raise InspectionRejected()
        try:
            return self._inspection.start(**intent)
        finally:
            self._lifecycle_lock.release()

    def close_inspection(self, **intent):
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            raise InspectionRejected()
        try:
            return self._inspection.close(**intent)
        finally:
            self._lifecycle_lock.release()

    def shutdown_inspection(self):
        with self._lifecycle_lock:
            self._inspection.shutdown()

    def draft_editor(self, action, args):
        # Reject contention before dispatch; never queue a mutation for later
        # execution after its caller has already lost the response deadline.
        if not self._lifecycle_lock.acquire(timeout=EDITOR_LOCK_TIMEOUT):
            raise DraftConflict()
        try:
            return self._draft_editor.dispatch(action, args)
        finally:
            self._lifecycle_lock.release()
