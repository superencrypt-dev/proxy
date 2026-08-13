from typing import Optional
from urllib.parse import parse_qs, unquote
from core.models import ProxyNode
from core.parsers.base import BaseParser, safe_base64_decode, parse_server_port


class ShadowsocksParser(BaseParser):
    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        if not uri.startswith("ss://"):
            return None

        raw = uri[5:]

        fragment = ""
        if "#" in raw:
            raw, fragment_part = raw.split("#", 1)
            fragment = unquote(fragment_part)

        query_str = ""
        if "?" in raw:
            raw, query_str = raw.split("?", 1)

        query_params = {}
        if query_str:
            parsed_q = parse_qs(query_str)
            query_params = {k: v[0] for k, v in parsed_q.items() if v}

        method = ""
        password = ""
        server = ""
        port = 8388

        if "@" in raw:
            userinfo, host_port = raw.rsplit("@", 1)
            server, port = parse_server_port(host_port, 8388)

            if ":" in userinfo:
                method, password = userinfo.split(":", 1)
                method = unquote(method)
                password = unquote(password)
            else:
                decoded_userinfo = safe_base64_decode(userinfo)
                if ":" in decoded_userinfo:
                    method, password = decoded_userinfo.split(":", 1)
        else:
            decoded_legacy = safe_base64_decode(raw)
            if "?" in decoded_legacy:
                decoded_legacy, leg_q = decoded_legacy.split("?", 1)
                if not query_params:
                    parsed_q = parse_qs(leg_q)
                    query_params = {k: v[0] for k, v in parsed_q.items() if v}

            if "@" in decoded_legacy:
                userinfo, host_port = decoded_legacy.rsplit("@", 1)
                server, port = parse_server_port(host_port, 8388)
                if ":" in userinfo:
                    method, password = userinfo.split(":", 1)

        if not server or not method or not password:
            return None

        name = fragment if fragment else f"SS-{server}:{port}"

        config = {
            "type": "shadowsocks",
            "tag": name,
            "server": server,
            "server_port": port,
            "method": method,
            "password": password,
        }

        plugin = query_params.get("plugin", "").strip()
        if plugin:
            if ";" in plugin:
                plugin_name, plugin_opts = plugin.split(";", 1)
                config["plugin"] = plugin_name
                config["plugin_opts"] = plugin_opts
            else:
                config["plugin"] = plugin

        node_id = ProxyNode.generate_id("shadowsocks", server, port, password, method)
        return ProxyNode(
            id=node_id,
            protocol="shadowsocks",
            name=name,
            server=server,
            port=port,
            raw_uri=uri,
            config=config,
        )
