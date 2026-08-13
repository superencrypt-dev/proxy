import os
import re
import json
import yaml
import base64
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from core.models import ProxyNode
from core.parsers import UniversalParser
from core.parsers.base import safe_base64_decode


def clash_proxy_to_uri(p: dict) -> Optional[str]:
    """Convert Clash proxy dictionary representation to standard proxy URI."""
    if not isinstance(p, dict):
        return None

    ptype = str(p.get("type", "")).lower().strip()
    name = str(p.get("name", "")).strip()
    server = str(p.get("server", "")).strip()
    port = p.get("port", 443)

    if not server or not ptype:
        return None

    if ptype == "vless":
        uuid = p.get("uuid", "")
        net = p.get("network", "tcp")
        tls = "tls" if p.get("tls") or p.get("reality-opts") else "none"
        if p.get("reality-opts"):
            tls = "reality"
        sni = p.get("servername") or p.get("sni", "")
        ws_opts = p.get("ws-opts", {}) or {}
        path = ws_opts.get("path", "") if isinstance(ws_opts, dict) else ""
        host = ""
        if isinstance(ws_opts, dict) and isinstance(ws_opts.get("headers"), dict):
            host = ws_opts.get("headers", {}).get("Host", "")

        query = f"type={net}&security={tls}"
        if sni:
            query += f"&sni={sni}"
        if path:
            query += f"&path={path}"
        if host:
            query += f"&host={host}"
        if p.get("reality-opts") and isinstance(p.get("reality-opts"), dict):
            ropts = p["reality-opts"]
            if ropts.get("public-key"):
                query += f"&pbk={ropts.get('public-key')}"
            if ropts.get("short-id"):
                query += f"&sid={ropts.get('short-id')}"
        return f"vless://{uuid}@{server}:{port}?{query}#{name}"

    elif ptype == "trojan":
        password = p.get("password", "")
        sni = p.get("sni") or p.get("servername", "")
        sec = "tls" if p.get("tls", True) else "none"
        query = f"security={sec}"
        if sni:
            query += f"&sni={sni}"
        return f"trojan://{password}@{server}:{port}?{query}#{name}"

    elif ptype in ("ss", "shadowsocks"):
        cipher = p.get("cipher", "")
        password = p.get("password", "")
        userinfo = base64.b64encode(f"{cipher}:{password}".encode()).decode()
        return f"ss://{userinfo}@{server}:{port}#{name}"

    elif ptype == "vmess":
        uuid = p.get("uuid", "")
        net = p.get("network", "tcp")
        tls = "tls" if p.get("tls") else ""
        ws_opts = p.get("ws-opts", {}) or {}
        path = ws_opts.get("path", "") if isinstance(ws_opts, dict) else ""
        host = ""
        if isinstance(ws_opts, dict) and isinstance(ws_opts.get("headers"), dict):
            host = ws_opts.get("headers", {}).get("Host", "")

        vmess_dict = {
            "v": "2",
            "ps": name,
            "add": server,
            "port": str(port),
            "id": uuid,
            "aid": str(p.get("alterId", 0)),
            "net": net,
            "type": "none",
            "host": host,
            "path": path,
            "tls": tls,
        }
        b64_json = base64.b64encode(json.dumps(vmess_dict).encode()).decode()
        return f"vmess://{b64_json}"

    elif ptype in ("hysteria2", "hy2"):
        password = p.get("password") or p.get("auth", "")
        sni = p.get("sni") or p.get("servername", "")
        insecure = "1" if p.get("skip-cert-verify") else "0"
        query = f"sni={sni}&insecure={insecure}"
        return f"hysteria2://{password}@{server}:{port}?{query}#{name}"

    elif ptype == "tuic":
        uuid = p.get("uuid", "")
        password = p.get("password", "")
        sni = p.get("sni") or p.get("servername", "")
        userinfo = f"{uuid}:{password}" if password else uuid
        query = f"sni={sni}"
        return f"tuic://{userinfo}@{server}:{port}?{query}#{name}"

    elif ptype in ("hysteria", "hy"):
        auth = p.get("auth_str") or p.get("auth", "")
        sni = p.get("sni") or p.get("servername", "")
        query = f"auth={auth}&sni={sni}"
        return f"hysteria://{server}:{port}?{query}#{name}"

    return None


class ProxyCollector:
    """Collector for retrieving, importing, parsing, and deduplicating proxy nodes."""

    @staticmethod
    def deduplicate(nodes: List[ProxyNode]) -> List[ProxyNode]:
        """Deduplicate proxy nodes based on node.id while preserving uniqueness and order."""
        seen_ids = set()
        unique_nodes = []
        for node in nodes:
            if node and node.id and node.id not in seen_ids:
                seen_ids.add(node.id)
                unique_nodes.append(node)
        return unique_nodes

    def _try_decode_base64(self, text: str) -> Optional[str]:
        cleaned = text.strip()
        if not cleaned:
            return None
        if "://" in cleaned and not cleaned.startswith("http"):
            return None
        try:
            decoded = safe_base64_decode(cleaned)
            if "://" in decoded:
                return decoded
        except Exception:
            pass
        return None

    def import_from_text(self, text: str) -> List[ProxyNode]:
        """Import proxy nodes from raw text string (lines, base64 sub, markdown, Clash YAML/JSON)."""
        if not text or not isinstance(text, str):
            return []

        decoded = self._try_decode_base64(text)
        content_to_parse = decoded if decoded else text

        nodes: List[ProxyNode] = []

        # Parse Clash YAML or JSON if present
        if "proxies:" in content_to_parse or content_to_parse.strip().startswith(("{", "[")):
            try:
                data = yaml.safe_load(content_to_parse)
                if isinstance(data, dict) and "proxies" in data and isinstance(data["proxies"], list):
                    for proxy_item in data["proxies"]:
                        uri = clash_proxy_to_uri(proxy_item)
                        if uri:
                            node = UniversalParser.parse_uri(uri)
                            if node:
                                nodes.append(node)
                elif isinstance(data, list):
                    for proxy_item in data:
                        uri = clash_proxy_to_uri(proxy_item)
                        if uri:
                            node = UniversalParser.parse_uri(uri)
                            if node:
                                nodes.append(node)
            except Exception:
                pass

        # Regex extract all proxy URIs
        uri_pattern = re.compile(
            r'(?:vless|vmess|trojan|ss|shadowsocks|tuic|hysteria2|hysteria|hy2)://[^\s\`"\'<>\n]+',
            re.IGNORECASE,
        )
        for match in uri_pattern.finditer(content_to_parse):
            raw_uri = match.group(0).strip()
            node = UniversalParser.parse_uri(raw_uri)
            if node:
                nodes.append(node)

        # Fallback: try decoding individual lines if no nodes found and text wasn't globally decoded
        if not nodes and not decoded:
            for line in content_to_parse.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d_line = safe_base64_decode(line)
                    for match in uri_pattern.finditer(d_line):
                        raw_uri = match.group(0).strip()
                        node = UniversalParser.parse_uri(raw_uri)
                        if node:
                            nodes.append(node)
                except Exception:
                    pass

        return self.deduplicate(nodes)

    def import_from_file(self, file_path: str) -> List[ProxyNode]:
        """Import proxy nodes from local file (.txt, .json, .yaml, .yml)."""
        if not os.path.isfile(file_path):
            return []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return self.import_from_text(content)
        except Exception:
            return []

    async def fetch_from_source(
        self, source_dict: dict, session: Optional[aiohttp.ClientSession] = None
    ) -> List[ProxyNode]:
        """Asynchronously fetch proxies from a single source endpoint dictionary."""
        url = source_dict.get("url")
        if not url:
            return []

        close_session = False
        if session is None:
            session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            close_session = True

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return self.import_from_text(text)
                return []
        except Exception:
            return []
        finally:
            if close_session:
                await session.close()

    async def fetch_all_sources(
        self, sources_list: list, session: Optional[aiohttp.ClientSession] = None
    ) -> List[ProxyNode]:
        """Asynchronously fetch proxies across all sources in list."""
        if not sources_list:
            return []

        close_session = False
        if session is None:
            session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            close_session = True

        try:
            tasks = [self.fetch_from_source(src, session) for src in sources_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_nodes: List[ProxyNode] = []
            for res in results:
                if isinstance(res, list):
                    all_nodes.extend(res)

            return self.deduplicate(all_nodes)
        finally:
            if close_session:
                await session.close()

    async def fetch_from_sources(
        self, sources_list: list, session: Optional[aiohttp.ClientSession] = None
    ) -> List[ProxyNode]:
        """Alias for fetch_all_sources."""
        return await self.fetch_all_sources(sources_list, session)
