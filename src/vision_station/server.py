"""Bounded private station server for one independently owned station backend."""
import fcntl
import json
import os
import socketserver
import stat
import threading
import time

from vision_api.access import Credentials, CursorRejected, ReportUnavailable
from vision_api.station_owner import NoActiveSession
from .inspection import InspectionRejected
from .luxonis_ir import IRRejected, validate_request
from .draft_editor import DraftConflict, DraftNotFound, EDITOR_WIRE_LIMIT, ASSET_WIRE_LIMIT
from .protocol import (EXCHANGE_TIMEOUT, PROTOCOL, REQUEST_LIMIT, RESPONSE_LIMIT, LEGACY_REQUEST_LIMIT,
                       check_peer, checked_path, checked_socket, exchange_timeout, receive, send)


def dispatch(host, request):
    if (type(request) is not dict or set(request) != {"schema", "operation", "query"}
            or request["schema"] != PROTOCOL or type(request["query"]) is not dict):
        raise ValueError("invalid station request")
    operation, query = request["operation"], request["query"]
    if operation == "draft_editor" and set(query) == {"action", "args"}:
        limit=ASSET_WIRE_LIMIT if query["action"]=="asset_import" else EDITOR_WIRE_LIMIT
        if len(json.dumps(request,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode("ascii"))>limit:
            raise ValueError("editor request too large")
        return host.draft_editor(query["action"], query["args"])
    if len(json.dumps(request, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii")) > LEGACY_REQUEST_LIMIT:
        raise ValueError("legacy request too large")
    if operation == "station" and not query:
        return host.station_report()
    if operation == "luxonis" and not query:
        return host.luxonis_report()
    if operation == "luxonis_ir" and validate_request(query):
        return host.luxonis_ir(**query)
    if operation == "luxonis_preview" and not query:
        return host.luxonis_report(preview=True)
    if operation == "inspection" and not query:
        return host.inspection_report()
    if operation == "inspection_start" and set(query) == {"selection_id", "instance_id", "intent_token", "operator"}:
        return host.start_inspection(**query)
    if operation == "inspection_close" and set(query) == {"session_id", "instance_id", "operator"}:
        return host.close_inspection(**query)
    if operation == "session" and not query:
        return host.session_report()
    if operation == "events" and set(query) == {"view", "after", "through"}:
        return host.events_report(**query)
    if operation == "library" and set(query) in (set(), {"view", "after"}):
        return host.library_reader.library_report(Credentials(), **query)
    if operation == "entry" and set(query) == {"entry_id", "view"}:
        return host.library_reader.entry_report(Credentials(), **query)
    if operation == "history" and set(query) == {"entry_id", "view", "after"}:
        return host.library_reader.history_report(Credentials(), **query)
    raise ValueError("unknown station operation")


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        started = time.monotonic()
        deadline = started + EXCHANGE_TIMEOUT
        response_limit=RESPONSE_LIMIT
        try:
            check_peer(self.request)
            request = receive(self.request, limit=REQUEST_LIMIT, deadline=deadline)
            if type(request) is dict:
                deadline = started + exchange_timeout(request.get("operation"))
            report = dispatch(self.server.host, request)
            if request["operation"]=="draft_editor" and request["query"]["action"]=="asset_preview":
                response_limit=ASSET_WIRE_LIMIT
            response = {"schema": PROTOCOL, "report": report}
        except DraftConflict:
            response = {"schema": PROTOCOL, "error": "DRAFT_CONFLICT"}
        except DraftNotFound:
            response = {"schema": PROTOCOL, "error": "DRAFT_NOT_FOUND"}
        except IRRejected:
            response = {"schema": PROTOCOL, "error": "IR_REJECTED"}
        except InspectionRejected:
            response = {"schema": PROTOCOL, "error": "INSPECTION_REJECTED"}
        except NoActiveSession:
            response = {"schema": PROTOCOL, "error": "NO_ACTIVE_SESSION"}
        except CursorRejected:
            response = {"schema": PROTOCOL, "error": "CURSOR_REJECTED"}
        except ReportUnavailable:
            response = {"schema": PROTOCOL, "error": "REPORT_UNAVAILABLE"}
        except (ValueError, TypeError, UnicodeError, RecursionError):
            response = {"schema": PROTOCOL, "error": "BAD_REQUEST"}
        except Exception:
            response = {"schema": PROTOCOL, "error": "REPORT_UNAVAILABLE"}
        try:
            send(self.request, response, limit=response_limit, deadline=deadline)
        except Exception:
            pass  # No raw payload, path, credential or traceback is logged.


class CoreServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """At most four workers, one frame per connection, fixed reads and inspection lifecycle operations."""

    request_queue_size = 8
    daemon_threads = False
    block_on_close = True

    def __init__(self, socket_path, host=None, *, host_factory=None):
        if (host is None) == (host_factory is None) or (host_factory is not None and not callable(host_factory)):
            raise ValueError("provide one station owner or owner factory")
        self.host = host
        self._slots = threading.BoundedSemaphore(4)
        self._lock_fd = None
        self._inode = None
        self._path = checked_path(socket_path, create_parent=True)
        lock_path = self._path.with_name(self._path.name + ".lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        self._lock_fd = fd
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValueError("invalid station owner lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Production creates the data/runtime owner only after obtaining
            # singleton authority. A duplicate process cannot initialize a
            # second library owner before its rejection.
            if host_factory is not None:
                self.host = host_factory()
            if self._path.exists():
                checked_socket(self._path)
                self._path.unlink()
            super().__init__(str(self._path), _Handler, bind_and_activate=False)
            self.server_bind()
            info = self._path.lstat()
            self._inode = (info.st_dev, info.st_ino)
            os.chmod(self._path, 0o600)
            checked_socket(self._path)
            self.server_activate()
        except BaseException:
            if hasattr(self, "socket"):
                self.server_close()
            elif self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            raise

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        pass  # Deliberately omit request data and implementation exceptions.

    def server_close(self):
        super().server_close()
        if self.host is not None and hasattr(self.host, "shutdown_inspection") and self._inode is not None:
            self.host.shutdown_inspection()
        if self._inode is not None:
            try:
                info = self._path.lstat()
                if (info.st_dev, info.st_ino) == self._inode:
                    self._path.unlink()
            except FileNotFoundError:
                pass
            self._inode = None
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
