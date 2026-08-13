import pytest
import re
from unittest.mock import patch, MagicMock
from core.models import ProxyNode
from core.geoip import GeoIPResolver

# Regex helper to test for emoji presence in strings
EMOJI_REGEX = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"  # symbols & pictographs
    r"\U0001F680-\U0001F6FF"  # transport & map symbols
    r"\U0001F1E6-\U0001F1FF"  # flags (iOS/Android regional indicator symbols)
    r"\U00002600-\U000027BF"  # misc symbols & dingbats
    r"\U0001FA00-\U0001FAFF"  # extended symbols
    r"]",
    flags=re.UNICODE
)

def test_standardize_name_clean_text():
    resolver = GeoIPResolver()
    node = ProxyNode(
        id="abc",
        protocol="vless",
        name="Random-Old-Name",
        server="1.1.1.1",
        port=443,
        raw_uri="",
        config={},
        country_code="ID",
        country_name="Indonesia",
        latency=75
    )
    std_name = resolver.standardize_name(node)
    assert "[ID]" in std_name
    assert "VLESS" in std_name
    assert "75ms" in std_name
    assert "🇮🇩" not in std_name  # Strictly no emojis
    assert not EMOJI_REGEX.search(std_name)

def test_standardize_name_untested_no_latency():
    resolver = GeoIPResolver()
    node = ProxyNode(
        id="def",
        protocol="hysteria2",
        name="SG-Server-01",
        server="1.0.0.1",
        port=443,
        raw_uri="",
        config={},
        country_code="SG",
        country_name="Singapore",
        latency=-1
    )
    std_name = resolver.standardize_name(node)
    assert "[SG]" in std_name
    assert "HYSTERIA2" in std_name or "HY2" in std_name
    assert "ms" not in std_name
    assert not EMOJI_REGEX.search(std_name)

def test_standardize_name_emoji_stripping():
    resolver = GeoIPResolver()
    node = ProxyNode(
        id="ghi",
        protocol="trojan",
        name="🇮🇩 ID Super Fast Node 🚀⚡",
        server="8.8.8.8",
        port=443,
        raw_uri="",
        config={},
        country_code="🇮🇩",
        country_name="Indonesia 🇮🇩",
        latency=42
    )
    std_name = resolver.standardize_name(node)
    assert "🇮🇩" not in std_name
    assert "🚀" not in std_name
    assert "⚡" not in std_name
    assert not EMOJI_REGEX.search(std_name)
    assert "42ms" in std_name

def test_resolve_country_local_and_private_ip():
    resolver = GeoIPResolver()
    cc, name = resolver.resolve_country("127.0.0.1")
    assert cc == "LOCAL" or cc == "XX"
    assert "Local" in name or "Private" in name or "Unknown" in name
    assert not EMOJI_REGEX.search(cc) and not EMOJI_REGEX.search(name)

    cc2, name2 = resolver.resolve_country("192.168.1.100")
    assert cc2 == "LOCAL" or cc2 == "XX"
    assert not EMOJI_REGEX.search(cc2) and not EMOJI_REGEX.search(name2)

def test_resolve_country_offline_fallback():
    resolver = GeoIPResolver()
    cc, name = resolver.resolve_country("1.1.1.1")
    assert cc == "US"
    assert "United States" in name or "Cloudflare" in name
    assert not EMOJI_REGEX.search(cc) and not EMOJI_REGEX.search(name)

def test_resolve_country_cache():
    resolver = GeoIPResolver()
    # First call populates cache
    res1 = resolver.resolve_country("8.8.8.8")
    assert "8.8.8.8" in resolver._cache
    # Second call uses cache
    res2 = resolver.resolve_country("8.8.8.8")
    assert res1 == res2

def test_resolve_country_invalid_host():
    resolver = GeoIPResolver()
    cc, name = resolver.resolve_country("invalid.domain.that.does.not.exist.example.invalid")
    assert cc == "XX"
    assert name == "Unknown"

@patch("requests.get")
def test_resolve_country_online_api_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "countryCode": "JP",
        "country": "Japan"
    }
    mock_get.return_value = mock_resp

    resolver = GeoIPResolver()
    cc, name = resolver.resolve_country("93.184.216.34")
    assert cc == "JP"
    assert name == "Japan"
    assert "93.184.216.34" in resolver._cache

@patch("requests.get")
def test_resolve_country_online_api_failure(mock_get):
    mock_get.side_effect = Exception("Connection error")

    resolver = GeoIPResolver()
    cc, name = resolver.resolve_country("93.184.216.35")
    assert cc == "XX"
    assert name == "Unknown"

@pytest.mark.asyncio
async def test_resolve_country_async():
    resolver = GeoIPResolver()
    cc, name = await resolver.resolve_country_async("1.1.1.1")
    assert cc == "US"
    assert not EMOJI_REGEX.search(cc) and not EMOJI_REGEX.search(name)
