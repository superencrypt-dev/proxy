# Universal Proxy Scraper, Health Checker & Management TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun aplikasi TUI Python yang mengumpulkan proxy (vmess, vless, trojan, ss, tuic, hysteria 1 & 2), memvalidasi kelayakan koneksi riil via sing-box HTTP 204, membuang proxy mati, mengelompokkan metadata GeoIP, mengekspor ke berbagai format klien, dan menyediakan local proxy runner dengan antarmuka teks bersih (tanpa emoji).

**Architecture:** Arsitektur modular Micro-Core dengan parser terisolasi per protokol, asynchronous worker pool untuk pengujian koneksi riil menggunakan sing-box micro instances, GeoIP enricher, multi-format exporter, local runner daemon, dan antarmuka TUI interaktif (Questionary + Rich).

**Tech Stack:** Python 3.10+, asyncio, aiohttp, rich, questionary, PyYAML, sing-box core binary.

**Spec:** `docs/superpowers/specs/2026-08-14-proxy-scraper-checker-tui-design.md`

## Global Constraints

- Python 3.10+ compatibility.
- Strictly clean text & ASCII formatting: **NO EMOJIS** in menus, banners, tables, filenames, or node tags (use ISO country codes e.g. `[ID]`, `[SG]`, `[US]`).
- Supported protocols: `vmess`, `vless`, `trojan`, `shadowsocks`, `tuic`, `hysteria`, `hysteria2`.
- Real handshake connection check via sing-box micro-instances with HTTP 204 verification endpoint.
- Dead proxy removal: Any node failing check is excluded from `proxies_active.json`.

---

### Task 1: Project Scaffolding & Configuration Setup

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `data/sources.json`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: Configuration schema in `config.json` and default curated public scrapers in `data/sources.json`.

- [ ] **Step 1: Write requirements.txt**

```text
aiohttp>=3.9.0
rich>=13.7.0
questionary>=2.0.1
pyyaml>=6.0.1
requests>=2.31.0
pytest>=7.4.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Write config.json**

```json
{
  "concurrency": 30,
  "timeout": 5000,
  "test_url": "http://cp.cloudflare.com/generate_204",
  "backup_test_url": "https://www.gstatic.com/generate_204",
  "local_socks_port": 1080,
  "local_http_port": 1081,
  "auto_update_interval_minutes": 60,
  "data_dir": "data",
  "exports_dir": "data/exports"
}
```

- [ ] **Step 3: Write data/sources.json**

```json
{
  "sources": [
    {
      "name": "Free-V2Ray-All",
      "url": "https://raw.githubusercontent.com/freefq/free/master/v2",
      "type": "base64"
    },
    {
      "name": "NodeFree-Daily",
      "url": "https://raw.githubusercontent.com/v2ray-links/v2ray-free/master/README.md",
      "type": "raw_extract"
    },
    {
      "name": "Epodonios-Aggregator",
      "url": "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
      "type": "raw_lines"
    },
    {
      "name": "Barry-Clash-Sub",
      "url": "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/All_Configs_Sub.txt",
      "type": "raw_lines"
    }
  ]
}
```

- [ ] **Step 4: Install dependencies in python virtual environment or environment**

Run: `pip install -r requirements.txt`
Expected: Dependencies installed successfully.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.json data/sources.json
git commit -m "chore: setup project dependencies and initial configuration"
```

---

### Task 2: Data Models & Sing-box Binary Manager

**Files:**
- Create: `core/models.py`
- Create: `core/binary_manager.py`
- Create: `tests/test_binary_manager.py`

**Interfaces:**
- Produces: `ProxyNode`, `CheckResult`, `BinaryManager.ensure_singbox()` returning executable binary path.

- [ ] **Step 1: Write test for BinaryManager and ProxyNode**

`tests/test_binary_manager.py`:
```python
import os
import pytest
from core.models import ProxyNode
from core.binary_manager import BinaryManager

def test_proxy_node_creation():
    node = ProxyNode(
        id="test-123",
        protocol="vless",
        name="[SG] VLESS-Reality - 45ms",
        server="1.1.1.1",
        port=443,
        raw_uri="vless://test@1.1.1.1:443",
        config={"type": "vless", "server": "1.1.1.1", "server_port": 443}
    )
    assert node.id == "test-123"
    assert node.protocol == "vless"
    assert node.is_alive is False
    assert node.to_dict()["name"] == "[SG] VLESS-Reality - 45ms"

def test_binary_manager_system_arch():
    manager = BinaryManager(bin_dir="data/bin")
    arch = manager.detect_arch()
    assert "linux" in arch
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_binary_manager.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'core')

- [ ] **Step 3: Implement core/models.py and core/binary_manager.py**

`core/models.py`:
```python
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
```

`core/binary_manager.py`:
```python
import os
import sys
import platform
import stat
import tarfile
import zipfile
import requests
from typing import Optional

class BinaryManager:
    SINGBOX_VERSION = "1.9.0"

    def __init__(self, bin_dir: str = "data/bin"):
        self.bin_dir = bin_dir
        os.makedirs(self.bin_dir, exist_ok=True)
        self.bin_path = os.path.join(self.bin_dir, "sing-box")

    def detect_arch(self) -> str:
        machine = platform.machine().lower()
        system = platform.system().lower()
        if system != "linux":
            system = "linux"
        
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        elif "armv7" in machine or "armv6" in machine:
            arch = "armv7"
        else:
            arch = "amd64"
        return f"{system}-{arch}"

    def is_available(self) -> bool:
        return os.path.isfile(self.bin_path) and os.access(self.bin_path, os.X_OK)

    def ensure_singbox(self) -> str:
        if self.is_available():
            return self.bin_path

        arch = self.detect_arch()
        url = f"https://github.com/SagerNet/sing-box/releases/download/v{self.SINGBOX_VERSION}/sing-box-{self.SINGBOX_VERSION}-{arch}.tar.gz"
        archive_path = os.path.join(self.bin_dir, "sing-box.tar.gz")

        print(f"[Core] Downloading sing-box binary ({arch}) v{self.SINGBOX_VERSION}...")
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()

        with open(archive_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/sing-box") or member.name == "sing-box":
                    member.name = os.path.basename(member.name)
                    tar.extract(member, path=self.bin_dir)
                    break

        if os.path.exists(archive_path):
            os.remove(archive_path)

        if os.path.exists(self.bin_path):
            os.chmod(self.bin_path, os.stat(self.bin_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return self.bin_path

        raise FileNotFoundError("Gagal mengekstrak binary sing-box")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_binary_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/binary_manager.py tests/test_binary_manager.py
git commit -m "feat: add proxy data models and sing-box binary manager"
```

---

### Task 3: Protocol Parsers Suite

**Files:**
- Create: `core/parsers/base.py`
- Create: `core/parsers/vmess.py`
- Create: `core/parsers/vless.py`
- Create: `core/parsers/trojan.py`
- Create: `core/parsers/shadowsocks.py`
- Create: `core/parsers/tuic.py`
- Create: `core/parsers/hysteria.py`
- Create: `core/parsers/__init__.py`
- Create: `tests/test_parsers.py`

**Interfaces:**
- Produces: `UniversalParser.parse_uri(uri: str) -> Optional[ProxyNode]`

- [ ] **Step 1: Write test for all protocol parsers**

`tests/test_parsers.py`:
```python
import pytest
from core.parsers import UniversalParser

def test_parse_vless_reality():
    uri = "vless://uuid-1234@104.16.1.1:443?type=tcp&security=reality&pbk=publickey123&sni=zoom.us&fp=chrome#Singapore-Node"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "vless"
    assert node.server == "104.16.1.1"
    assert node.port == 443
    assert node.config["tls"]["reality"]["public_key"] == "publickey123"

def test_parse_trojan():
    uri = "trojan://password123@trojan.example.com:443?security=tls&sni=trojan.example.com#Trojan-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "trojan"
    assert node.server == "trojan.example.com"
    assert node.config["password"] == "password123"

def test_parse_shadowsocks():
    uri = "ss://YWVzLTEyOC1nY206cGFzc3dvcmQxMjM=@1.2.3.4:8388#SS-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "shadowsocks"
    assert node.server == "1.2.3.4"
    assert node.port == 8388
    assert node.config["method"] == "aes-128-gcm"

def test_parse_hysteria2():
    uri = "hysteria2://auth123@hy2.example.com:8443?sni=hy2.example.com&insecure=1#Hy2-Test"
    node = UniversalParser.parse_uri(uri)
    assert node is not None
    assert node.protocol == "hysteria2"
    assert node.server == "hy2.example.com"
    assert node.config["auth"] == "auth123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parsers.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'core.parsers')

- [ ] **Step 3: Implement core/parsers/base.py, all protocol modules, and UniversalParser**

Implement base parser and concrete parsers for `vmess`, `vless`, `trojan`, `shadowsocks`, `tuic`, `hysteria` (1 & 2), outputting exact sing-box 1.9+ JSON outbound structures.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parsers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/ tests/test_parsers.py
git commit -m "feat: implement universal protocol parsers for vmess, vless, trojan, ss, tuic, hysteria"
```

---

### Task 4: Proxy Collector & Smart Deduplication

**Files:**
- Create: `core/collector.py`
- Create: `tests/test_collector.py`

**Interfaces:**
- Produces: `ProxyCollector.fetch_from_sources(sources_list) -> List[ProxyNode]`, `ProxyCollector.import_from_text(text) -> List[ProxyNode]`, `ProxyCollector.deduplicate(nodes) -> List[ProxyNode]`.

- [ ] **Step 1: Write test for ProxyCollector**

`tests/test_collector.py`:
```python
import pytest
from core.collector import ProxyCollector

def test_import_from_raw_text():
    raw_content = """
    vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1
    vless://uuid-1@1.1.1.1:443?type=tcp&security=none#Node1-Duplicate
    trojan://pass@2.2.2.2:443#Node2
    invalid_line_here
    """
    collector = ProxyCollector()
    nodes = collector.import_from_text(raw_content)
    assert len(nodes) == 2  # Deduplicated from 3 valid lines (1 duplicate removed)
    assert nodes[0].protocol == "vless"
    assert nodes[1].protocol == "trojan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_collector.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'core.collector')

- [ ] **Step 3: Implement core/collector.py**

Implement `ProxyCollector` with:
- Asynchronous fetching from HTTP/HTTPS source endpoints (handling raw lines, base64 subscriptions, markdown code block extracts).
- File importer (reading from `.txt`, `.yaml`, `.json`).
- Text stream importer.
- Deduplication based on `ProxyNode.id` hash.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_collector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/collector.py tests/test_collector.py
git commit -m "feat: implement proxy collector with smart deduplication"
```

---

### Task 5: GeoIP Lookup & Clean Standardization (No Emoji)

**Files:**
- Create: `core/geoip.py`
- Create: `tests/test_geoip.py`

**Interfaces:**
- Produces: `GeoIPResolver.resolve_country(ip_or_host: str) -> (country_code, country_name)`, `GeoIPResolver.standardize_name(node: ProxyNode) -> str`.

- [ ] **Step 1: Write test for GeoIPResolver**

`tests/test_geoip.py`:
```python
import pytest
from core.models import ProxyNode
from core.geoip import GeoIPResolver

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_geoip.py -v`
Expected: FAIL

- [ ] **Step 3: Implement core/geoip.py**

Implement fast async GeoIP lookup with in-memory caching and fallback offline IP range table + clean name standardizer (`[{CC}] {PROTOCOL} - {SERVER} - {LATENCY}ms`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_geoip.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/geoip.py tests/test_geoip.py
git commit -m "feat: implement geoip lookup and clean text standardization"
```

---

### Task 6: Concurrent Sing-box Health Checker Engine

**Files:**
- Create: `core/checker.py`
- Create: `tests/test_checker.py`

**Interfaces:**
- Produces: `ProxyChecker.check_nodes(nodes: List[ProxyNode], on_progress=None) -> (alive_nodes, dead_nodes)`

- [ ] **Step 1: Write test for ProxyChecker**

`tests/test_checker.py`:
```python
import pytest
from core.models import ProxyNode
from core.checker import ProxyChecker

@pytest.mark.asyncio
async def test_generate_singbox_temp_config():
    checker = ProxyChecker(concurrency=5, timeout=3000)
    node = ProxyNode(
        id="test",
        protocol="trojan",
        name="test",
        server="1.1.1.1",
        port=443,
        raw_uri="",
        config={"type": "trojan", "tag": "proxy-out", "server": "1.1.1.1", "server_port": 443, "password": "p"}
    )
    cfg = checker._build_temp_config(node, inbound_port=25000)
    assert cfg["inbounds"][0]["listen_port"] == 25000
    assert cfg["outbounds"][0]["tag"] == "proxy-out"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_checker.py -v`
Expected: FAIL

- [ ] **Step 3: Implement core/checker.py**

Implement `ProxyChecker` using:
- `asyncio.Semaphore` for concurrency limit.
- Dynamic temporary JSON config per node with random local port.
- Subprocess execution of `sing-box run -c <temp_config>`.
- Real HTTP GET request through local SOCKS5 proxy to `http://cp.cloudflare.com/generate_204`.
- Exact latency measurement and clean process termination / file cleanup.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_checker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/checker.py tests/test_checker.py
git commit -m "feat: implement concurrent health checker using sing-box core"
```

---

### Task 7: Multi-Format Exporters

**Files:**
- Create: `core/exporter.py`
- Create: `tests/test_exporter.py`

**Interfaces:**
- Produces: `ProxyExporter.export_raw(nodes, path)`, `ProxyExporter.export_base64(nodes, path)`, `ProxyExporter.export_clash(nodes, path)`, `ProxyExporter.export_singbox(nodes, path)`.

- [ ] **Step 1: Write test for ProxyExporter**

`tests/test_exporter.py`:
```python
import os
import yaml
import json
import pytest
from core.models import ProxyNode
from core.exporter import ProxyExporter

def test_export_clash_yaml(tmp_path):
    out_file = tmp_path / "clash.yaml"
    node = ProxyNode(
        id="1",
        protocol="trojan",
        name="[SG] Trojan-Fast - 50ms",
        server="1.1.1.1",
        port=443,
        raw_uri="trojan://pass@1.1.1.1:443",
        config={"type": "trojan", "server": "1.1.1.1", "server_port": 443, "password": "pass"},
        country_code="SG",
        latency=50,
        is_alive=True
    )
    exporter = ProxyExporter()
    exporter.export_clash([node], str(out_file))
    assert os.path.exists(str(out_file))
    with open(str(out_file)) as f:
        data = yaml.safe_load(f)
    assert "proxies" in data
    assert len(data["proxies"]) == 1
    assert data["proxies"][0]["name"] == "[SG] Trojan-Fast - 50ms"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_exporter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement core/exporter.py**

Implement `ProxyExporter` supporting raw links, base64 subscriptions, Clash Meta/Mihomo YAML with proxy groups, and Sing-box JSON format with outbounds and URLTest groups.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_exporter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/exporter.py tests/test_exporter.py
git commit -m "feat: implement multi-format proxy exporters"
```

---

### Task 8: Local Proxy Runner & Auto-Scheduler

**Files:**
- Create: `core/runner.py`
- Create: `core/scheduler.py`
- Create: `tests/test_runner_scheduler.py`

**Interfaces:**
- Produces: `LocalProxyRunner.start(node, socks_port, http_port)`, `LocalProxyRunner.stop()`, `AutoScheduler.start(interval_minutes, job_func)`.

- [ ] **Step 1: Write test for LocalProxyRunner config generation**

`tests/test_runner_scheduler.py`:
```python
import pytest
from core.models import ProxyNode
from core.runner import LocalProxyRunner

def test_runner_config_generation():
    runner = LocalProxyRunner(bin_path="sing-box")
    node = ProxyNode(
        id="1",
        protocol="trojan",
        name="[ID] Trojan - 40ms",
        server="1.1.1.1",
        port=443,
        raw_uri="trojan://pass@1.1.1.1:443",
        config={"type": "trojan", "tag": "proxy-out", "server": "1.1.1.1", "server_port": 443, "password": "pass"}
    )
    cfg = runner._generate_runner_config(node, socks_port=1080, http_port=1081)
    assert len(cfg["inbounds"]) == 2
    assert cfg["inbounds"][0]["listen_port"] == 1080
    assert cfg["inbounds"][1]["listen_port"] == 1081
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: Implement core/runner.py and core/scheduler.py**

Implement daemon management for running a selected proxy node locally, checking process liveness, and periodic background scheduler.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runner_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/runner.py core/scheduler.py tests/test_runner_scheduler.py
git commit -m "feat: implement local proxy runner and background auto-scheduler"
```

---

### Task 9: Clean TUI Views & Themes (Strictly No Emoji)

**Files:**
- Create: `tui/themes.py`
- Create: `tui/views.py`
- Create: `tests/test_tui_views.py`

**Interfaces:**
- Produces: `TUIViews.render_banner()`, `TUIViews.render_proxy_table(nodes)`, `TUIViews.render_status_panel()`, `TUIViews.render_summary(alive_count, dead_count)`.

- [ ] **Step 1: Write test for TUI Views (Verifying zero emojis in output)**

`tests/test_tui_views.py`:
```python
import re
from tui.themes import ASCII_BANNER
from tui.views import TUIViews
from core.models import ProxyNode

def test_banner_and_views_have_no_emojis():
    # Regex matching unicode emoji ranges
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251]+",
        flags=re.UNICODE
    )
    assert not emoji_pattern.search(ASCII_BANNER)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui_views.py -v`
Expected: FAIL

- [ ] **Step 3: Implement tui/themes.py and tui/views.py**

Implement Rich-based view components using clean ASCII borders, clean colors (cyan, green, yellow, red), tables, and summary boxes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tui_views.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tui/themes.py tui/views.py tests/test_tui_views.py
git commit -m "feat: implement clean text TUI views and themes without emojis"
```

---

### Task 10: Interactive TUI Menu & CLI Entry Point

**Files:**
- Create: `tui/menu.py`
- Create: `main.py`
- Create: `tests/test_integration.py`

**Interfaces:**
- Produces: Interactive CLI loop and seamless sub-menu navigation.

- [ ] **Step 1: Write test for integration flow**

`tests/test_integration.py`:
```python
import pytest
from core.collector import ProxyCollector
from core.models import ProxyNode
from core.exporter import ProxyExporter

def test_full_pipeline_mock(tmp_path):
    collector = ProxyCollector()
    raw_text = "trojan://testpass@1.1.1.1:443#Singapore-Test\nvless://uuid@2.2.2.2:443?security=none#Indo-Test"
    nodes = collector.import_from_text(raw_text)
    assert len(nodes) == 2

    # Mock health check result
    nodes[0].is_alive = True
    nodes[0].latency = 45
    nodes[0].country_code = "SG"
    nodes[0].name = "[SG] TROJAN - 1.1.1.1 - 45ms"

    nodes[1].is_alive = False  # Dead

    alive_nodes = [n for n in nodes if n.is_alive]
    assert len(alive_nodes) == 1

    out_file = tmp_path / "clean_sub.txt"
    exporter = ProxyExporter()
    exporter.export_raw(alive_nodes, str(out_file))
    assert out_file.read_text().strip().startswith("trojan://")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Implement tui/menu.py and main.py**

Connect all modules into an interactive loop with Questionary:
1. Scrape & Auto-Check Semua Sumber
2. Kumpulkan Proxy (Scrape Publik / Input Custom URL / File)
3. Jalankan Health Check & Filter Proxy Aktif
4. Lihat Daftar Proxy Aktif
5. Ekspor Proxy (Raw, Base64, Clash, Sing-box)
6. Jalankan Local Proxy Server
7. Auto-Scheduler
8. Pengaturan & Kelola Sumber
0. Keluar

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All unit and integration tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/menu.py main.py tests/test_integration.py
git commit -m "feat: implement interactive TUI menu and main entrypoint"
```
