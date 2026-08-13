import os
import time
import pytest
from unittest.mock import MagicMock, patch

from core.models import ProxyNode
from core.runner import LocalProxyRunner
from core.scheduler import AutoScheduler


def test_runner_config_generation():
    runner = LocalProxyRunner(bin_path="sing-box")
    node = ProxyNode(
        id="1",
        protocol="trojan",
        name="[ID] Trojan - 40ms",
        server="1.1.1.1",
        port=443,
        raw_uri="trojan://pass@1.1.1.1:443",
        config={"type": "trojan", "tag": "proxy-out", "server": "1.1.1.1", "server_port": 443, "password": "pass"}
    )
    cfg = runner._generate_runner_config(node, socks_port=1080, http_port=1081)
    assert len(cfg["inbounds"]) == 2
    assert cfg["inbounds"][0]["listen_port"] == 1080
    assert cfg["inbounds"][1]["listen_port"] == 1081
    assert cfg["outbounds"][0]["tag"] == "proxy-out"


def test_runner_start_stop_lifecycle():
    runner = LocalProxyRunner(bin_path="sing-box")
    node = ProxyNode(
        id="2",
        protocol="vless",
        name="[SG] Vless - 20ms",
        server="2.2.2.2",
        port=443,
        raw_uri="vless://id@2.2.2.2:443",
        config={"type": "vless", "tag": "proxy-out", "server": "2.2.2.2", "server_port": 443}
    )

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 12345
    mock_proc.terminate = MagicMock()
    mock_proc.wait = MagicMock()

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch.object(runner, "_check_port_open", return_value=True), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="sing-box"):

        started = runner.start(node, socks_port=1080, http_port=1081)
        assert started is True
        assert runner.is_running() is True

        status = runner.get_status()
        assert status["status"] == "RUNNING"
        assert status["socks_port"] == 1080
        assert status["http_port"] == 1081
        assert status["pid"] == 12345
        assert status["node"]["id"] == "2"

        stopped = runner.stop()
        assert stopped is True
        assert runner.is_running() is False

        status_after = runner.get_status()
        assert status_after["status"] == "STOPPED"
        assert status_after["pid"] is None


def test_runner_start_failure():
    runner = LocalProxyRunner(bin_path="sing-box")
    node = ProxyNode(
        id="3",
        protocol="ss",
        name="[US] Shadowsocks",
        server="3.3.3.3",
        port=8388,
        raw_uri="ss://...",
        config={"type": "shadowsocks"}
    )

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1  # Process exited immediately with error

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="sing-box"):

        started = runner.start(node, socks_port=1080, http_port=1081)
        assert started is False
        assert runner.is_running() is False


def test_runner_check_port_open():
    runner = LocalProxyRunner(bin_path="sing-box")

    # Test single arg port
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value = MagicMock()
        assert runner._check_port_open(1080) is True
        mock_conn.assert_called_with(("127.0.0.1", 1080), timeout=0.5)

    # Test host and port args
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value = MagicMock()
        assert runner._check_port_open("127.0.0.1", 1080) is True
        mock_conn.assert_called_with(("127.0.0.1", 1080), timeout=0.5)

    # Test closed port
    with patch("socket.create_connection", side_effect=OSError("Port closed")):
        assert runner._check_port_open(1080) is False


def test_runner_start_port_check_failure():
    runner = LocalProxyRunner(bin_path="sing-box")
    node = ProxyNode(
        id="4",
        protocol="vless",
        name="[SG] Port Fail",
        server="4.4.4.4",
        port=443,
        raw_uri="vless://...",
        config={"type": "vless"}
    )
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # Process claims to be alive

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch.object(runner, "_check_port_open", return_value=False), \
         patch("core.binary_manager.BinaryManager.ensure_singbox", return_value="sing-box"):

        started = runner.start(node, socks_port=1080, http_port=1081)
        assert started is False
        assert runner.is_running() is False


def test_scheduler_lifecycle():
    scheduler = AutoScheduler()
    assert scheduler.is_running() is False

    task_mock = MagicMock()
    log_mock = MagicMock()

    scheduler.start(interval_minutes=1, task_callback=task_mock, on_log=log_mock)
    assert scheduler.is_running() is True

    status = scheduler.get_status()
    assert status["status"] == "RUNNING"
    assert status["interval_minutes"] == 1

    # Stop scheduler
    scheduler.stop()
    assert scheduler.is_running() is False

    status_stopped = scheduler.get_status()
    assert status_stopped["status"] == "STOPPED"


def test_scheduler_triggers_task():
    scheduler = AutoScheduler()
    call_count = 0

    def dummy_task():
        nonlocal call_count
        call_count += 1

    real_sleep = time.sleep
    with patch("time.sleep", side_effect=lambda s: real_sleep(0.001)):
        scheduler._check_interval = 0.01
        scheduler.start(interval_minutes=0.0001, task_callback=dummy_task)
        real_sleep(0.05)
        scheduler.stop()

    assert call_count >= 1
    assert scheduler.last_run != ""

