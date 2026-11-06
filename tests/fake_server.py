"""A local fake HTTP server that records requests and answers from scripted responses."""

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlsplit


@dataclass
class RecordedRequest:
    """One request the server received."""

    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: Any


@dataclass
class _Response:
    """One scripted response."""

    status: int
    body: object | str | None
    headers: dict[str, str]
    once: bool
    used: bool = False


@dataclass
class _Routes:
    """The scripted responses and the recorded requests, shared with the handler."""

    responses: dict[tuple[str, str], list[_Response]] = field(default_factory=dict)
    requests: list[RecordedRequest] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def pick(self, method: str, path: str) -> _Response | None:
        """Return the response to send for a route, consuming a once response."""
        for response in self.responses.get((method, path), []):
            if not response.once:
                return response
            if not response.used:
                response.used = True
                return response
        return None


def _make_handler(routes: _Routes) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to routes."""

    class Handler(BaseHTTPRequestHandler):
        """Record the request and send the scripted response."""

        def log_message(self, format: str, *args: Any) -> None:
            """Stay silent so test output stays clean."""

        def _handle(self) -> None:
            """Handle a request of any method."""
            parts = urlsplit(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
            body: Any = raw
            if raw:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = raw
            with routes.lock:
                routes.requests.append(
                    RecordedRequest(self.command, parts.path, parse_qs(parts.query), dict(self.headers.items()), body)
                )
                response = routes.pick(self.command, parts.path)
            if response is None:
                self._send(404, {"error": "no route"}, {})
            else:
                self._send(response.status, response.body, response.headers)

        def _send(self, status: int, body: object | str | None, headers: dict[str, str]) -> None:
            """Write a response."""
            data = b""
            content_type = ""
            if isinstance(body, str):
                data, content_type = body.encode("utf-8"), "text/html; charset=utf-8"
            elif body is not None:
                data, content_type = json.dumps(body).encode("utf-8"), "application/json"
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            for name, value in headers.items():
                self.send_header(name, value)
            if not any(name.lower() == "content-length" for name in headers):
                self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    return Handler


class FakeServer:
    """A context manager running a local HTTP server on a free port."""

    def __init__(self) -> None:
        self._routes = _Routes()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self._routes))
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    @property
    def url(self) -> str:
        """Return the base URL of the server."""
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    @property
    def requests(self) -> list[RecordedRequest]:
        """Return every request received, in order."""
        return self._routes.requests

    def add(
        self,
        method: str,
        path: str,
        status: int,
        body: object | str | None = None,
        *,
        headers: dict[str, str] | None = None,
        once: bool = False,
    ) -> None:
        """Script a response; once responses are used in order, then the next one for the route applies."""
        response = _Response(status, body, headers or {}, once)
        with self._routes.lock:
            self._routes.responses.setdefault((method, path), []).append(response)

    def requests_for(self, method: str, path: str) -> list[RecordedRequest]:
        """Return the requests received for one method and path."""
        return [r for r in self.requests if r.method == method and r.path == path]

    def start(self) -> None:
        """Start serving in a daemon thread."""
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the socket."""
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()

    def __enter__(self) -> Self:
        """Start the server."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the server."""
        self.stop()
