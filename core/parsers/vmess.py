import json
from typing import Optional
from core.models import ProxyNode
from core.parsers.base import BaseParser, safe_base64_decode, build_transport_config, build_tls_config


class VMessParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if not uri.startswith("vmess://"):
            return None

        b64_part = uri[8:]
        b64_part = b64_part.split("#")[0].split("?")[0]

        decoded_str = safe_base64_decode(b64_part)
        try:
            data = json.loads(decoded_str)
        except Exception:
            return None

        server = str(data.get("add", "")).strip()
        try:
            port = int(data.get("port", 443))
        except (ValueError, TypeError):
            port = 443

        uuid = str(data.get("id", "")).strip()
        if not server or not uuid:
            return None

        ps = str(data.get("ps", "")).strip() or f"VMess-{server}:{port}"
        aid = int(data.get("aid", 0)) if data.get("aid") is not None else 0
        scy = str(data.get("scy", "auto")).strip() or "auto"
        net = str(data.get("net", "")).strip()
        type_param = str(data.get("type", "")).strip()
        host = str(data.get("host", "")).strip()
        path = str(data.get("path", "")).strip()
        tls_param = str(data.get("tls", "")).strip()
        sni = str(data.get("sni", "")).strip()
        fp = str(data.get("fp", "")).strip()
        alpn = str(data.get("alpn", "")).strip()

        config = {
            "type": "vmess",
            "tag": ps,
            "server": server,
            "server_port": port,
            "uuid": uuid,
            "security": scy,
            "alter_id": aid,
        }

        transport = build_transport_config(net, path, host, type_param)
        if transport:
            config["transport"] = transport

        security = "tls" if tls_param in ("tls", "1", "true") else ""
        tls_cfg = build_tls_config(
            security=security,
            sni=sni,
            fp=fp,
            alpn=alpn,
            default_server=server,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        node_id = ProxyNode.generate_id("vmess", server, port, uuid)
        return ProxyNode(
            id=node_id,
            protocol="vmess",
            name=ps,
            server=server,
            port=port,
            raw_uri=uri,
            config=config,
        )
