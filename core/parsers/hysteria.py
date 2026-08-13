from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from core.models import ProxyNode
from core.parsers.base import BaseParser, parse_server_port, build_tls_config


class HysteriaParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if uri.startswith("hysteria2://") or uri.startswith("hy2://"):
            return cls._parse_hy2(uri)
        elif uri.startswith("hysteria://"):
            return cls._parse_hy1(uri)
        return None

    @classmethod
    def _parse_hy2(cls, uri: str) -> Optional[ProxyNode]:
        parsed = urlparse(uri)
        auth = unquote(parsed.username) if parsed.username else ""
        if not auth and "@" in parsed.netloc:
            auth = parsed.netloc.split("@")[0]

        hostname = parsed.hostname or ""
        port = parsed.port or 443
        if not hostname and parsed.netloc:
            host_port_str = parsed.netloc.rsplit("@", 1)[-1]
            hostname, port = parse_server_port(host_port_str, 443)

        if not hostname:
            return None

        fragment = unquote(parsed.fragment) if parsed.fragment else ""
        name = fragment if fragment else f"Hy2-{hostname}:{port}"

        query_raw = parse_qs(parsed.query)
        params = {k: v[0] for k, v in query_raw.items() if v}

        sni = params.get("sni", "").strip()
        insecure = params.get("insecure", "").strip()
        obfs_type = params.get("obfs", "").strip()
        obfs_pass = params.get(
            "obfs-password", params.get("obfs_password", "")
        ).strip()

        config = {
            "type": "hysteria2",
            "tag": name,
            "server": hostname,
            "server_port": port,
        }
        if auth:
            config["auth"] = auth

        tls_cfg = build_tls_config(
            security="tls",
            sni=sni,
            insecure=insecure,
            default_server=hostname,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        if obfs_type:
            obfs_dict = {"type": obfs_type}
            if obfs_pass:
                obfs_dict["password"] = obfs_pass
            config["obfs"] = obfs_dict

        node_id = ProxyNode.generate_id("hysteria2", hostname, port, auth)
        return ProxyNode(
            id=node_id,
            protocol="hysteria2",
            name=name,
            server=hostname,
            port=port,
            raw_uri=uri,
            config=config,
        )

    @classmethod
    def _parse_hy1(cls, uri: str) -> Optional[ProxyNode]:
        parsed = urlparse(uri)
        auth = unquote(parsed.username) if parsed.username else ""
        if not auth and "@" in parsed.netloc:
            auth = parsed.netloc.split("@")[0]

        hostname = parsed.hostname or ""
        port = parsed.port or 443
        if not hostname and parsed.netloc:
            host_port_str = parsed.netloc.rsplit("@", 1)[-1]
            hostname, port = parse_server_port(host_port_str, 443)

        if not hostname:
            return None

        fragment = unquote(parsed.fragment) if parsed.fragment else ""
        name = fragment if fragment else f"Hy1-{hostname}:{port}"

        query_raw = parse_qs(parsed.query)
        params = {k: v[0] for k, v in query_raw.items() if v}

        auth_str = params.get("auth", auth).strip()
        peer = params.get("peer", params.get("sni", "")).strip()
        insecure = params.get("insecure", "").strip()
        alpn = params.get("alpn", "").strip()
        upmbps = params.get("upmbps", params.get("up", "")).strip()
        downmbps = params.get("downmbps", params.get("down", "")).strip()
        obfs = params.get("obfs", "").strip()

        config = {
            "type": "hysteria",
            "tag": name,
            "server": hostname,
            "server_port": port,
        }
        if auth_str:
            config["auth_str"] = auth_str

        if upmbps:
            try:
                config["up_mbps"] = int(upmbps)
            except ValueError:
                pass

        if downmbps:
            try:
                config["down_mbps"] = int(downmbps)
            except ValueError:
                pass

        if obfs:
            config["obfs"] = obfs

        tls_cfg = build_tls_config(
            security="tls",
            sni=peer,
            alpn=alpn,
            insecure=insecure,
            default_server=hostname,
        )
        if tls_cfg:
            config["tls"] = tls_cfg

        node_id = ProxyNode.generate_id("hysteria", hostname, port, auth_str)
        return ProxyNode(
            id=node_id,
            protocol="hysteria",
            name=name,
            server=hostname,
            port=port,
            raw_uri=uri,
            config=config,
        )
