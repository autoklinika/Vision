"""Closed JSON framing for same-user station operations; no executable payloads."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import time

from vision_api.reports import MAX_PROTECTED_BYTES, _utc

LEGACY_REQUEST_LIMIT = 8192
REQUEST_LIMIT = 3 * 1024 * 1024
RESPONSE_LIMIT = MAX_PROTECTED_BYTES + 256
EXCHANGE_TIMEOUT = 2.0
LIBRARY_EXCHANGE_TIMEOUT = 10.0
EDITOR_EXCHANGE_TIMEOUT = 30.0


def exchange_timeout(operation):
    # Complete, bounded history verification is disk work. It gets its own
    # response deadline; request reception and operational exchanges stay short.
    if operation == "draft_editor":
        return EDITOR_EXCHANGE_TIMEOUT
    if operation in ("library", "entry", "history"):
        return LIBRARY_EXCHANGE_TIMEOUT
    return EXCHANGE_TIMEOUT

PROTOCOL = "vision.station.ipc.v1"
ERRORS = frozenset({"NO_ACTIVE_SESSION", "CURSOR_REJECTED", "REPORT_UNAVAILABLE", "BAD_REQUEST", "INSPECTION_REJECTED", "DRAFT_CONFLICT", "DRAFT_NOT_FOUND"})
FIELDS = {"schema", "source", "instanceId", "stationId", "capturedAt", "libraryId",
          "state", "coreConnection", "coreReadiness", "sessionId", "sessionViewId"}


def validate_station_report(value):
    if (type(value) is not dict or set(value) != FIELDS
            or value["schema"] != "vision.api.station.v1" or value["source"] != "STATION"
            or value["stationId"] != "VENTUNO" or value["libraryId"] != "vision-ecu-library"
            or not isinstance(value["instanceId"], str)
            or re.fullmatch(r"[0-9a-f]{32}", value["instanceId"]) is None
            or not _utc(value["capturedAt"]) or value["coreReadiness"] != "UNKNOWN"
            or value["coreConnection"] not in ("CONNECTED", "NOT_CONNECTED")):
        return False
    if value["state"] == "NO_ACTIVE_SESSION":
        return value["sessionId"] is None and value["sessionViewId"] is None
    return (value["state"] == "SESSION_ACTIVE" and value["coreConnection"] == "CONNECTED"
            and isinstance(value["sessionId"], str)
            and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value["sessionId"]) is not None
            and isinstance(value["sessionViewId"], str)
            and re.fullmatch(r"[0-9a-f]{32}", value["sessionViewId"]) is not None)


def checked_path(value, *, create_parent=False):
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or not path.name
            or len(os.fsencode(path)) > 100
            or any(part.is_symlink() for part in (path, *path.parents))):
        raise ValueError("unsafe private socket path")
    if create_parent:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.parent.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("socket directory must be private and owned by the service user")
    return path


def checked_socket(path):
    info = path.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError("invalid private socket")
    return info


def check_peer(connection):
    # Deployment targets Linux. Filesystem permissions and both peer checks are
    # independent; no request field can nominate a trusted user.
    _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    if uid != os.getuid():
        raise ValueError("untrusted station peer")


def _remaining(connection, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("station exchange expired")
    connection.settimeout(remaining)


def _receive_exact(connection, count, deadline):
    result = bytearray()
    while len(result) < count:
        _remaining(connection, deadline)
        chunk = connection.recv(count - len(result))
        if not chunk:
            raise ValueError("incomplete station frame")
        result.extend(chunk)
    return bytes(result)


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate station field")
        value[key] = item
    return value


def receive(connection, *, limit, deadline):
    length = struct.unpack("!I", _receive_exact(connection, 4, deadline))[0]
    if not 1 <= length <= limit:
        raise ValueError("station frame exceeds bound")
    raw = _receive_exact(connection, length, deadline)
    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid number")))


def send(connection, value, *, limit, deadline):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    if not 1 <= len(raw) <= limit:
        raise ValueError("station frame exceeds bound")
    _remaining(connection, deadline)
    connection.sendall(struct.pack("!I", len(raw)) + raw)
