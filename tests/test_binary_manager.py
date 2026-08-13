import os
import tarfile
import io
import pytest
from unittest.mock import patch, MagicMock
from core.models import ProxyNode
from core.binary_manager import BinaryManager

def test_proxy_node_creation():
    node = ProxyNode(
        id="test-123",
        protocol="vless",
        name="[SG] VLESS-Reality - 45ms",
        server="1.1.1.1",
        port=443,
        raw_uri="vless://test@1.1.1.1:443",
        config={"type": "vless", "server": "1.1.1.1", "server_port": 443}
    )
    assert node.id == "test-123"
    assert node.protocol == "vless"
    assert node.is_alive is False
    assert node.to_dict()["name"] == "[SG] VLESS-Reality - 45ms"

def test_proxy_node_generate_id():
    node_id1 = ProxyNode.generate_id("vless", "1.1.1.1", 443, "user1")
    node_id2 = ProxyNode.generate_id("vless", "1.1.1.1", 443, "user1")
    node_id3 = ProxyNode.generate_id("vless", "1.1.1.1", 443, "user2")
    assert node_id1 == node_id2
    assert node_id1 != node_id3
    assert len(node_id1) == 16

def test_proxy_node_from_dict():
    data = {
        "id": "test-456",
        "protocol": "vmess",
        "name": "Test Node",
        "server": "8.8.8.8",
        "port": 8080,
        "raw_uri": "vmess://test",
        "config": {"type": "vmess"},
        "country_code": "US",
        "country_name": "United States",
        "latency": 120,
        "is_alive": True,
        "last_checked": "2026-08-14T00:00:00Z"
    }
    node = ProxyNode.from_dict(data)
    assert node.id == "test-456"
    assert node.country_code == "US"
    assert node.is_alive is True

def test_binary_manager_system_arch():
    manager = BinaryManager(bin_dir="data/bin")
    arch = manager.detect_arch()
    assert "linux" in arch

def test_binary_manager_is_available(tmp_path):
    bin_dir = str(tmp_path / "bin")
    manager = BinaryManager(bin_dir=bin_dir)
    assert manager.is_available() is False

    # Create dummy executable binary
    dummy_bin = os.path.join(bin_dir, "sing-box")
    with open(dummy_bin, "w") as f:
        f.write("#!/bin/sh\necho sing-box")
    os.chmod(dummy_bin, 0o755)

    assert manager.is_available() is True

def test_binary_manager_ensure_singbox_already_available(tmp_path):
    bin_dir = str(tmp_path / "bin")
    manager = BinaryManager(bin_dir=bin_dir)
    dummy_bin = os.path.join(bin_dir, "sing-box")
    with open(dummy_bin, "w") as f:
        f.write("#!/bin/sh\necho sing-box")
    os.chmod(dummy_bin, 0o755)

    path = manager.ensure_singbox()
    assert path == dummy_bin

def test_binary_manager_ensure_singbox_download(tmp_path):
    bin_dir = str(tmp_path / "bin")
    manager = BinaryManager(bin_dir=bin_dir)

    # Create fake tar.gz archive in memory with a sing-box binary
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:gz") as tar:
        binary_content = b"#!/bin/sh\necho sing-box mock"
        tarinfo = tarfile.TarInfo(name="sing-box-1.9.0-linux-amd64/sing-box")
        tarinfo.size = len(binary_content)
        tarinfo.mode = 0o755
        tar.addfile(tarinfo, io.BytesIO(binary_content))

    tar_bytes = tar_stream.getvalue()

    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [tar_bytes]
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        res_path = manager.ensure_singbox()
        assert res_path == os.path.join(bin_dir, "sing-box")
        assert os.path.isfile(res_path)
        assert os.access(res_path, os.X_OK)
