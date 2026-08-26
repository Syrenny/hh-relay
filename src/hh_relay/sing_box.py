from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

import httpx

from hh_relay.client import DEFAULT_HEADERS, HH_SEARCH_URL
from hh_relay.models import ProxyHealthResponse

SING_BOX_VLESS_URL_ENV: Final = "SINGBOX_VLESS_URL"
SING_BOX_HOST: Final = "127.0.0.1"
SING_BOX_PORT: Final = 19080
SING_BOX_STARTUP_TIMEOUT: Final = 5.0
TEMP_DIRECTORY: Final = Path(tempfile.gettempdir())
SING_BOX_CONFIG_PATH: Final = TEMP_DIRECTORY / "hh-relay-sing-box.json"
SING_BOX_BINARY_PATH: Final = Path(
    os.getenv(
        "SINGBOX_BINARY_PATH",
        str(Path(__file__).resolve().parent / "vendor" / "sing-box"),
    ),
)
INITIAL_STATE_MARKER: Final = b' id="HH-Lux-InitialState"'
PROXY_NOT_CONFIGURED: Final = "proxy_not_configured"
PROXY_CONFIG_INVALID: Final = "proxy_config_invalid"
PROXY_BINARY_MISSING: Final = "proxy_binary_missing"
PROXY_START_FAILED: Final = "proxy_start_failed"
PROXY_NOT_READY: Final = "proxy_not_ready"


class SingBoxError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SingBoxSettings:
    binary_path: Path = SING_BOX_BINARY_PATH
    config_path: Path = SING_BOX_CONFIG_PATH
    host: str = SING_BOX_HOST
    port: int = SING_BOX_PORT
    startup_timeout: float = SING_BOX_STARTUP_TIMEOUT


DEFAULT_SING_BOX_SETTINGS: Final = SingBoxSettings()


class SingBoxManager:
    def __init__(
        self,
        *,
        settings: SingBoxSettings = DEFAULT_SING_BOX_SETTINGS,
        vless_url: str | None = None,
    ) -> None:
        self._settings = settings
        self._vless_url = vless_url
        self._process: asyncio.subprocess.Process | None = None
        self._ready = False
        self._lock = asyncio.Lock()

    @property
    def proxy_url(self) -> str:
        return f"socks5://{self._settings.host}:{self._settings.port}"

    async def ensure_started(self) -> None:
        if self._is_running():
            return
        async with self._lock:
            if self._is_running():
                return
            await self._stop_process()
            config = self._create_config()
            self._write_config(config)
            self._process = await self._launch_process()
            try:
                await self._wait_until_ready()
            except SingBoxError:
                await self._stop_process()
                raise
            self._ready = True

    async def close(self) -> None:
        async with self._lock:
            await self._stop_process()

    def _is_running(self) -> bool:
        return (
            self._ready
            and self._process is not None
            and self._process.returncode is None
        )

    def _create_config(self) -> bytes:
        vless_url = self._vless_url or os.getenv(SING_BOX_VLESS_URL_ENV)
        if not vless_url:
            raise SingBoxError(PROXY_NOT_CONFIGURED)
        try:
            config = build_sing_box_config(
                vless_url,
                listen_host=self._settings.host,
                listen_port=self._settings.port,
            )
        except (TypeError, ValueError) as error:
            raise SingBoxError(PROXY_CONFIG_INVALID) from error
        return json.dumps(config, ensure_ascii=False).encode()

    def _write_config(self, config: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        descriptor = os.open(self._settings.config_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            os.close(descriptor)
            raise
        with os.fdopen(descriptor, "wb") as output:
            output.write(config)

    async def _launch_process(self) -> asyncio.subprocess.Process:
        if not self._settings.binary_path.is_file():
            raise SingBoxError(PROXY_BINARY_MISSING)
        try:
            return await asyncio.create_subprocess_exec(
                str(self._settings.binary_path),
                "run",
                "-c",
                str(self._settings.config_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(TEMP_DIRECTORY),
            )
        except OSError as error:
            raise SingBoxError(PROXY_START_FAILED) from error

    async def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self._settings.startup_timeout
        while time.monotonic() < deadline:
            if self._process is None or self._process.returncode is not None:
                raise SingBoxError(PROXY_START_FAILED)
            try:
                _reader, writer = await asyncio.open_connection(
                    self._settings.host,
                    self._settings.port,
                )
            except OSError:
                await asyncio.sleep(0.05)
                continue
            writer.close()
            await writer.wait_closed()
            return
        raise SingBoxError(PROXY_NOT_READY)

    async def _stop_process(self) -> None:
        process = self._process
        self._process = None
        self._ready = False
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.kill()
            await process.wait()


def build_sing_box_config(
    vless_url: str,
    *,
    listen_host: str = SING_BOX_HOST,
    listen_port: int = SING_BOX_PORT,
) -> dict[str, object]:
    parsed = urlsplit(vless_url)
    if parsed.scheme != "vless" or parsed.hostname is None or parsed.username is None:
        raise ValueError(PROXY_CONFIG_INVALID)
    if parsed.password is not None:
        raise ValueError(PROXY_CONFIG_INVALID)
    try:
        server_port = parsed.port
        user_id = str(UUID(unquote(parsed.username)))
    except ValueError as error:
        raise ValueError(PROXY_CONFIG_INVALID) from error
    if server_port is None:
        raise ValueError(PROXY_CONFIG_INVALID)

    query = parse_qs(parsed.query, keep_blank_values=True)
    if _query_value(query, "security") != "reality":
        raise ValueError(PROXY_CONFIG_INVALID)
    if _query_value(query, "type", default="tcp") != "tcp":
        raise ValueError(PROXY_CONFIG_INVALID)

    outbound: dict[str, object] = {
        "type": "vless",
        "tag": "hh-vless",
        "server": parsed.hostname,
        "server_port": server_port,
        "uuid": user_id,
        "tls": {
            "enabled": True,
            "server_name": _query_value(query, "sni"),
            "utls": {
                "enabled": True,
                "fingerprint": _query_value(query, "fp", default="chrome"),
            },
            "reality": {
                "enabled": True,
                "public_key": _query_value(query, "pbk"),
                "short_id": _query_value(query, "sid"),
            },
        },
    }
    flow = _query_value(query, "flow", default="")
    if flow:
        outbound["flow"] = flow

    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [
            {
                "type": "socks",
                "tag": "hh-socks",
                "listen": listen_host,
                "listen_port": listen_port,
            },
        ],
        "outbounds": [outbound],
        "route": {"final": "hh-vless"},
    }


def _query_value(
    query: dict[str, list[str]],
    name: str,
    *,
    default: str | None = None,
) -> str:
    values = query.get(name)
    if values and values[0]:
        return values[0]
    if default is not None:
        return default
    raise ValueError(PROXY_CONFIG_INVALID)


async def probe_hh_via_proxy(
    manager: SingBoxManager,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProxyHealthResponse:
    try:
        await manager.ensure_started()
    except SingBoxError as error:
        return _proxy_error(error.code)

    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            proxy=manager.proxy_url if transport is None else None,
            transport=transport,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(15.0, connect=5.0),
        ) as client:
            response = await client.get(
                HH_SEARCH_URL,
                params={
                    "text": "Python backend",
                    "area": 1,
                    "page": 0,
                    "order_by": "publication_time",
                },
            )
    except httpx.TimeoutException:
        return _proxy_error("upstream_timeout", elapsed_ms=_elapsed_ms(started_at))
    except httpx.HTTPError:
        return _proxy_error("upstream_http_error", elapsed_ms=_elapsed_ms(started_at))

    marker_found = INITIAL_STATE_MARKER in response.content
    error_code: str | None = None
    if response.status_code == httpx.codes.FORBIDDEN:
        error_code = "upstream_forbidden"
    elif response.status_code != httpx.codes.OK:
        error_code = "upstream_http_error"
    elif not marker_found:
        error_code = "upstream_structure_changed"

    return ProxyHealthResponse(
        status="ok" if error_code is None else "error",
        sing_box="running",
        http_status=response.status_code,
        final_hostname=response.url.host,
        elapsed_ms=_elapsed_ms(started_at),
        response_bytes=len(response.content),
        initial_state_found=marker_found,
        error_code=error_code,
    )


def _proxy_error(code: str, *, elapsed_ms: int | None = None) -> ProxyHealthResponse:
    return ProxyHealthResponse(
        status="error",
        sing_box="error" if code.startswith("proxy_") else "running",
        elapsed_ms=elapsed_ms,
        error_code=code,
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
