"""Authenticated station WebGUI deployment, with a single backend owner.

The production HTTP parser is Waitress. It binds IPv4 loopback only; a separate
trusted TLS reverse proxy may expose the explicitly configured HTTPS origin.
The LAB API adapter remains a separate executable with its original contract.
"""
import argparse
from http import HTTPStatus
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from .access import AccessDenied, Credentials, CursorRejected, ReportUnavailable
from .identity import (CurrentPasswordInvalid, IdentityStore, InvalidIdentityStore,
                       PasswordRejected, RateLimited, parse_session_cookie)
from .reports import MAX_PROTECTED_BYTES, MAX_SEQUENCE
from .server import EVENTS_PATH, LIBRARY_ENTRY, LIBRARY_HISTORY, LIBRARY_PAGE
from .station_owner import NoActiveSession
from .status import boot_status
from vision_station.inspection import InspectionRejected, ID, HEX32
from vision_station.draft_editor import DraftConflict, DraftNotFound, FIELDS, EDITOR_WIRE_LIMIT, ASSET_WIRE_LIMIT

# Two 1024-byte passwords can each expand sixfold with JSON escaping.
MAX_BODY = 16384
MAX_STATIC_FILE = 4 * 1024 * 1024
MAX_STATIC_TOTAL = 24 * 1024 * 1024
ASSET = re.compile(r"/assets/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(js|css|woff2?|ttf|svg|png|ico)", re.ASCII)
MIME = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
        "woff": "font/woff", "woff2": "font/woff2", "ttf": "font/ttf",
        "svg": "image/svg+xml", "png": "image/png", "ico": "image/x-icon"}
STATION_MARKER = b'<meta name="vision-deployment" content="station">'
COOKIE_NAME = "vision_session"
COOKIE_AGE = 8 * 60 * 60


def _no_symlinks(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink path rejected")
    return path


def _load_static(root):
    """Read a bounded allowlist once; no request can open a filesystem path."""
    root = _no_symlinks(root)
    if not root.is_dir():
        raise ValueError("built WebGUI directory required")
    candidates = [root / "index.html", root / "THIRD_PARTY_NOTICES.txt"]
    assets = _no_symlinks(root / "assets")
    if not assets.is_dir():
        raise ValueError("built WebGUI assets required")
    for path in assets.iterdir():
        if len(candidates) >= 128:
            raise ValueError("static asset limit exceeded")
        target = "/assets/" + path.name
        if ASSET.fullmatch(target):
            candidates.append(path)
    result, total = {}, 0
    for path in candidates:
        _no_symlinks(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATIC_FILE:
                raise ValueError("invalid static asset")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                body = stream.read(MAX_STATIC_FILE + 1)
        finally:
            os.close(fd)
        if len(body) > MAX_STATIC_FILE:
            raise ValueError("static asset limit exceeded")
        total += len(body)
        if total > MAX_STATIC_TOTAL:
            raise ValueError("static asset limit exceeded")
        target = "/" + path.relative_to(root).as_posix()
        content_type = ("text/html; charset=utf-8" if target == "/index.html" else
                        "text/plain; charset=utf-8" if target == "/THIRD_PARTY_NOTICES.txt" else
                        MIME[path.suffix[1:]])
        result[target] = (body, content_type)
    if STATION_MARKER not in result["/index.html"][0]:
        raise ValueError("station WebGUI build required")
    result["/"] = result["/index.html"]
    return result


def _origins(values):
    result = {}
    for origin in values:
        if not isinstance(origin, str) or len(origin) > 200:
            raise ValueError("invalid public origin")
        u = urlsplit(origin)
        if (u.path or u.query or u.fragment or u.username or u.password
                or not u.hostname or origin != f"{u.scheme}://{u.netloc}"
                or u.netloc != u.netloc.lower() or not re.fullmatch(r"[a-z0-9.:-]+", u.netloc)):
            raise ValueError("invalid public origin")
        if u.scheme == "http":
            if u.hostname != "127.0.0.1" or u.port is None:
                raise ValueError("HTTP only permitted for IPv4 loopback")
        elif u.scheme != "https":
            raise ValueError("HTTPS required remotely")
        if u.netloc in result:
            raise ValueError("ambiguous public origin")
        result[u.netloc] = origin
    if not result or len(result) > 4:
        raise ValueError("public origins required")
    return result


class StationApplication:
    """Authentication is enforced before accessing any protected owner. Session commands also require operator permission."""

    def __init__(self, *, identity, owner, dist_root, origins):
        self.identity = identity
        self.owner = owner
        self.origins = _origins(origins)
        self.static = _load_static(dist_root)

    @staticmethod
    def _response(start_response, status, body, content_type, *, extra=(), head=False):
        headers = [
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Resource-Policy", "same-origin"),
            ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
            *extra,
        ]
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [b"" if head else body]

    def _json(self, start_response, status, value, *, extra=(), head=False, limit=MAX_PROTECTED_BYTES):
        body = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
        if len(body) > limit:
            raise ReportUnavailable()
        return self._response(start_response, status, body, "application/json; charset=utf-8", extra=extra, head=head)

    def _error(self, start_response, status, code, *, extra=(), head=False):
        return self._json(start_response, status, {"schema": "vision.api.error.v1", "code": code}, extra=extra, head=head)

    @staticmethod
    def _cookie(token, *, secure, clear=False):
        return (f"{COOKIE_NAME}={'' if clear else token}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={0 if clear else COOKIE_AGE}" + ("; Secure" if secure else ""))

    @staticmethod
    def _credentials(environ):
        raw = environ.get("HTTP_COOKIE", "")
        # Waitress joins duplicate headers with a comma. Cookies do not allow
        # commas in this application, so duplicates cannot be silently merged.
        if (not isinstance(raw, str) or len(raw) > 4096 or "," in raw
                or environ.get("HTTP_AUTHORIZATION")):
            raise AccessDenied()
        return parse_session_cookie(raw, name=COOKIE_NAME)

    def _authorize(self, environ, *, touch=True):
        token = self._credentials(environ)
        if token is None:
            raise AccessDenied()
        return self.identity.session(token, touch=touch)

    @staticmethod
    def _body(environ, expected, limit=MAX_BODY):
        length = environ.get("CONTENT_LENGTH", "")
        if (not re.fullmatch(r"[1-9][0-9]{0,6}", length) or int(length) > limit
                or environ.get("CONTENT_TYPE", "") not in ("application/json", "application/json; charset=utf-8")
                or environ.get("HTTP_CONTENT_ENCODING") or environ.get("HTTP_TRANSFER_ENCODING")):
            raise ValueError("invalid request")
        raw = environ["wsgi.input"].read(int(length))
        if len(raw) != int(length):
            raise ValueError("invalid request")
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate field")
                value[key] = item
            return value
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=unique)
        if type(value) is not dict or set(value) != expected:
            raise ValueError("invalid request")
        return value

    def __call__(self, environ, start_response):
        head = environ.get("REQUEST_METHOD") == "HEAD"
        try:
            return self._dispatch(environ, start_response)
        except RateLimited as error:
            return self._error(start_response, 429, "RATE_LIMITED", extra=[("Retry-After", str(error.retry_after))], head=head)
        except CurrentPasswordInvalid:
            return self._error(start_response, 403, "CURRENT_PASSWORD_INVALID", head=head)
        except PasswordRejected:
            return self._error(start_response, 400, "PASSWORD_REJECTED", head=head)
        except AccessDenied:
            return self._error(start_response, 401, "ACCESS_DENIED", head=head)
        except DraftConflict:
            return self._error(start_response, 409, "DRAFT_CONFLICT", head=head)
        except DraftNotFound:
            return self._error(start_response, 404, "DRAFT_NOT_FOUND", head=head)
        except InspectionRejected:
            return self._error(start_response, 409, "INSPECTION_REJECTED", head=head)
        except NoActiveSession:
            return self._error(start_response, 409, "NO_ACTIVE_SESSION", head=head)
        except CursorRejected:
            return self._error(start_response, 409, "CURSOR_REJECTED", head=head)
        except (InvalidIdentityStore, ReportUnavailable):
            return self._error(start_response, 503, "REPORT_UNAVAILABLE", head=head)
        except (ValueError, UnicodeError, TypeError, RecursionError):
            return self._error(start_response, 400, "BAD_REQUEST", head=head)
        except Exception:
            # Paths, credentials, storage exceptions and raw request values
            # never enter response bodies or application logs.
            return self._error(start_response, 503, "REPORT_UNAVAILABLE", head=head)

    def _dispatch(self, environ, start_response):
        host = environ.get("HTTP_HOST", "")
        origin = self.origins.get(host)
        method = environ.get("REQUEST_METHOD", "")
        head = method == "HEAD"
        if origin is None:
            return self._error(start_response, 403, "HOST_REJECTED", head=head)
        path, query = environ.get("PATH_INFO", ""), environ.get("QUERY_STRING", "")
        target = path + ("?" + query if query else "")
        # Waitress supplies the original encoded URI. Reject aliases even if
        # PATH_INFO was decoded. In-memory WSGI tests use the same field.
        raw_uri = environ.get("REQUEST_URI", target)
        if (len(target) > 256 or raw_uri != target or "%" in target or "\\" in target
                or not path.startswith("/") or path.startswith("//")):
            return self._error(start_response, 404, "NOT_FOUND", head=head)
        is_api = path.startswith("/api/")
        if not is_api:
            if method not in ("GET", "HEAD"):
                return self._error(start_response, 405, "METHOD_NOT_ALLOWED", extra=[("Allow", "GET, HEAD")], head=head)
            if query and path not in ("/", "/index.html"):
                return self._error(start_response, 404, "NOT_FOUND", head=head)
            entry = self.static.get(path)
            if entry is None:
                return self._error(start_response, 404, "NOT_FOUND", head=head)
            body, content_type = entry
            return self._response(start_response, 200, body, content_type, head=head)
        if (environ.get("HTTP_ORIGIN") not in (None, origin)
                or environ.get("HTTP_SEC_FETCH_SITE") not in (None, "same-origin", "none")):
            return self._error(start_response, 403, "ORIGIN_REJECTED", head=head)
        secure = origin.startswith("https://")
        if method == "POST" and target in ("/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/password"):
            if (environ.get("HTTP_ORIGIN") != origin
                    or environ.get("HTTP_X_VISION_CLIENT") != "webgui"):
                return self._error(start_response, 403, "ORIGIN_REJECTED")
            if target.endswith("/login"):
                value = self._body(environ, {"username", "password"})
                token, report = self.identity.login(value["username"], value["password"], "station-browser")
                return self._json(start_response, 200, report, extra=[("Set-Cookie", self._cookie(token, secure=secure))])
            if target.endswith("/password"):
                self._authorize(environ, touch=False)
                value = self._body(environ, {"currentPassword", "newPassword"})
                report = self.identity.change_password(self._credentials(environ),
                                                       value["currentPassword"], value["newPassword"])
                return self._json(start_response, 200, report,
                                  extra=[("Set-Cookie", self._cookie("", secure=secure, clear=True))])
            self._body(environ, set())
            token = self._credentials(environ)
            if token:
                self.identity.logout(token)
            return self._json(start_response, 200, {"schema": "vision.api.logout.v1", "loggedOut": True},
                              extra=[("Set-Cookie", self._cookie("", secure=secure, clear=True))])
        if method == "POST" and target in {"/api/v1/library/editor/" + action for action in FIELDS}:
            if (environ.get("HTTP_ORIGIN") != origin
                    or environ.get("HTTP_X_VISION_CLIENT") != "webgui"):
                return self._error(start_response, 403, "ORIGIN_REJECTED")
            identity = self._authorize(environ, touch=False)
            if identity["role"] != "operator":
                return self._error(start_response, 403, "OPERATOR_REQUIRED")
            action = target.rsplit("/",1)[1]
            body = self._body(environ, FIELDS[action], ASSET_WIRE_LIMIT if action=="asset_import" else EDITOR_WIRE_LIMIT)
            report = self.owner.draft_editor(action, body)
            return self._json(start_response, 200, report,
                limit=ASSET_WIRE_LIMIT if action=="asset_preview" else MAX_PROTECTED_BYTES)
        if method == "POST" and target in ("/api/v1/inspection/start", "/api/v1/inspection/close"):
            if (environ.get("HTTP_ORIGIN") != origin
                    or environ.get("HTTP_X_VISION_CLIENT") != "webgui"):
                return self._error(start_response, 403, "ORIGIN_REJECTED")
            identity = self._authorize(environ, touch=False)
            if identity["role"] != "operator":
                return self._error(start_response, 403, "OPERATOR_REQUIRED")
            if target.endswith("/start"):
                body = self._body(environ, {"selectionId", "instanceId", "intentToken"})
                if not isinstance(body["selectionId"], str) or not ID.fullmatch(body["selectionId"]) or not isinstance(body["instanceId"], str) or not HEX32.fullmatch(body["instanceId"]) or not isinstance(body["intentToken"], str) or not HEX32.fullmatch(body["intentToken"]):
                    raise ValueError("invalid inspection request")
                report = self.owner.start_inspection(selection_id=body["selectionId"],
                    instance_id=body["instanceId"], intent_token=body["intentToken"], operator=identity["username"])
            else:
                body = self._body(environ, {"sessionId", "instanceId"})
                if not isinstance(body["sessionId"], str) or not ID.fullmatch(body["sessionId"]) or not isinstance(body["instanceId"], str) or not HEX32.fullmatch(body["instanceId"]):
                    raise ValueError("invalid inspection request")
                report = self.owner.close_inspection(session_id=body["sessionId"],
                    instance_id=body["instanceId"], operator=identity["username"])
            return self._json(start_response, 200, report)
        if method != "GET":
            return self._error(start_response, 405, "METHOD_NOT_ALLOWED", extra=[("Allow", "GET")], head=head)
        if (environ.get("CONTENT_LENGTH", "") not in ("", "0")
                or environ.get("HTTP_TRANSFER_ENCODING") or environ.get("HTTP_CONTENT_ENCODING")):
            return self._error(start_response, 400, "BAD_REQUEST")
        if target == "/api/v1/status":
            return self._json(start_response, 200, boot_status())
        if target == "/api/v1/auth/session":
            return self._json(start_response, 200, self._authorize(environ, touch=False))
        protected = (target in ("/api/v1/station", "/api/v1/session", "/api/v1/library", "/api/v1/inspection")
                     or EVENTS_PATH.fullmatch(target) or LIBRARY_PAGE.fullmatch(target)
                     or LIBRARY_ENTRY.fullmatch(target) or LIBRARY_HISTORY.fullmatch(target))
        if not protected:
            return self._error(start_response, 404, "NOT_FOUND")
        self._authorize(environ)
        if target == "/api/v1/station":
            report = self.owner.station_report()
        elif target == "/api/v1/inspection":
            report = self.owner.inspection_report()
        elif target == "/api/v1/session":
            report = self.owner.session_report()
        elif target == "/api/v1/library":
            report = self.owner.library_reader.library_report(Credentials())
        elif match := EVENTS_PATH.fullmatch(target):
            view, after, through = match.groups()
            after, through = int(after), int(through)
            if after > MAX_SEQUENCE or through > MAX_SEQUENCE or after > through:
                raise CursorRejected()
            report = self.owner.events_report(view=view, after=after, through=through)
        elif match := LIBRARY_PAGE.fullmatch(target):
            view, after = match.groups()
            report = self.owner.library_reader.library_report(Credentials(), view=view, after=int(after))
        elif match := LIBRARY_ENTRY.fullmatch(target):
            entry_id, view = match.groups()
            report = self.owner.library_reader.entry_report(Credentials(), entry_id=entry_id, view=view)
        else:
            match = LIBRARY_HISTORY.fullmatch(target)
            entry_id, view, after = match.groups()
            report = self.owner.library_reader.history_report(Credentials(), entry_id=entry_id, view=view, after=int(after))
        return self._json(start_response, 200, report)


def serve_application(application, *, port):
    from waitress import serve
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid loopback port")
    serve(application, host="127.0.0.1", port=port, threads=4,
          connection_limit=32, backlog=32, channel_timeout=10, cleanup_interval=2,
          max_request_header_size=8192, max_request_body_size=ASSET_WIRE_LIMIT,
          outbuf_overflow=MAX_STATIC_FILE, outbuf_high_watermark=MAX_STATIC_FILE,
          inbuf_overflow=4096, expose_tracebacks=False, ident="Vision",
          clear_untrusted_proxy_headers=True, log_untrusted_proxy_headers=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18490)
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--core-socket", required=True)
    parser.add_argument("--dist", required=True)
    parser.add_argument("--https-origin", action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or any(not x.startswith("https://") for x in args.https_origin):
        parser.error("invalid station endpoint")
    # The API owns browser identity and presentation only. The independently
    # running Core host owns the library and any actual Runtime/Workflow.
    from vision_station.client import RemoteStationOwner
    try:
        identity = IdentityStore(args.accounts, forbidden_roots=(args.dist,))
        owner = RemoteStationOwner(args.core_socket)
        application = StationApplication(identity=identity, owner=owner, dist_root=args.dist,
                                         origins=[f"http://127.0.0.1:{args.port}", *args.https_origin])
    except Exception:
        parser.exit(1, "Station configuration rejected; check private paths and station build.\n")
    print("VISION_STATION_WEBGUI_STARTED core_transport=LOCAL_SOCKET", flush=True)
    serve_application(application, port=args.port)


if __name__ == "__main__":
    main()
