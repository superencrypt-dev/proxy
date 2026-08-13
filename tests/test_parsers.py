import pytest
from core.parsers import UniversalParser


def test_parse_vless_reality():
    uri = "vless://uuid-1234@104.16.1.1:443?type=tcp&security=reality&pbk=publickey123&sni=zoom.us&fp=chrome#Singapore-Node"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "vless"
    assert node.server == "104.16.1.1"
    assert node.port == 443
    assert node.name == "Singapore-Node"
    assert node.config["type"] == "vless"
    assert node.config["uuid"] == "uuid-1234"
    assert node.config["tls"]["enabled"] is True
    assert node.config["tls"]["server_name"] == "zoom.us"
    assert node.config["tls"]["utls"]["fingerprint"] == "chrome"
    assert node.config["tls"]["reality"]["public_key"] == "publickey123"


def test_parse_vless_ws():
    uri = "vless://uuid-5678@example.com:8080?type=ws&path=/vless-ws&host=example.com&security=tls&sni=example.com#VLESS-WS"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "vless"
    assert node.server == "example.com"
    assert node.port == 8080
    assert node.config["transport"]["type"] == "ws"
    assert node.config["transport"]["path"] == "/vless-ws"
    assert node.config["transport"]["headers"]["Host"] == "example.com"


def test_parse_trojan():
    uri = "trojan://password123@trojan.example.com:443?security=tls&sni=trojan.example.com#Trojan-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "trojan"
    assert node.server == "trojan.example.com"
    assert node.port == 443
    assert node.name == "Trojan-Test"
    assert node.config["type"] == "trojan"
    assert node.config["password"] == "password123"
    assert node.config["tls"]["enabled"] is True
    assert node.config["tls"]["server_name"] == "trojan.example.com"


def test_parse_shadowsocks():
    uri = "ss://YWVzLTEyOC1nY206cGFzc3dvcmQxMjM=@1.2.3.4:8388#SS-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "shadowsocks"
    assert node.server == "1.2.3.4"
    assert node.port == 8388
    assert node.name == "SS-Test"
    assert node.config["type"] == "shadowsocks"
    assert node.config["method"] == "aes-128-gcm"
    assert node.config["password"] == "password123"


def test_parse_shadowsocks_unencoded_userinfo():
    uri = "ss://chacha20-ietf-poly1305:secret123@1.1.1.1:8443#SS-Unencoded"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "shadowsocks"
    assert node.server == "1.1.1.1"
    assert node.port == 8443
    assert node.config["method"] == "chacha20-ietf-poly1305"
    assert node.config["password"] == "secret123"


def test_parse_shadowsocks_legacy():
    # base64("aes-256-gcm:pass456@9.9.9.9:9000")
    uri = "ss://YWVzLTI1Ni1nY206cGFzczQ1NkA5LjkuOS45OjkwMDA=#SS-Legacy"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "shadowsocks"
    assert node.server == "9.9.9.9"
    assert node.port == 9000
    assert node.config["method"] == "aes-256-gcm"
    assert node.config["password"] == "pass456"


def test_parse_hysteria2():
    uri = "hysteria2://auth123@hy2.example.com:8443?sni=hy2.example.com&insecure=1#Hy2-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "hysteria2"
    assert node.server == "hy2.example.com"
    assert node.port == 8443
    assert node.name == "Hy2-Test"
    assert node.config["type"] == "hysteria2"
    assert node.config["auth"] == "auth123"
    assert node.config["tls"]["enabled"] is True
    assert node.config["tls"]["insecure"] is True


def test_parse_hy2_alias():
    uri = "hy2://secretpass@hy2.example.org:443?sni=hy2.example.org#Hy2-Alias"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "hysteria2"
    assert node.server == "hy2.example.org"
    assert node.port == 443
    assert node.config["auth"] == "secretpass"


def test_parse_hysteria1():
    uri = "hysteria://hy1.example.com:36712?auth=userpass&peer=hy1.example.com&insecure=1&upmbps=100&downmbps=500#Hy1-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "hysteria"
    assert node.server == "hy1.example.com"
    assert node.port == 36712
    assert node.config["type"] == "hysteria"
    assert node.config["auth_str"] == "userpass"
    assert node.config["up_mbps"] == 100
    assert node.config["down_mbps"] == 500


def test_parse_tuic():
    uri = "tuic://uuid-tuic-999:tuicpass@tuic.example.com:8443?congestion_control=bbr&alpn=h3&sni=tuic.example.com#TUIC-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "tuic"
    assert node.server == "tuic.example.com"
    assert node.port == 8443
    assert node.config["type"] == "tuic"
    assert node.config["uuid"] == "uuid-tuic-999"
    assert node.config["password"] == "tuicpass"
    assert node.config["congestion_control"] == "bbr"
    assert node.config["tls"]["alpn"] == ["h3"]


def test_parse_vmess():
    import base64
    import json

    vmess_json = {
        "v": "2",
        "ps": "VMess-Node",
        "add": "1.2.3.4",
        "port": 443,
        "id": "uuid-vmess-000",
        "aid": 0,
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": "vmess.example.com",
        "path": "/path-ws",
        "tls": "tls",
        "sni": "vmess.example.com",
        "fp": "chrome",
    }
    encoded = base64.b64encode(json.dumps(vmess_json).encode("utf-8")).decode("utf-8")
    uri = f"vmess://{encoded}"

    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "vmess"
    assert node.server == "1.2.3.4"
    assert node.port == 443
    assert node.name == "VMess-Node"
    assert node.config["type"] == "vmess"
    assert node.config["uuid"] == "uuid-vmess-000"
    assert node.config["security"] == "auto"
    assert node.config["transport"]["type"] == "ws"
    assert node.config["transport"]["path"] == "/path-ws"
    assert node.config["transport"]["headers"]["Host"] == "vmess.example.com"
    assert node.config["tls"]["enabled"] is True
    assert node.config["tls"]["utls"]["fingerprint"] == "chrome"


def test_parse_invalid_or_unknown():
    assert UniversalParser.parse_uri("invalid://something") is None
    assert UniversalParser.parse_uri("http://example.com") is None
    assert UniversalParser.parse_uri("not-a-url") is None
