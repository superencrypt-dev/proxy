from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from core.models import ProxyNode
from core.parsers.base import BaseParser, parse_server_port, build_transport_config, build_tls_config


class VLessParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if not uri.startswith("vless://"):
            return None

        parsed = urlparse(uri)
        uuid = unquote(parsed.username) if parsed.username else ""
        if not uuid and "@" in parsed.netloc:
            uuid = parsed.netloc.split("@")[0]

        hostname = parsed.hostname or ""
        port = parsed.port or 443
        if not hostname and parsed.netloc:
            host_port_str = parsed.netloc.rsplit("@", 1)[-1]
            hostname, port = parse_server_port(host_port_str, 443)

        if not hostname or not uuid:
            return None

        fragment = unquote(parsed.fragment) if parsed.fragment else ""
        name = fragment if fragment else f"VLESS-{hostname}:{port}"

        query_raw = parse_qs(parsed.query)
        params = {k: v[0] for k, v in query_raw.items() if v}

        flow = params.get("flow", "").strip()
        net = params.get("type", params.get("net", "")).strip()
        security = params.get("security", "").strip()
        pbk = params.get("pbk", "").strip()
        sni = params.get("sni", "").strip()
        fp = params.get("fp", "").strip()
        sid = params.get("sid", "").strip()
        spx = params.get("spx", "").strip()
        path = params.get("path", params.get("serviceName", "")).strip()
        host = params.get("host", params.get("headerType", "")).strip()
        alpn = params.get("alpn", "").strip()
        insecure = params.get("insecure", params.get("allowInsecure", "")).strip()

        config = {
            "type": "vless",
            "tag": name,
            "server": hostname,
            "server_port": port,
            "uuid": uuid,
        }
        if flow:
            config["flow"] = flow

        transport = build_transport_config(net, path, host)
        if transport:
            config["transport"] = transport

        tls_cfg = build_tls_config(
            security=security,
            sni=sni,
            fp=fp,
            alpn=alpn,
            insecure=insecure,
            pbk=pbk,
            sid=sid,
            spx=spx,
            default_server=hostname,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        node_id = ProxyNode.generate_id("vless", hostname, port, uuid)
        return ProxyNode(
            id=node_id,
            protocol="vless",
            name=name,
            server=hostname,
            port=port,
            raw_uri=uri,
            config=config,
        )
