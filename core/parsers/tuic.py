from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from core.models import ProxyNode
from core.parsers.base import BaseParser, parse_server_port, build_tls_config


class TUICParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if not uri.startswith("tuic://"):
            return None

        parsed = urlparse(uri)
        userinfo = unquote(parsed.username) if parsed.username else ""
        password = unquote(parsed.password) if parsed.password else ""

        if not userinfo and "@" in parsed.netloc:
            raw_userinfo = parsed.netloc.split("@")[0]
            if ":" in raw_userinfo:
                userinfo, password = raw_userinfo.split(":", 1)
            else:
                userinfo = raw_userinfo

        uuid = userinfo
        hostname = parsed.hostname or ""
        port = parsed.port or 8443
        if not hostname and parsed.netloc:
            host_port_str = parsed.netloc.rsplit("@", 1)[-1]
            hostname, port = parse_server_port(host_port_str, 8443)

        if not hostname or not uuid:
            return None

        fragment = unquote(parsed.fragment) if parsed.fragment else ""
        name = fragment if fragment else f"TUIC-{hostname}:{port}"

        query_raw = parse_qs(parsed.query)
        params = {k: v[0] for k, v in query_raw.items() if v}

        congestion_control = params.get("congestion_control", "").strip()
        udp_relay_mode = params.get("udp_relay_mode", "").strip()
        zero_rtt = params.get("zero_rtt_handshake", "").strip()
        sni = params.get("sni", "").strip()
        alpn = params.get("alpn", "").strip()
        insecure = params.get("insecure", params.get("allow_insecure", "")).strip()

        config = {
            "type": "tuic",
            "tag": name,
            "server": hostname,
            "server_port": port,
            "uuid": uuid,
        }
        if password:
            config["password"] = password
        if congestion_control:
            config["congestion_control"] = congestion_control
        if udp_relay_mode:
            config["udp_relay_mode"] = udp_relay_mode
        if zero_rtt.lower() in ("1", "true", "yes"):
            config["zero_rtt_handshake"] = True

        tls_cfg = build_tls_config(
            security="tls",
            sni=sni,
            alpn=alpn,
            insecure=insecure,
            default_server=hostname,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        node_id = ProxyNode.generate_id("tuic", hostname, port, uuid)
        return ProxyNode(
            id=node_id,
            protocol="tuic",
            name=name,
            server=hostname,
            port=port,
            raw_uri=uri,
            config=config,
        )
