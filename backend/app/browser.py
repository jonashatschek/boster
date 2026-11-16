"""Run the app inside the visitor's browser, with Pyodide.

The frontend's Web Worker (frontend/src/python/worker.ts) loads this module and
passes each API request to `handle`, which calls the FastAPI app directly over
ASGI. Nothing is sent over the network. The data directory is kept in the
browser's IndexedDB by the worker.
"""

from pathlib import Path

import anyio.to_thread

from app.config import Settings
from app.main import create_app

_app = None


async def _run_without_thread(func, *args, abandon_on_cancel=False, cancellable=None, limiter=None):
    return func(*args)


def boot(data_directory: str, risk_rules_path: str) -> None:
    global _app
    # Browsers have no threads for Python. FastAPI runs synchronous endpoints in a
    # thread pool through anyio, so run them directly instead.
    anyio.to_thread.run_sync = _run_without_thread
    _app = create_app(Settings(data_directory=Path(data_directory), risk_rules_path=Path(risk_rules_path)))


async def handle(method: str, path: str, headers: list, body: bytes) -> tuple[int, list[list[str]], bytes]:
    """Call the app like an HTTP server would. Returns (status, headers, body)."""
    if _app is None:
        raise RuntimeError("boot() has not been called.")
    raw_path, _, query = path.partition("?")
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method.upper(),
        "scheme": "http", "path": raw_path, "raw_path": raw_path.encode(), "query_string": query.encode(),
        "root_path": "", "headers": [(str(k).lower().encode("latin-1"), str(v).encode("latin-1")) for k, v in headers],
        "client": ("browser", 0), "server": ("boster", 80),
    }
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    status = 500
    response_headers: list[list[str]] = []
    chunks: list[bytes] = []

    async def send(message):
        nonlocal status, response_headers
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = [[k.decode("latin-1"), v.decode("latin-1")] for k, v in message.get("headers", [])]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await _app(scope, receive, send)
    return status, response_headers, b"".join(chunks)
