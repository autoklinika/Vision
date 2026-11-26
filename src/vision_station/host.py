"""Backend ownership outside the WebGUI/API process, including the idle state."""
import threading

from vision_api.access import ReportUnavailable
from vision_api.station_owner import StationOwner
from vision_modules.ecu_library_backend import ECULibraryService
from vision_runtime import VisionRuntimeCoordinator
from .inspection import InspectionOwner, InspectionRejected
from .draft_editor import DraftEditor, DraftConflict, EDITOR_LOCK_TIMEOUT
from .luxonis import LuxonisMonitor


class CoreHost:
    """Own station data and retain an optional actual inspection coordinator.

    An idle station is a real backend state, not a synthetic inspection. No
    Workflow, Journal, profile approval, evidence or hardware operation is
    created at startup. A trusted backend composition can attach an already
    constructed coordinator once its real declaration and inputs exist.
    Neither attachment nor cleanup is exposed by the private read protocol.
    """

    def __init__(self, library_root, *, composition=None, session_root=None, diagnostics=None, catalog_dir=None, review_authority=None, composition_factory=None, luxonis_directory=None):
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
        self._inspection = InspectionOwner(self, composition=composition, session_root=session_root, diagnostics=diagnostics)

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

    def luxonis_report(self, *, preview=False):
        station=self.station_report()
        return self._luxonis.report(station["instanceId"],preview=preview,
            idle=station["state"]=="NO_ACTIVE_SESSION")

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
