import base64
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from core.models import ProxyNode


def safe_base64_decode(data: str) -> str:
    """Safely decode base64 string with padding auto-fix and URL-safe replacements."""
    data = data.strip()
    data = data.replace("-", "+").replace("_", "/")
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def parse_server_port(host_str: str, default_port: int = 443) -> Tuple[str, int]:
    """Parses host:port string handling IPv6 brackets if any."""
    if not host_str:
        return "", default_port

    if "]" in host_str:
        parts = host_str.split("]")
        server = parts[0].lstrip("[")
        port = default_port
        if len(parts) > 1 and parts[1].startswith(":"):
            try:
                port = int(parts[1][1:])
            except ValueError:
                pass
        return server, port

    if ":" in host_str:
        parts = host_str.rsplit(":", 1)
        server = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = default_port
        return server, port

    return host_str, default_port


def build_transport_config(
    net: str, path: str = "", host: str = "", type_param: str = ""
) -> Optional[Dict[str, Any]]:
    """Build sing-box 1.9+ transport config dict based on transport type and parameters."""
    net = (net or type_param or "").lower().strip()
    if not net or net == "tcp":
        if type_param and type_param.lower() in ("http", "h2"):
            cfg: Dict[str, Any] = {"type": "http"}
            if path:
                cfg["path"] = path
            if host:
                cfg["host"] = [host]
            return cfg
        return None

    if net == "ws":
        ws_cfg: Dict[str, Any] = {"type": "ws"}
        if path:
            ws_cfg["path"] = path
        if host:
            ws_cfg["headers"] = {"Host": host}
        return ws_cfg

    if net == "grpc":
        grpc_cfg: Dict[str, Any] = {"type": "grpc"}
        if path:
            grpc_cfg["service_name"] = path
        return grpc_cfg

    if net in ("http", "h2"):
        http_cfg: Dict[str, Any] = {"type": "http"}
        if path:
            http_cfg["path"] = path
        if host:
            http_cfg["host"] = [host]
        return http_cfg

    if net == "quic":
        return {"type": "quic"}

    return None


def build_tls_config(
    security: str = "",
    sni: str = "",
    fp: str = "",
    alpn: str = "",
    insecure: str = "",
    pbk: str = "",
    sid: str = "",
    spx: str = "",
    default_server: str = "",
) -> Optional[Dict[str, Any]]:
    """Build sing-box 1.9+ tls config dict."""
    sec = (security or "").lower().strip()
    is_tls = sec in ("tls", "reality") or bool(sni) or bool(pbk)

    if not is_tls and not sec:
        return None

    if sec == "none":
        return None

    server_name = sni if sni else default_server
    is_insecure = insecure.lower() in ("1", "true", "yes")

    tls_cfg: Dict[str, Any] = {
        "enabled": True,
    }
    if server_name:
        tls_cfg["server_name"] = server_name
    if is_insecure:
        tls_cfg["insecure"] = True

    if fp:
        tls_cfg["utls"] = {
            "enabled": True,
            "fingerprint": fp,
        }

    if alpn:
        alpn_list = [a.strip() for a in alpn.split(",") if a.strip()]
        if alpn_list:
            tls_cfg["alpn"] = alpn_list

    if sec == "reality" or pbk:
        reality_cfg: Dict[str, Any] = {"enabled": True}
        if pbk:
            reality_cfg["public_key"] = pbk
        if sid:
            reality_cfg["short_id"] = sid
        if spx:
            reality_cfg["spider_x"] = spx
        tls_cfg["reality"] = reality_cfg

    return tls_cfg


class BaseParser:
    """Base class for all protocol parsers."""

    @classmethod
    def parse(cls, uri: str) -> Optional[ProxyNode]:
        raise NotImplementedError
