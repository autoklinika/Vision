"""Read-only proxy: no local fallback owner, Workflow, journal or ECU store."""
import socket
import time
from uuid import uuid4

from vision_api.access import CursorRejected, ReportUnavailable
from vision_api.library_reports import (validate_library_report, validate_library_entry_report,
                                        validate_library_history_report)
from vision_api.reports import _timestamp, validate_session_report, validate_events_report
from vision_api.station_owner import NoActiveSession
from .protocol import (ERRORS, EXCHANGE_TIMEOUT, PROTOCOL, REQUEST_LIMIT, RESPONSE_LIMIT,
                       check_peer, checked_path, checked_socket, receive, send,
                       validate_station_report)


class _LibraryProxy:
    def __init__(self, owner):
        self._owner = owner

    def library_report(self, _credentials, *, view=None, after=0):
        query = {} if view is None and after == 0 else {"view": view, "after": after}
        report = self._owner._read("library", query, validate_library_report)
        if report["after"] != after or (view is not None and report["viewId"] != view):
            raise ReportUnavailable()
        return report

    def entry_report(self, _credentials, *, entry_id, view):
        report = self._owner._read("entry", {"entry_id": entry_id, "view": view},
                                  validate_library_entry_report)
        if report["viewId"] != view or report["entry"]["entryId"] != entry_id:
            raise ReportUnavailable()
        return report

    def history_report(self, _credentials, *, entry_id, view, after=0):
        report = self._owner._read("history", {"entry_id": entry_id, "view": view, "after": after},
                                  validate_library_history_report)
        if report["viewId"] != view or report["entryId"] != entry_id or report["after"] != after:
            raise ReportUnavailable()
        return report


class RemoteStationOwner:
    """Authentication belongs to the HTTP composition before these reads.

    The socket is an independently permissioned backend boundary. User cookies
    are never forwarded. An outage returns only a truthful disconnected
    station summary; all protected Core/library data then becomes unavailable.
    """

    def __init__(self, socket_path):
        self._socket_path = socket_path
        self._outage_instance = uuid4().hex
        self.library_reader = _LibraryProxy(self)

    def _read(self, operation, query, validator):
        try:
            path = checked_path(self._socket_path)
            checked_socket(path)
            deadline = time.monotonic() + EXCHANGE_TIMEOUT
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(EXCHANGE_TIMEOUT)
                connection.connect(str(path))
                check_peer(connection)
                send(connection, {"schema": PROTOCOL, "operation": operation, "query": query},
                     limit=REQUEST_LIMIT, deadline=deadline)
                response = receive(connection, limit=RESPONSE_LIMIT, deadline=deadline)
            if type(response) is not dict or response.get("schema") != PROTOCOL:
                raise ValueError("invalid station envelope")
            if set(response) == {"schema", "error"}:
                code = response["error"]
                if not isinstance(code, str) or code not in ERRORS:
                    raise ValueError("invalid station error")
                if code == "NO_ACTIVE_SESSION":
                    raise NoActiveSession()
                if code == "CURSOR_REJECTED":
                    raise CursorRejected()
                raise ReportUnavailable()
            if set(response) != {"schema", "report"} or not validator(response["report"]):
                raise ValueError("invalid station report")
            report = response["report"]
            if report.get("source") != "STATION":
                raise ValueError("station source required")
            if operation in ("library", "entry", "history") and report["libraryId"] != "vision-ecu-library":
                raise ValueError("station library identity mismatch")
            return report
        except (NoActiveSession, CursorRejected, ReportUnavailable):
            raise
        except Exception:
            raise ReportUnavailable() from None

    def station_report(self):
        try:
            report = self._read("station", {}, validate_station_report)
            if report["coreConnection"] != "CONNECTED":
                raise ReportUnavailable()
            return report
        except (ReportUnavailable, NoActiveSession, CursorRejected):
            return {"schema": "vision.api.station.v1", "source": "STATION",
                    "instanceId": self._outage_instance, "stationId": "VENTUNO",
                    "capturedAt": _timestamp(time.time()), "libraryId": "vision-ecu-library",
                    "state": "NO_ACTIVE_SESSION", "coreConnection": "NOT_CONNECTED",
                    "coreReadiness": "UNKNOWN", "sessionId": None, "sessionViewId": None}

    def session_report(self):
        return self._read("session", {}, validate_session_report)

    def events_report(self, *, view, after, through):
        report = self._read("events", {"view": view, "after": after, "through": through},
                            validate_events_report)
        if (report["viewId"] != view or report["afterSequence"] != after
                or report["throughSequence"] != through):
            raise ReportUnavailable()
        return report
