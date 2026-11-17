import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen


def format_alert(payload: dict) -> str:
    status = payload.get("status", "unknown").upper()
    alerts = payload.get("alerts", [])
    lines = [f"Infrastructure Lab: {status}"]
    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        lines.append(
            "\n".join(
                [
                    f"• {labels.get('alertname', 'Unnamed alert')}",
                    f"  Service: {labels.get('service', 'unknown')}",
                    f"  Severity: {labels.get('severity', 'unknown')}",
                    f"  {annotations.get('summary', 'No summary provided')}",
                ]
            )
        )
    return "\n".join(lines)


def send_telegram_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("Telegram settings are not configured")

    body = json.dumps({"chat_id": chat_id, "text": text}).encode()
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram returned HTTP {response.status}")


class AlertHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length))
            send_telegram_message(format_alert(payload))
        except (ValueError, RuntimeError, URLError) as error:
            print(f"Alert delivery failed: {error}", flush=True)
            self.send_error(503, "Alert delivery unavailable")
            return

        self.send_response(202)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8081), AlertHandler).serve_forever()
