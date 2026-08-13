import re
import socket
import ipaddress
import asyncio
from typing import Tuple, Dict, Optional
import requests
import aiohttp
from core.models import ProxyNode

_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"  # symbols & pictographs
    r"\U0001F680-\U0001F6FF"  # transport & map symbols
    r"\U0001F1E6-\U0001F1FF"  # flags (iOS/Android regional indicator symbols)
    r"\U00002600-\U000027BF"  # misc symbols & dingbats
    r"\U0001FA00-\U0001FAFF"  # extended symbols
    r"\uFE00-\uFE0F"          # variation selectors
    r"\u200D"                # zero width joiner
    r"]+",
    flags=re.UNICODE
)

def strip_emojis(text: str) -> str:
    """Removes emoji characters, flags, and unicode symbols from text."""
    if not text:
        return ""
    clean = _EMOJI_PATTERN.sub("", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

OFFLINE_IP_TABLE: Dict[str, Tuple[str, str]] = {
    "1.1.1.1": ("US", "United States"),
    "1.0.0.1": ("US", "United States"),
    "8.8.8.8": ("US", "United States"),
    "8.8.4.4": ("US", "United States"),
    "9.9.9.9": ("US", "United States"),
    "149.112.112.112": ("US", "United States"),
    "208.67.222.222": ("US", "United States"),
    "208.67.220.220": ("US", "United States"),
}

class GeoIPResolver:
    """GeoIP Resolver with local memory cache, offline fallbacks, and fast API lookup."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[str, str]] = {}

    def _is_private_or_local(self, ip_str: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            return (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
            )
        except ValueError:
            return False

    def _resolve_host_to_ip(self, host: str) -> Optional[str]:
        # Check if already a valid IP address
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass

        # Try resolving hostname via DNS
        try:
            return socket.gethostbyname(host)
        except (socket.gaierror, socket.herror, socket.timeout, Exception):
            return None

    def resolve_country(self, ip_or_host: str) -> Tuple[str, str]:
        """Resolves a host/IP to a (country_code, country_name) tuple synchronously."""
        if not ip_or_host:
            return ("XX", "Unknown")

        target = ip_or_host.strip()

        # 1. Check memory cache
        if target in self._cache:
            return self._cache[target]

        # 2. Check hostname resolution
        ip_addr = self._resolve_host_to_ip(target)
        if not ip_addr:
            result = ("XX", "Unknown")
            self._cache[target] = result
            return result

        if ip_addr != target and ip_addr in self._cache:
            result = self._cache[ip_addr]
            self._cache[target] = result
            return result

        # 3. Check private / local IP
        if self._is_private_or_local(ip_addr):
            result = ("LOCAL", "Local Network")
            self._cache[target] = result
            self._cache[ip_addr] = result
            return result

        # 4. Check offline lookup table
        if ip_addr in OFFLINE_IP_TABLE:
            result = OFFLINE_IP_TABLE[ip_addr]
            self._cache[target] = result
            self._cache[ip_addr] = result
            return result

        # 5. Online GeoIP API lookup (ip-api.com with timeout)
        try:
            url = f"http://ip-api.com/json/{ip_addr}?fields=status,countryCode,country"
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    cc = strip_emojis(data.get("countryCode", "XX")).upper() or "XX"
                    name = strip_emojis(data.get("country", "Unknown")) or "Unknown"
                    result = (cc, name)
                    self._cache[target] = result
                    self._cache[ip_addr] = result
                    return result
        except Exception:
            pass

        # Fallback if API fails or times out
        result = ("XX", "Unknown")
        self._cache[target] = result
        self._cache[ip_addr] = result
        return result

    async def resolve_country_async(self, ip_or_host: str) -> Tuple[str, str]:
        """Resolves a host/IP to a (country_code, country_name) tuple asynchronously."""
        if not ip_or_host:
            return ("XX", "Unknown")

        target = ip_or_host.strip()

        # 1. Check memory cache
        if target in self._cache:
            return self._cache[target]

        # 2. Check hostname resolution in thread executor
        ip_addr = await asyncio.to_thread(self._resolve_host_to_ip, target)
        if not ip_addr:
            result = ("XX", "Unknown")
            self._cache[target] = result
            return result

        if ip_addr != target and ip_addr in self._cache:
            result = self._cache[ip_addr]
            self._cache[target] = result
            return result

        # 3. Check private / local IP
        if self._is_private_or_local(ip_addr):
            result = ("LOCAL", "Local Network")
            self._cache[target] = result
            self._cache[ip_addr] = result
            return result

        # 4. Check offline lookup table
        if ip_addr in OFFLINE_IP_TABLE:
            result = OFFLINE_IP_TABLE[ip_addr]
            self._cache[target] = result
            self._cache[ip_addr] = result
            return result

        # 5. Online GeoIP API lookup via aiohttp
        try:
            url = f"http://ip-api.com/json/{ip_addr}?fields=status,countryCode,country"
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "success":
                            cc = strip_emojis(data.get("countryCode", "XX")).upper() or "XX"
                            name = strip_emojis(data.get("country", "Unknown")) or "Unknown"
                            result = (cc, name)
                            self._cache[target] = result
                            self._cache[ip_addr] = result
                            return result
        except Exception:
            pass

        result = ("XX", "Unknown")
        self._cache[target] = result
        self._cache[ip_addr] = result
        return result

    def standardize_name(self, node: ProxyNode) -> str:
        """Formats proxy node name into a clean, standardized format with NO EMOJIS.
        
        Format:
          - Tested (latency > -1): [{COUNTRY_CODE}] {PROTOCOL} - {TAG} - {LATENCY}ms
          - Untested (latency == -1): [{COUNTRY_CODE}] {PROTOCOL} - {TAG}
        """
        # Determine country code
        raw_cc = strip_emojis(node.country_code).upper()
        if not raw_cc or raw_cc == "XX":
            # Attempt to resolve from server if country_code is not set
            cc_res, name_res = self.resolve_country(node.server)
            raw_cc = cc_res.upper()
            if node.country_name == "Unknown" and name_res != "Unknown":
                node.country_name = name_res
        
        node.country_code = raw_cc
        cc_tag = f"[{raw_cc}]"

        # Protocol upper
        protocol_str = (node.protocol or "UNKNOWN").upper()

        # Tag/Server name clean
        clean_name = strip_emojis(node.name)
        if not clean_name or clean_name == node.raw_uri:
            tag = node.server
        else:
            tag = clean_name

        if node.latency > -1:
            return f"{cc_tag} {protocol_str} - {tag} - {node.latency}ms"
        else:
            return f"{cc_tag} {protocol_str} - {tag}"
