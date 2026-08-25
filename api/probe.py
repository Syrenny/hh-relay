import json
import socket
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HH_SEARCH_URL = (
    "https://hh.ru/search/vacancy"
    "?text=Python&area=1&page=0&enable_snippets=true"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
INITIAL_STATE_MARKER = 'id="HH-Lux-InitialState"'


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status_code = 200

        try:
            request = Request(
                HH_SEARCH_URL,
                headers={
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                    "User-Agent": USER_AGENT,
                },
            )
            with urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")
                payload: dict[str, object] = {
                    "ok": response.status == 200
                    and INITIAL_STATE_MARKER in body,
                    "upstream_status": response.status,
                    "final_host": urlsplit(response.url).hostname,
                    "initial_state_found": INITIAL_STATE_MARKER in body,
                    "response_bytes": len(body.encode("utf-8")),
                }
        except HTTPError as error:
            status_code = 502
            payload = {
                "ok": False,
                "error": "upstream_http_error",
                "upstream_status": error.code,
                "final_host": urlsplit(error.url).hostname,
            }
        except (TimeoutError, socket.timeout):
            status_code = 504
            payload = {"ok": False, "error": "upstream_timeout"}
        except URLError as error:
            status_code = 502
            payload = {
                "ok": False,
                "error": "upstream_connection_error",
                "reason": type(error.reason).__name__,
            }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

