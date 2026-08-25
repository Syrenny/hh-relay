from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

HH_SEARCH_URL = "https://hh.ru/search/vacancy"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
INITIAL_STATE_MARKER = 'id="HH-Lux-InitialState"'

app = FastAPI(title="hh.ru connectivity probe")


@app.get("/api/probe")
async def probe() -> JSONResponse:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "User-Agent": USER_AGENT,
            },
            timeout=15,
        ) as client:
            response = await client.get(
                HH_SEARCH_URL,
                params={
                    "text": "Python",
                    "area": 1,
                    "page": 0,
                    "enable_snippets": "true",
                },
            )
            body = response.text
            initial_state_found = INITIAL_STATE_MARKER in body
            payload: dict[str, object] = {
                "ok": response.status_code == 200 and initial_state_found,
                "upstream_status": response.status_code,
                "final_host": urlsplit(str(response.url)).hostname,
                "initial_state_found": initial_state_found,
                "response_bytes": len(response.content),
            }
            status_code = 200 if payload["ok"] else 502
            return JSONResponse(payload, status_code=status_code)
    except httpx.TimeoutException:
        return JSONResponse(
            {"ok": False, "error": "upstream_timeout"},
            status_code=504,
        )
    except httpx.HTTPError as error:
        return JSONResponse(
            {
                "ok": False,
                "error": "upstream_connection_error",
                "reason": type(error).__name__,
            },
            status_code=502,
        )

