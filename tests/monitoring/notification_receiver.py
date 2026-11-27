"""Destino sintético de webhooks; las reglas y el notificador de Grafana son reales."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

EVENTS = []
LOCK = Lock()


class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/events":
            self.send_error(404)
            return
        with LOCK:
            data = json.dumps(EVENTS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/alerts":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 1_048_576:
            self.send_error(413)
            return
        event = json.loads(self.rfile.read(length))
        with LOCK:
            EVENTS.append(event)
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Receiver).serve_forever()
