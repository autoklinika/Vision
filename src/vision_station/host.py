"""Backend ownership outside the WebGUI/API process, including the idle state."""
import threading

from vision_api.station_owner import StationOwner
from vision_modules.ecu_library_backend import ECULibraryService
from vision_runtime import VisionRuntimeCoordinator


class CoreHost:
    """Own station data and retain an optional actual inspection coordinator.

    An idle station is a real backend state, not a synthetic inspection. No
    Workflow, Journal, profile approval, evidence or hardware operation is
    created at startup. A trusted backend composition can attach an already
    constructed coordinator once its real declaration and inputs exist.
    Neither attachment nor cleanup is exposed by the private read protocol.
    """

    def __init__(self, library_root):
        self.library = ECULibraryService(library_root)
        self._reader = StationOwner(self.library)
        self.library_reader = self._reader.library_reader
        self._lifecycle_lock = threading.Lock()
        self._runtime = None
        self._view_id = None

    def attach_runtime(self, runtime):
        if not isinstance(runtime, VisionRuntimeCoordinator):
            raise ValueError("an existing Vision Runtime coordinator is required")
        with self._lifecycle_lock:
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

    def session_report(self):
        return self._reader.session_report()

    def events_report(self, *, view, after, through):
        return self._reader.events_report(view=view, after=after, through=through)
