import os
import json
import tempfile
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.models import ProxyNode
from core.checker import ProxyChecker


@pytest.mark.asyncio
async def test_generate_singbox_temp_config():
    checker = ProxyChecker(concurrency=5, timeout=3000)
    node = ProxyNode(
        id="test",
        protocol="trojan",
        name="test",
        server="1.1.1.1",
        port=443,
        raw_uri="",
        config={"type": "trojan", "tag": "proxy-out", "server": "1.1.1.1", "server_port": 443, "password": "p"}
    )
    cfg = checker._build_temp_config(node, inbound_port=25000)
    assert cfg["inbounds"][0]["listen_port"] == 25000
    assert cfg["outbounds"][0]["tag"] == "proxy-out"


@pytest.mark.asyncio
async def test_check_single_node_success():
    checker = ProxyChecker(concurrency=2, timeout=3000)
    node = ProxyNode(
        id="test1",
        protocol="vless",
        name="server1",
        server="1.1.1.1",
        port=443,
        raw_uri="",
        config={"type": "vless", "server": "1.1.1.1", "server_port": 443}
    )

    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
         patch.object(checker, "_wait_for_port", return_value=True), \
         patch.object(checker, "_http_get_check", return_value=120.5), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="/fake/bin/sing-box"):
        
        checked = await checker.check_single_node(node)
        assert checked.is_alive is True
        assert checked.latency == 120
        assert checked.last_checked != ""
        mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_check_single_node_failure():
    checker = ProxyChecker(concurrency=2, timeout=3000)
    node = ProxyNode(
        id="test2",
        protocol="trojan",
        name="server2",
        server="2.2.2.2",
        port=443,
        raw_uri="",
        config={"type": "trojan", "server": "2.2.2.2", "server_port": 443}
    )

    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
         patch.object(checker, "_wait_for_port", return_value=True), \
         patch.object(checker, "_http_get_check", side_effect=Exception("Timeout")), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="/fake/bin/sing-box"):
        
        checked = await checker.check_single_node(node)
        assert checked.is_alive is False
        assert checked.latency == -1
        mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_check_single_node_cleanup_on_exception():
    checker = ProxyChecker(concurrency=2, timeout=3000)
    node = ProxyNode(
        id="test3",
        protocol="ss",
        name="server3",
        server="3.3.3.3",
        port=8388,
        raw_uri="",
        config={"type": "shadowsocks", "server": "3.3.3.3", "server_port": 8388}
    )

    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()

    created_files = []

    original_open = open

    with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("Subprocess failed")), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="/fake/bin/sing-box"):
        
        checked = await checker.check_single_node(node)
        assert checked.is_alive is False
        assert checked.latency == -1


@pytest.mark.asyncio
async def test_check_nodes_concurrency():
    checker = ProxyChecker(concurrency=3, timeout=3000)
    nodes = [
        ProxyNode(id=f"n{i}", protocol="vless", name=f"n{i}", server=f"10.0.0.{i}", port=443, raw_uri="", config={})
        for i in range(5)
    ]

    async def mock_check(node):
        res = ProxyNode(
            id=node.id,
            protocol=node.protocol,
            name=node.name,
            server=node.server,
            port=node.port,
            raw_uri=node.raw_uri,
            config=node.config
        )
        if node.id in ("n0", "n2"):
            res.is_alive = True
            res.latency = 50
        else:
            res.is_alive = False
            res.latency = -1
        return res

    progress_calls = []

    def on_progress(completed, total, last_node):
        progress_calls.append((completed, total, last_node.id))

    with patch.object(checker, "check_single_node", side_effect=mock_check), \
         patch.object(checker.geoip_resolver, "resolve_country_async", return_value=("US", "United States")):
        
        alive, dead = await checker.check_nodes(nodes, on_progress=on_progress)
        assert len(alive) == 2
        assert len(dead) == 3
        assert len(progress_calls) == 5
        assert progress_calls[-1][0] == 5
        assert progress_calls[-1][1] == 5
        # Alive nodes should have GeoIP resolved and name standardized
        for node in alive:
            assert node.country_code == "US"
            assert node.country_name == "United States"
            assert "[US]" in node.name


@pytest.mark.asyncio
async def test_fast_tcp_ping():
    checker = ProxyChecker(enable_fast_ping=True, fast_ping_timeout=500)
    node = ProxyNode(
        id="ping_test",
        protocol="trojan",
        name="ping_node",
        server="192.0.2.1",
        port=443,
        raw_uri="",
        config={}
    )

    with patch.object(checker, "_fast_tcp_ping", return_value=False):
        checked = await checker.check_single_node(node)
        assert checked.is_alive is False
        assert checked.latency == -1
