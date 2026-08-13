from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from core.models import ProxyNode
from core.parsers.base import BaseParser, parse_server_port, build_transport_config, build_tls_config


class TrojanParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if not uri.startswith("trojan://"):
            return None

        parsed = urlparse(uri)
        password = unquote(parsed.username) if parsed.username else ""
        if not password and "@" in parsed.netloc:
            password = parsed.netloc.split("@")[0]

        hostname = parsed.hostname or ""
        port = parsed.port or 443
        if not hostname and parsed.netloc:
            host_port_str = parsed.netloc.rsplit("@", 1)[-1]
            hostname, port = parse_server_port(host_port_str, 443)

        if not hostname or not password:
            return None

        fragment = unquote(parsed.fragment) if parsed.fragment else ""
        name = fragment if fragment else f"Trojan-{hostname}:{port}"

        query_raw = parse_qs(parsed.query)
        params = {k: v[0] for k, v in query_raw.items() if v}

        net = params.get("type", params.get("net", "")).strip()
        security = params.get("security", "tls").strip()
        sni = params.get("sni", "").strip()
        fp = params.get("fp", "").strip()
        path = params.get("path", "").strip()
        host = params.get("host", "").strip()
        alpn = params.get("alpn", "").strip()
        insecure = params.get("insecure", params.get("allowInsecure", "")).strip()

        config = {
            "type": "trojan",
            "tag": name,
            "server": hostname,
            "server_port": port,
            "password": password,
        }

        transport = build_transport_config(net, path, host)
        if transport:
            config["transport"] = transport

        tls_cfg = build_tls_config(
            security=security,
            sni=sni,
            fp=fp,
            alpn=alpn,
            insecure=insecure,
            default_server=hostname,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        node_id = ProxyNode.generate_id("trojan", hostname, port, password)
        return ProxyNode(
            id=node_id,
            protocol="trojan",
            name=name,
            server=hostname,
            port=port,
            raw_uri=uri,
            config=config,
        )
