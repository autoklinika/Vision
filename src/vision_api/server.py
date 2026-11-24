"""Minimal local LAB HTTP adapter; no Core construction or hardware access."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .status import boot_status, validate_boot_status

MAX_RESPONSE_BYTES = 4096
PATH = "/api/v1/status"
LOOPBACK = "127.0.0.1"


class LabServer(HTTPServer):
    # No global service, network bind option, or background worker.
    allow_reuse_address = True

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(2.0)
        return sock, address


class Handler(BaseHTTPRequestHandler):
    server_version = "VisionAPI"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args):
        # No raw request paths, client addresses, or exception details in logs.
        return

    def _json(self, status, value, *, allow=False):
        body = json.dumps(value, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("response bound exceeded")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        if allow:
            self.send_header("Allow", "GET")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)

    def _error(self, status, code):
        self._json(status, {"schema": "vision.api.error.v1", "code": code},
                   allow=status == 405)

    def send_error(self, code, message=None, explain=None):
        # Called by the stdlib on malformed requests or unimplemented verbs.
        del message, explain
        if code == 501 or code == 405:
            self._error(405, "METHOD_NOT_ALLOWED")
        elif code >= 500:
            self._error(500, "INTERNAL_ERROR")
        else:
            self._error(400, "BAD_REQUEST")

    def _check_request(self):
        expected_host = f"{LOOPBACK}:{self.server.server_port}"
        if self.headers.get_all("Host") != [expected_host]:
            self._error(403, "HOST_REJECTED")
            return False
        origins = self.headers.get_all("Origin") or []
        fetch_sites = self.headers.get_all("Sec-Fetch-Site") or []
        if (origins not in ([], [f"http://{expected_host}"])
                or fetch_sites not in ([], ["same-origin"], ["none"])):
            self._error(403, "ORIGIN_REJECTED")
            return False
        lengths = self.headers.get_all("Content-Length") or []
        if (lengths not in ([], ["0"])
                or self.headers.get_all("Transfer-Encoding")):
            self._error(400, "BAD_REQUEST")
            return False
        return True

    def do_GET(self):
        if not self._check_request():
            return
        # BaseHTTPRequestHandler normalizes an initial //; require the raw
        # target as well so aliases, query strings, and absolute URLs fail.
        words = self.requestline.split()
        if self.path != PATH or len(words) != 3 or words[1] != PATH:
            self._error(404, "NOT_FOUND")
            return
        try:
            value = boot_status()
            if not validate_boot_status(value):
                raise ValueError("invalid provider report")
        except Exception:
            self._error(500, "INTERNAL_ERROR")
            return
        self._json(200, value)

    def _deny_method(self):
        self._error(405, "METHOD_NOT_ALLOWED")

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = _deny_method


def make_server(port=18491):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid port")
    return LabServer((LOOPBACK, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18491)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    with make_server(args.port) as server:
        print(f"VISION_API_LAB_ONLY port={server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
