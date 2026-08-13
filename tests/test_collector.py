import os
import base64
import json
import yaml
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.models import ProxyNode
from core.collector import ProxyCollector


def test_import_from_raw_text():
    raw_content = """
    vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1
    vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1-Duplicate
    trojan://pass@2.2.2.2:443#Node2
    invalid_line_here
    """
    collector = ProxyCollector()
    nodes = collector.import_from_text(raw_content)
    assert len(nodes) == 2  # Deduplicated from 3 valid lines (1 duplicate removed)
    assert nodes[0].protocol == "vless"
    assert nodes[1].protocol == "trojan"


def test_import_from_base64_text():
    raw_content = """vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1
trojan://pass@2.2.2.2:443#Node2"""
    b64_content = base64.b64encode(raw_content.encode()).decode()
    collector = ProxyCollector()
    nodes = collector.import_from_text(b64_content)
    assert len(nodes) == 2
    assert nodes[0].protocol == "vless"
    assert nodes[1].protocol == "trojan"


def test_import_from_file_txt(tmp_path):
    txt_file = tmp_path / "proxies.txt"
    txt_file.write_text(
        "vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1\n"
        "trojan://pass@2.2.2.2:443#Node2\n"
    )
    collector = ProxyCollector()
    nodes = collector.import_from_file(str(txt_file))
    assert len(nodes) == 2


def test_import_from_file_yaml(tmp_path):
    yaml_file = tmp_path / "clash.yaml"
    clash_data = {
        "proxies": [
            {
                "name": "Node1",
                "type": "vless",
                "server": "1.1.1.1",
                "port": 443,
                "uuid": "uuid-1",
            },
            {
                "name": "Node2",
                "type": "trojan",
                "server": "2.2.2.2",
                "port": 443,
                "password": "pass",
            },
        ]
    }
    yaml_file.write_text(yaml.dump(clash_data))
    collector = ProxyCollector()
    nodes = collector.import_from_file(str(yaml_file))
    assert len(nodes) == 2
    assert nodes[0].protocol == "vless"
    assert nodes[1].protocol == "trojan"


def test_import_from_file_json(tmp_path):
    json_file = tmp_path / "proxies.json"
    json_data = {
        "proxies": [
            {
                "name": "Node1",
                "type": "trojan",
                "server": "2.2.2.2",
                "port": 443,
                "password": "pass",
            }
        ]
    }
    json_file.write_text(json.dumps(json_data))
    collector = ProxyCollector()
    nodes = collector.import_from_file(str(json_file))
    assert len(nodes) == 1
    assert nodes[0].protocol == "trojan"


def test_deduplicate():
    collector = ProxyCollector()
    node1 = ProxyNode(
        id="id1",
        protocol="vless",
        name="Node1",
        server="1.1.1.1",
        port=443,
        raw_uri="vless://...",
        config={},
    )
    node2 = ProxyNode(
        id="id1",
        protocol="vless",
        name="Node1 Duplicate",
        server="1.1.1.1",
        port=443,
        raw_uri="vless://...",
        config={},
    )
    node3 = ProxyNode(
        id="id2",
        protocol="trojan",
        name="Node2",
        server="2.2.2.2",
        port=443,
        raw_uri="trojan://...",
        config={},
    )
    nodes = [node1, node2, node3]
    deduped = collector.deduplicate(nodes)
    assert len(deduped) == 2
    assert deduped[0].id == "id1"
    assert deduped[0].name == "Node1"
    assert deduped[1].id == "id2"


@pytest.mark.asyncio
async def test_fetch_from_source():
    collector = ProxyCollector()
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = (
        "vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1\n"
        "trojan://pass@2.2.2.2:443#Node2\n"
    )

    mock_get = MagicMock()
    mock_get.__aenter__.return_value = mock_response
    mock_get.__aexit__.return_value = None
    mock_session.get.return_value = mock_get

    source = {
        "name": "TestSource",
        "url": "https://example.com/sub.txt",
        "type": "raw_lines",
    }
    nodes = await collector.fetch_from_source(source, mock_session)
    assert len(nodes) == 2
    assert nodes[0].protocol == "vless"


@pytest.mark.asyncio
async def test_fetch_all_sources():
    collector = ProxyCollector()
    mock_session = MagicMock()
    mock_response1 = AsyncMock()
    mock_response1.status = 200
    mock_response1.text.return_value = "vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1"

    mock_response2 = AsyncMock()
    mock_response2.status = 200
    mock_response2.text.return_value = "trojan://pass@2.2.2.2:443#Node2"

    mock_get1 = MagicMock()
    mock_get1.__aenter__.return_value = mock_response1
    mock_get1.__aexit__.return_value = None

    mock_get2 = MagicMock()
    mock_get2.__aenter__.return_value = mock_response2
    mock_get2.__aexit__.return_value = None

    mock_session.get.side_effect = [mock_get1, mock_get2]

    sources = [
        {"name": "S1", "url": "https://example.com/1", "type": "raw_lines"},
        {"name": "S2", "url": "https://example.com/2", "type": "raw_lines"},
    ]

    nodes = await collector.fetch_all_sources(sources, session=mock_session)
    assert len(nodes) == 2
