import io
import re
import pytest
from rich.console import Console
from rich.progress import Progress

from core.models import ProxyNode


EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251]+",
    flags=re.UNICODE
)


def capture_render(render_func, *args, **kwargs) -> str:
    """Helper to capture console output of a rendering method."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None)
    render_func(*args, console=console, **kwargs)
    return buf.getvalue()


def test_ascii_banner_has_no_emojis():
    from tui.themes import ASCII_BANNER
    assert ASCII_BANNER
    assert not EMOJI_PATTERN.search(ASCII_BANNER)


def test_render_banner_output():
    from tui.views import TUIViews
    views = TUIViews()
    output = capture_render(views.render_banner)
    assert "PROXY" in output or "SING-BOX" in output
    assert not EMOJI_PATTERN.search(output)


def test_render_proxy_table():
    from tui.views import TUIViews
    views = TUIViews()
    nodes = [
        ProxyNode(
            id="1",
            protocol="vless",
            name="[SG] VLESS-Test - 45ms",
            server="1.1.1.1",
            port=443,
            raw_uri="vless://test@1.1.1.1:443",
            config={},
            country_code="SG",
            country_name="Singapore",
            latency=45,
            is_alive=True
        ),
        ProxyNode(
            id="2",
            protocol="trojan",
            name="[ID] Trojan-Test - 120ms",
            server="2.2.2.2",
            port=8443,
            raw_uri="trojan://pass@2.2.2.2:8443",
            config={},
            country_code="ID",
            country_name="Indonesia",
            latency=120,
            is_alive=True
        ),
        ProxyNode(
            id="3",
            protocol="vmess",
            name="[US] VMess-Dead",
            server="3.3.3.3",
            port=80,
            raw_uri="vmess://test@3.3.3.3:80",
            config={},
            country_code="US",
            country_name="United States",
            latency=-1,
            is_alive=False
        )
    ]
    output = capture_render(views.render_proxy_table, nodes=nodes, title="DAFTAR PROXY TEST", page=1, page_size=2)
    assert "DAFTAR PROXY TEST" in output
    assert "1.1.1.1" in output
    assert "2.2.2.2" in output
    # Page size is 2, node 3 (3.3.3.3) should not be on page 1
    assert "3.3.3.3" not in output
    assert not EMOJI_PATTERN.search(output)


def test_render_summary():
    from tui.views import TUIViews
    views = TUIViews()
    output = capture_render(views.render_summary, total=100, alive=80, dead=20, duration_sec=12.5)
    assert "100" in output
    assert "80" in output
    assert "20" in output
    assert "12.5" in output or "12.50" in output
    assert not EMOJI_PATTERN.search(output)


def test_render_status_panel():
    from tui.views import TUIViews
    views = TUIViews()
    output = capture_render(views.render_status_panel, title="SYSTEM INFO", message="All systems operational", style="green")
    assert "SYSTEM INFO" in output
    assert "All systems operational" in output
    assert not EMOJI_PATTERN.search(output)


def test_render_runner_status():
    from tui.views import TUIViews
    views = TUIViews()
    runner_status = {
        "running": True,
        "pid": 1234,
        "node_name": "[SG] VLESS-Fast",
        "server": "1.1.1.1",
        "port": 443,
        "protocol": "vless",
        "socks_port": 1080,
        "http_port": 1081
    }
    output = capture_render(views.render_runner_status, runner_status=runner_status)
    assert "RUNNING" in output or "AKTIF" in output
    assert "1080" in output
    assert "1081" in output
    assert "[SG] VLESS-Fast" in output
    assert not EMOJI_PATTERN.search(output)


def test_render_scheduler_status():
    from tui.views import TUIViews
    views = TUIViews()
    sched_status = {
        "active": True,
        "interval_minutes": 60,
        "last_run": "2026-08-14 06:00:00",
        "next_run": "2026-08-14 07:00:00"
    }
    output = capture_render(views.render_scheduler_status, sched_status=sched_status)
    assert "60" in output
    assert "2026-08-14 06:00:00" in output
    assert not EMOJI_PATTERN.search(output)


def test_create_progress_bar():
    from tui.views import TUIViews
    views = TUIViews()
    progress = views.create_progress_bar()
    assert isinstance(progress, Progress)
