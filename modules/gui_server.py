from __future__ import annotations

import json
import logging
import mimetypes
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from modules.utils import PROJECT_ROOT


LOG = logging.getLogger(__name__)


class GuiEventBus:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {
            "status": "starting",
            "message": "Starting JARVIS",
            "transcript": "",
            "assistant": "",
            "history": [],
        }

    def emit(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "event")
        with self._lock:
            if event_type == "status":
                self.state["status"] = event.get("state", self.state["status"])
                self.state["message"] = event.get("message", self.state["message"])
            elif event_type == "transcript":
                self.state["transcript"] = event.get("text", "")
                self._append_history("user", self.state["transcript"])
            elif event_type == "assistant":
                self.state["assistant"] = event.get("text", "")
                self._append_history("assistant", self.state["assistant"])
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            subscriber.put(event)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.state))

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        subscriber.put({"type": "snapshot", **self.snapshot()})
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def _append_history(self, role: str, text: str) -> None:
        if not text:
            return
        history = self.state.setdefault("history", [])
        history.append({"role": role, "text": text})
        del history[:-30]


class GuiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_gui_server(assistant: Any, host: str, port: int, start_voice_loop: bool) -> None:
    dist_dir = PROJECT_ROOT / "dist"
    bus = GuiEventBus()
    assistant_lock = threading.Lock()
    assistant.set_event_sink(bus.emit)
    bus.emit(
        {
            "type": "status",
            "state": "ready",
            "message": "GUI server is ready",
            "voice_loop_enabled": start_voice_loop,
        }
    )

    if start_voice_loop:
        thread = threading.Thread(target=assistant.run_voice_loop, name="jarvis-voice-loop", daemon=True)
        thread.start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "JarvisGUI/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.info("%s - %s", self.address_string(), fmt % args)

        def do_OPTIONS(self) -> None:
            self._send_empty(204)

        def do_GET(self) -> None:
            if self.path == "/api/status":
                self._send_json({**bus.snapshot(), "voiceLoopEnabled": start_voice_loop})
                return
            if self.path == "/api/events":
                self._send_events()
                return
            self._send_static()

        def do_POST(self) -> None:
            if self.path == "/api/command":
                payload = self._read_json()
                text = str(payload.get("text", "")).strip()
                if not text:
                    self._send_json({"ok": False, "error": "Missing command text"}, status=400)
                    return
                with assistant_lock:
                    response = assistant.respond(text)
                self._send_json({"ok": True, "response": response})
                return

            if self.path == "/api/listen-once":
                with assistant_lock:
                    assistant.emit("status", state="listening", message="Listening for speech")
                    assistant.tts.speak("Yes?")
                    text = assistant.stt.listen_once()
                    if not text:
                        assistant.emit("status", state="no_speech", message="No speech detected")
                        assistant.tts.speak("I did not hear that.")
                        self._send_json({"ok": False, "text": "", "response": "I did not hear that."})
                        return
                    response = assistant.respond(text)
                self._send_json({"ok": True, "text": text, "response": response})
                return

            self._send_json({"ok": False, "error": "Not found"}, status=404)

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

        def _send_events(self) -> None:
            subscriber = bus.subscribe()
            self.send_response(200)
            self._send_common_headers(content_type="text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    try:
                        event = subscriber.get(timeout=20)
                        payload = json.dumps(event)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                bus.unsubscribe(subscriber)

        def _send_static(self) -> None:
            if not dist_dir.exists():
                self._send_html(
                    "<!doctype html><title>JARVIS GUI</title>"
                    "<body style='font-family:sans-serif;background:#090909;color:#fff;padding:32px'>"
                    "<h1>JARVIS GUI frontend is not built yet.</h1>"
                    "<p>Run <code>npm install</code> and <code>npm run dev</code> for development, "
                    "or <code>npm run build</code> to serve this page from Python.</p>"
                    "</body>"
                )
                return

            request_path = unquote(self.path.split("?", 1)[0]).lstrip("/")
            if not request_path:
                request_path = "index.html"
            candidate = (dist_dir / request_path).resolve()
            try:
                candidate.relative_to(dist_dir)
            except ValueError:
                self._send_empty(403)
                return
            if not candidate.exists() or candidate.is_dir():
                candidate = dist_dir / "index.html"
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            data = candidate.read_bytes()
            self.send_response(200)
            self._send_common_headers(content_type=content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self._send_common_headers(content_type="application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str, status: int = 200) -> None:
            data = html.encode("utf-8")
            self.send_response(status)
            self._send_common_headers(content_type="text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self._send_common_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_common_headers(self, content_type: str = "text/plain") -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    server = GuiHTTPServer((host, port), Handler)
    print(f"JARVIS GUI API running at http://{host}:{port}")
    if dist_dir.exists():
        print(f"Open http://{host}:{port} in your browser.")
    else:
        print("Frontend dev mode: run npm install, then npm run dev, and open http://127.0.0.1:5173")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
