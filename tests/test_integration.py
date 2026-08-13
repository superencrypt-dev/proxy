import os
import json
import pytest
from core.collector import ProxyCollector
from core.models import ProxyNode
from core.exporter import ProxyExporter
from core.runner import LocalProxyRunner
from core.scheduler import AutoScheduler


def test_full_pipeline_mock(tmp_path):
    collector = ProxyCollector()
    raw_text = (
        "trojan://testpass@1.1.1.1:443#Singapore-Test\n"
        "vless://uuid@2.2.2.2:443?security=none#Indo-Test"
    )
    nodes = collector.import_from_text(raw_text)
    assert len(nodes) == 2

    # Mock health check result
    nodes[0].is_alive = True
    nodes[0].latency = 45
    nodes[0].country_code = "SG"
    nodes[0].name = "[SG] TROJAN - 1.1.1.1 - 45ms"

    nodes[1].is_alive = False  # Dead

    alive_nodes = [n for n in nodes if n.is_alive]
    assert len(alive_nodes) == 1

    out_file = tmp_path / "clean_sub.txt"
    exporter = ProxyExporter()
    exporter.export_raw(alive_nodes, str(out_file))
    assert out_file.read_text().strip().startswith("trojan://")

    # Additional export format assertions
    b64_file = tmp_path / "sub.b64"
    exporter.export_base64(alive_nodes, str(b64_file))
    assert b64_file.exists()

    clash_file = tmp_path / "clash.yaml"
    exporter.export_clash(alive_nodes, str(clash_file))
    assert clash_file.exists()

    sb_file = tmp_path / "singbox.json"
    exporter.export_singbox(alive_nodes, str(sb_file))
    assert sb_file.exists()


def test_runner_and_scheduler_integration():
    runner = LocalProxyRunner(bin_path="/bin/true")
    status = runner.get_status()
    assert status["status"] == "STOPPED"

    scheduler = AutoScheduler()
    assert not scheduler.is_running()
