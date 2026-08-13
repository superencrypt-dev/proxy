import os
import yaml
import json
import base64
import pytest
from core.models import ProxyNode
from core.exporter import ProxyExporter


def create_sample_nodes():
    node1 = ProxyNode(
        id="1",
        protocol="trojan",
        name="[SG] Trojan-Fast - 50ms",
        server="1.1.1.1",
        port=443,
        raw_uri="trojan://pass1@1.1.1.1:443#%5BSG%5D%20Trojan-Fast%20-%2050ms",
        config={
            "type": "trojan",
            "server": "1.1.1.1",
            "server_port": 443,
            "password": "pass1",
            "tls": {"enabled": True, "server_name": "1.1.1.1"},
        },
        country_code="SG",
        country_name="Singapore",
        latency=50,
        is_alive=True,
    )
    node2 = ProxyNode(
        id="2",
        protocol="vless",
        name="[ID] VLESS-Reality - 80ms",
        server="2.2.2.2",
        port=443,
        raw_uri="vless://uuid2@2.2.2.2:443#%5BID%5D%20VLESS-Reality%20-%2080ms",
        config={
            "type": "vless",
            "server": "2.2.2.2",
            "server_port": 443,
            "uuid": "uuid2",
            "tls": {
                "enabled": True,
                "server_name": "2.2.2.2",
                "reality": {"enabled": True, "public_key": "pbk123"},
            },
        },
        country_code="ID",
        country_name="Indonesia",
        latency=80,
        is_alive=True,
    )
    node3 = ProxyNode(
        id="3",
        protocol="vmess",
        name="[US] VMess-Slow - 250ms",
        server="3.3.3.3",
        port=80,
        raw_uri="vmess://eyJ2IjoiMiIsInBzIjoiW1VTXSBWTWVzcy1TTE9XLTDI1MG1zIiwiYWRkIjoiMy4zLjMuMyIsInBvcnQiOjgwfQ==",
        config={
            "type": "vmess",
            "server": "3.3.3.3",
            "server_port": 80,
            "uuid": "uuid3",
            "security": "auto",
        },
        country_code="US",
        country_name="United States",
        latency=250,
        is_alive=True,
    )
    return [node1, node2, node3]


def test_export_clash_yaml(tmp_path):
    out_file = tmp_path / "clash.yaml"
    nodes = create_sample_nodes()
    exporter = ProxyExporter()
    res_path = exporter.export_clash(nodes[:1], str(out_file))

    assert res_path == str(out_file)
    assert os.path.exists(str(out_file))

    with open(str(out_file), "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "proxies" in data
    assert len(data["proxies"]) == 1
    assert data["proxies"][0]["name"] == "[SG] Trojan-Fast - 50ms"
    assert data["proxies"][0]["type"] == "trojan"
    assert data["proxies"][0]["server"] == "1.1.1.1"

    assert "proxy-groups" in data
    group_names = [g["name"] for g in data["proxy-groups"]]
    assert "Auto-Select" in group_names
    assert "Fallback" in group_names
    assert "Manual Select" in group_names
    assert "Load-Balance" in group_names

    assert "rules" in data


def test_export_raw(tmp_path):
    out_file = tmp_path / "proxies_raw.txt"
    nodes = create_sample_nodes()
    exporter = ProxyExporter()
    res_path = exporter.export_raw(nodes, str(out_file))

    assert res_path == str(out_file)
    assert os.path.exists(str(out_file))

    with open(str(out_file), "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 3
    assert lines[0] == nodes[0].raw_uri
    assert lines[1] == nodes[1].raw_uri
    assert lines[2] == nodes[2].raw_uri


def test_export_base64(tmp_path):
    out_file = tmp_path / "subscription.txt"
    nodes = create_sample_nodes()
    exporter = ProxyExporter()
    res_path = exporter.export_base64(nodes, str(out_file))

    assert res_path == str(out_file)
    assert os.path.exists(str(out_file))

    with open(str(out_file), "r", encoding="utf-8") as f:
        encoded_content = f.read().strip()

    decoded_bytes = base64.b64decode(encoded_content)
    decoded_str = decoded_bytes.decode("utf-8")
    lines = [line.strip() for line in decoded_str.splitlines() if line.strip()]

    assert len(lines) == 3
    assert lines[0] == nodes[0].raw_uri
    assert lines[1] == nodes[1].raw_uri


def test_export_singbox_json(tmp_path):
    out_file = tmp_path / "singbox.json"
    nodes = create_sample_nodes()
    exporter = ProxyExporter()
    res_path = exporter.export_singbox(nodes, str(out_file))

    assert res_path == str(out_file)
    assert os.path.exists(str(out_file))

    with open(str(out_file), "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "inbounds" in data
    assert len(data["inbounds"]) >= 1
    assert data["inbounds"][0]["type"] == "mixed"
    assert data["inbounds"][0]["listen_port"] == 2080

    assert "outbounds" in data
    outbounds = data["outbounds"]
    outbound_tags = [o["tag"] for o in outbounds]

    assert "select" in outbound_tags
    assert "auto" in outbound_tags
    assert "[SG] Trojan-Fast - 50ms" in outbound_tags
    assert "[ID] VLESS-Reality - 80ms" in outbound_tags
    assert "direct" in outbound_tags
    assert "block" in outbound_tags

    assert "route" in data
    assert "rules" in data["route"]


def test_filter_nodes():
    nodes = create_sample_nodes()
    exporter = ProxyExporter()

    # Filter by country code
    sg_nodes = exporter.filter_nodes(nodes, country="SG")
    assert len(sg_nodes) == 1
    assert sg_nodes[0].country_code == "SG"

    # Filter by protocol
    vless_nodes = exporter.filter_nodes(nodes, protocol="vless")
    assert len(vless_nodes) == 1
    assert vless_nodes[0].protocol == "vless"

    # Filter by max_latency
    fast_nodes = exporter.filter_nodes(nodes, max_latency=100)
    assert len(fast_nodes) == 2
    assert all(n.latency <= 100 for n in fast_nodes)

    # Combined filter
    combined = exporter.filter_nodes(nodes, country="ID", protocol="vless", max_latency=100)
    assert len(combined) == 1
    assert combined[0].id == "2"


def test_export_empty_nodes(tmp_path):
    exporter = ProxyExporter()

    raw_file = str(tmp_path / "empty_raw.txt")
    exporter.export_raw([], raw_file)
    assert os.path.exists(raw_file)

    b64_file = str(tmp_path / "empty_b64.txt")
    exporter.export_base64([], b64_file)
    assert os.path.exists(b64_file)

    clash_file = str(tmp_path / "empty_clash.yaml")
    exporter.export_clash([], clash_file)
    assert os.path.exists(clash_file)

    sb_file = str(tmp_path / "empty_sb.json")
    exporter.export_singbox([], sb_file)
    assert os.path.exists(sb_file)
