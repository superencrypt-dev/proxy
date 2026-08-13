from typing import Optional
from core.models import ProxyNode
from core.parsers.vmess import VMessParser
from core.parsers.vless import VLessParser
from core.parsers.trojan import TrojanParser
from core.parsers.shadowsocks import ShadowsocksParser
from core.parsers.tuic import TUICParser
from core.parsers.hysteria import HysteriaParser


class UniversalParser:
    PARSERS = {
        "vmess": VMessParser,
        "vless": VLessParser,
        "trojan": TrojanParser,
        "ss": ShadowsocksParser,
        "shadowsocks": ShadowsocksParser,
        "tuic": TUICParser,
        "hysteria": HysteriaParser,
        "hysteria2": HysteriaParser,
        "hy2": HysteriaParser,
    }

    @classmethod
    def parse_uri(cls, uri: str) -> Optional[ProxyNode]:
        if not uri or not isinstance(uri, str):
            return None

        uri = uri.strip()
        if "://" not in uri:
            return None

        scheme = uri.split("://", 1)[0].lower()
        parser_cls = cls.PARSERS.get(scheme)
        if not parser_cls:
            return None

        try:
            return parser_cls.parse(uri)
        except Exception:
            return None


__all__ = [
    "UniversalParser",
    "VMessParser",
    "VLessParser",
    "TrojanParser",
    "ShadowsocksParser",
    "TUICParser",
    "HysteriaParser",
]
