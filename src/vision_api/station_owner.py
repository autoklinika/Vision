"""Trusted station composition, independent of browser and HTTP lifetimes.

No Core is constructed here. A real runtime owner may bind its existing engine
and clear that binding when the inspection ends. A retired engine is never
closed by this adapter; its owner must manage its lifetime outside engine locks.
"""
from dataclasses import dataclass
import threading
import time
from uuid import uuid4

from .access import Credentials, CursorRejected, LibraryReadGrant, ReadGrant
from .library_reports import LibraryReadService, LibraryReportProvider
from .reports import CoreReportProvider, SessionReadService, _timestamp


class NoActiveSession(Exception):
    """There is no trusted Core owner bound to this station reader."""


@dataclass(frozen=True)
class _Binding:
    provider: CoreReportProvider
    service: SessionReadService


class StationOwner:
    """Backend-only lifecycle. None of the binding methods is an HTTP route.

    Its delegated readers are backend-internal: the HTTP composition must
    authenticate a reader before calling them. They are not public authorizers.
    The short registry lock is never held while taking an engine lock. Reads
    retain the exact binding and recheck it before publishing; a concurrent
    cutover rejects that response instead of mixing two inspection sessions.
    """

    def __init__(self, library, *, station_id="VENTUNO", library_id="vision-ecu-library"):
        if station_id != "VENTUNO" or library_id != "vision-ecu-library":
            raise ValueError("unsupported station identity")
        self.station_id = station_id
        self.library_id = library_id
        self.instance_id = uuid4().hex
        self._lock = threading.Lock()
        self._binding = None
        self._library = library  # Strong ownership for the service lifetime.
        provider = LibraryReportProvider(library, library_id=library_id, source="STATION")
        self.library_reader = LibraryReadService(
            provider=provider,
            authorizer=lambda _credentials: LibraryReadGrant(library_id, frozenset({"library:read"})),
        )

    def bind_core(self, existing_engine):
        """Called by the trusted runtime composition, never by the WebGUI.

        This reads engine identity only: no construction, journal replay,
        state transition, initialization or hardware command.
        """
        provider = CoreReportProvider(existing_engine, source="STATION")
        binding = _Binding(provider, SessionReadService(
            provider=provider,
            authorizer=lambda _credentials: ReadGrant(provider.session_id, frozenset({"session:read", "events:read"})),
        ))
        with self._lock:
            self._binding = binding
        return provider.view_id

    def clear_core(self, expected_view_id):
        """An old runtime's cleanup cannot detach a newer runtime binding."""
        with self._lock:
            if self._binding is None or self._binding.provider.view_id != expected_view_id:
                return False
            self._binding = None
            return True

    def station_report(self):
        with self._lock:
            provider = self._binding.provider if self._binding else None
            return {
                "schema": "vision.api.station.v1", "source": "STATION",
                "instanceId": self.instance_id, "stationId": self.station_id,
                "capturedAt": _timestamp(time.time()), "libraryId": self.library_id,
                "state": "SESSION_ACTIVE" if provider else "NO_ACTIVE_SESSION",
                "coreConnection": "CONNECTED" if provider else "NOT_CONNECTED",
                "coreReadiness": "UNKNOWN",
                "sessionId": provider.session_id if provider else None,
                "sessionViewId": provider.view_id if provider else None,
            }

    def _read_current(self, operation):
        with self._lock:
            binding = self._binding
        if binding is None:
            raise NoActiveSession()
        try:
            result = operation(binding.service)
        finally:
            with self._lock:
                if binding is not self._binding:
                    raise CursorRejected() from None
        return result

    def session_report(self):
        return self._read_current(lambda reader: reader.session_report(Credentials()))

    def events_report(self, *, view, after, through):
        return self._read_current(lambda reader: reader.events_report(
            Credentials(), view=view, after=after, through=through))
