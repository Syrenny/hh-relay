import asyncio
import json
import stat
from pathlib import Path
from typing import cast

import httpx
import pytest

from hh_relay.errors import UpstreamProxyError
from hh_relay.sing_box import (
    SingBoxError,
    SingBoxManager,
    SingBoxSettings,
    build_sing_box_config,
    probe_hh_via_proxy,
    proxy_http_client,
)

VLESS_URL = (
    "vless://00000000-0000-4000-8000-000000000000@proxy.example.com:443"
    "?security=reality&type=raw&sni=example.com&fp=chrome"
    "&pbk=public-key&sid=0123456789abcdef&flow=xtls-rprx-vision#Moscow"
)


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


@pytest.mark.asyncio
async def test_manager_starts_only_once_for_concurrent_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary_path = tmp_path / "sing-box"
    binary_path.touch()
    config_path = tmp_path / "config.json"
    process = FakeProcess()
    launches = 0

    async def fake_launch(_manager: SingBoxManager) -> asyncio.subprocess.Process:
        nonlocal launches
        launches += 1
        return cast("asyncio.subprocess.Process", process)

    async def fake_wait(_manager: SingBoxManager) -> None:
        return None

    monkeypatch.setattr(SingBoxManager, "_launch_process", fake_launch)
    monkeypatch.setattr(SingBoxManager, "_wait_until_ready", fake_wait)
    manager = SingBoxManager(
        settings=SingBoxSettings(
            binary_path=binary_path,
            config_path=config_path,
        ),
        vless_url=VLESS_URL,
    )

    await asyncio.gather(*(manager.ensure_started() for _ in range(5)))

    assert launches == 1
    config = json.loads(config_path.read_text())
    assert config["inbounds"][0]["listen_port"] == 19080
    assert config["outbounds"][0]["server"] == "proxy.example.com"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    await manager.close()
    assert process.terminated


@pytest.mark.asyncio
async def test_manager_rejects_missing_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SINGBOX_VLESS_URL", raising=False)
    manager = SingBoxManager()

    with pytest.raises(SingBoxError, match="proxy_not_configured"):
        await manager.ensure_started()


@pytest.mark.asyncio
async def test_manager_rejects_invalid_config() -> None:
    manager = SingBoxManager(vless_url="not-a-vless-url")

    with pytest.raises(SingBoxError, match="proxy_config_invalid"):
        await manager.ensure_started()


@pytest.mark.asyncio
async def test_proxy_client_maps_configuration_error() -> None:
    manager = SingBoxManager(vless_url="not-a-vless-url")

    with pytest.raises(UpstreamProxyError):
        async with proxy_http_client(manager):
            pytest.fail("Invalid proxy config must not yield an HTTP client")


@pytest.mark.asyncio
async def test_probe_confirms_initial_state() -> None:
    manager = SingBoxManager(vless_url=VLESS_URL)

    async def fake_started() -> None:
        return None

    manager.ensure_started = fake_started  # type: ignore[method-assign]
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            content=b'<html><template id="HH-Lux-InitialState">{}</template></html>',
        ),
    )

    result = await probe_hh_via_proxy(manager, transport=transport)

    assert result.status == "ok"
    assert result.sing_box == "running"
    assert result.http_status == 200
    assert result.final_hostname == "hh.ru"
    assert result.initial_state_found
    assert result.response_bytes > 0
    assert result.error_code is None


def test_build_config_from_vless_url() -> None:
    config = build_sing_box_config(VLESS_URL)
    outbound = config["outbounds"][0]  # type: ignore[index]

    assert outbound["server"] == "proxy.example.com"  # type: ignore[index]
    assert outbound["server_port"] == 443  # type: ignore[index]
    assert outbound["uuid"] == "00000000-0000-4000-8000-000000000000"  # type: ignore[index]
    assert outbound["flow"] == "xtls-rprx-vision"  # type: ignore[index]
    tls = outbound["tls"]  # type: ignore[index]
    assert tls["server_name"] == "example.com"  # type: ignore[index]
    assert tls["reality"]["public_key"] == "public-key"  # type: ignore[index]


@pytest.mark.parametrize("transport_type", ["tcp", "raw"])
def test_build_config_accepts_direct_tcp_transport(transport_type: str) -> None:
    build_sing_box_config(VLESS_URL.replace("type=raw", f"type={transport_type}"))
