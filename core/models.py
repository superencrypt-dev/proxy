import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

@dataclass
class ProxyNode:
    id: str
    protocol: str
    name: str
    server: str
    port: int
    raw_uri: str
    config: Dict[str, Any]
    country_code: str = "XX"
    country_name: str = "Unknown"
    latency: int = -1
    is_alive: bool = False
    last_checked: str = ""

    @staticmethod
    def generate_id(protocol: str, server: str, port: int, creds: str = "", extra: str = "") -> str:
        raw = f"{protocol.lower()}:{server.lower()}:{port}:{creds}:{extra}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxyNode":
        return cls(**data)
