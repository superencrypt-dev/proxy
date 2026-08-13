"""Interactive TUI Menu Component for Proxy Scraper & Checker (Strictly No Emoji).
Refactored & Streamlined Architecture: Modular, DRY, Data-Safe, and Unified.
"""

import os
import sys
import json
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

from core.models import ProxyNode
from core.collector import ProxyCollector
from core.checker import ProxyChecker
from core.exporter import ProxyExporter
from core.binary_manager import BinaryManager
from core.runner import LocalProxyRunner
from core.scheduler import AutoScheduler
from tui.views import TUIViews


CONFIG_FILE = "config.json"
SOURCES_FILE = "data/sources.json"
ACTIVE_PROXIES_FILE = "data/proxies_active.json"
RAW_PROXIES_FILE = "data/proxies_raw.txt"
EXPORTS_DIR = "data/exports"


class TUIMenu:
    """Main interactive TUI Menu controller."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.views = TUIViews(self.console)
        self.runner = LocalProxyRunner()
        self.scheduler = AutoScheduler()
        self.exporter = ProxyExporter()
        self.collector = ProxyCollector()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure necessary data and exports directories exist."""
        os.makedirs("data", exist_ok=True)
        os.makedirs(EXPORTS_DIR, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json with fallback defaults."""
        defaults = {
            "concurrency": 30,
            "timeout": 5000,
            "test_url": "http://cp.cloudflare.com/generate_204",
            "backup_test_url": "https://www.gstatic.com/generate_204",
            "local_socks_port": 1080,
            "local_http_port": 1081,
            "auto_update_interval_minutes": 60,
            "data_dir": "data",
            "exports_dir": EXPORTS_DIR,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    defaults.update(cfg)
            except Exception:
                pass
        return defaults

    def _save_config(self, cfg: Dict[str, Any]) -> None:
        """Save configuration dictionary to config.json."""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal menyimpan config.json: {e}", style="red")

    def _load_sources(self) -> List[Dict[str, Any]]:
        """Load upstream sources list from data/sources.json."""
        if os.path.exists(SOURCES_FILE):
            try:
                with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "sources" in data:
                        return data["sources"]
                    elif isinstance(data, list):
                        return data
            except Exception:
                pass
        return [
            {
                "name": "Free-V2Ray-All",
                "url": "https://raw.githubusercontent.com/freefq/free/master/v2",
                "type": "base64",
            }
        ]

    def _save_sources(self, sources: List[Dict[str, Any]]) -> None:
        """Save upstream sources list to data/sources.json."""
        try:
            with open(SOURCES_FILE, "w", encoding="utf-8") as f:
                json.dump({"sources": sources}, f, indent=2)
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal menyimpan data/sources.json: {e}", style="red")

    def _load_active_proxies(self) -> List[ProxyNode]:
        """Load active nodes from data/proxies_active.json."""
        if os.path.exists(ACTIVE_PROXIES_FILE):
            try:
                with open(ACTIVE_PROXIES_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    if isinstance(items, list):
                        return [ProxyNode.from_dict(item) for item in items if isinstance(item, dict)]
            except Exception:
                pass
        return []

    def _save_active_proxies(self, nodes: List[ProxyNode]) -> None:
        """Save active nodes list to data/proxies_active.json."""
        try:
            items = [n.to_dict() for n in nodes]
            with open(ACTIVE_PROXIES_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal menyimpan active proxies: {e}", style="red")

    def _load_raw_proxies(self) -> List[ProxyNode]:
        """Load raw nodes from data/proxies_raw.txt."""
        if os.path.exists(RAW_PROXIES_FILE):
            return self.collector.import_from_file(RAW_PROXIES_FILE)
        return []

    def _save_raw_proxies(self, nodes: List[ProxyNode], merge_with_existing: bool = True) -> None:
        """Save raw nodes to data/proxies_raw.txt with safe deduplicated merge."""
        try:
            target_nodes = nodes
            if merge_with_existing and os.path.exists(RAW_PROXIES_FILE):
                existing = self._load_raw_proxies()
                target_nodes = self.collector.deduplicate(existing + nodes)
            else:
                target_nodes = self.collector.deduplicate(nodes)

            raw_uris = [n.raw_uri for n in target_nodes if n.raw_uri]
            with open(RAW_PROXIES_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(raw_uris) + "\n")
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal menyimpan raw proxies: {e}", style="red")

    # =========================================================================
    # CORE PIPELINE (DRY & UNIFIED HEALTH CHECKER)
    # =========================================================================

    def _run_health_check_pipeline(
        self,
        nodes: List[ProxyNode],
        is_interactive: bool = True,
        save_to_active: bool = True,
    ) -> Tuple[List[ProxyNode], List[ProxyNode]]:
        """Unified, reusable core health checker pipeline with progress reporting and saving."""
        if not nodes:
            if is_interactive:
                self.views.render_status_panel("INFO", "Tidak ada node proxy yang diberikan untuk dicek.", style="yellow")
            return [], []

        cfg = self._load_config()
        concurrency = int(cfg.get("concurrency", 30))
        timeout = int(cfg.get("timeout", 5000))
        test_url = cfg.get("test_url", "http://cp.cloudflare.com/generate_204")
        backup_test_url = cfg.get("backup_test_url", "https://www.gstatic.com/generate_204")

        # 1. Ensure sing-box binary is ready
        try:
            bm = BinaryManager()
            bin_path = bm.ensure_singbox()
        except Exception as e:
            if is_interactive:
                self.views.render_status_panel("ERROR", f"Gagal memverifikasi binary sing-box: {e}", style="red")
            return [], []

        checker = ProxyChecker(
            concurrency=concurrency,
            timeout=timeout,
            test_url=test_url,
            fallback_test_url=backup_test_url,
            binary_path=bin_path,
            enable_fast_ping=True,
        )

        start_time = time.time()
        alive_nodes: List[ProxyNode] = []
        dead_nodes: List[ProxyNode] = []

        if is_interactive:
            progress = self.views.create_progress_bar()
            with progress:
                task_id = progress.add_task(f"Memeriksa {len(nodes)} Proxy...", total=len(nodes))

                def on_progress(completed: int, total: int, node: ProxyNode):
                    progress.update(task_id, completed=completed)

                alive_nodes, dead_nodes = asyncio.run(checker.check_nodes(nodes, on_progress=on_progress))
        else:
            alive_nodes, dead_nodes = asyncio.run(checker.check_nodes(nodes, on_progress=None))

        duration = time.time() - start_time

        # Sort alive nodes by latency ascending (fastest first)
        alive_nodes.sort(key=lambda n: n.latency if n.latency > 0 else 999999)

        if save_to_active:
            self._save_active_proxies(alive_nodes)

        if is_interactive:
            self.views.render_summary(
                total=len(nodes),
                alive=len(alive_nodes),
                dead=len(dead_nodes),
                duration_sec=duration,
            )

        return alive_nodes, dead_nodes

    # =========================================================================
    # MENU 1: QUICK UPDATE (SAFE MERGE + CHECK ALL)
    # =========================================================================

    def handle_quick_update(self) -> List[ProxyNode]:
        """Scrape all upstream sources, safely merge with existing raw proxies, and run health check."""
        self.views.render_banner()
        self.console.print("[bold cyan][1/3] Menyiapkan environment & binary sing-box...[/bold cyan]")
        try:
            bm = BinaryManager()
            bm.ensure_singbox()
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal download binary sing-box: {e}", style="red")
            return []

        self.console.print("[bold cyan][2/3] Mengumpulkan proxy dari seluruh sumber upstream...[/bold cyan]")
        sources = self._load_sources()
        fresh_nodes = asyncio.run(self.collector.fetch_all_sources(sources))

        # Safe merge with existing raw proxies so manual imports are not lost
        existing_raw = self._load_raw_proxies()
        all_raw_nodes = self.collector.deduplicate(existing_raw + fresh_nodes)
        self._save_raw_proxies(all_raw_nodes, merge_with_existing=False)

        self.console.print(
            f"[green]Terkumpul {len(fresh_nodes)} node baru (Total database raw: {len(all_raw_nodes)} node unik).[/green]"
        )

        self.console.print(f"[bold cyan][3/3] Menjalankan health check ({len(all_raw_nodes)} nodes)...[/bold cyan]")
        alive_nodes, _ = self._run_health_check_pipeline(all_raw_nodes, is_interactive=True, save_to_active=True)
        return alive_nodes

    def handle_scrape_and_check_all(self) -> List[ProxyNode]:
        """Alias for handle_quick_update for backward compatibility."""
        return self.handle_quick_update()

    def handle_headless_update(self) -> List[ProxyNode]:
        """Silent update routine designed for background auto-scheduler and headless execution."""
        try:
            bm = BinaryManager()
            bm.ensure_singbox()
            sources = self._load_sources()
            fresh_nodes = asyncio.run(self.collector.fetch_all_sources(sources))
            existing_raw = self._load_raw_proxies()
            all_raw = self.collector.deduplicate(existing_raw + fresh_nodes)
            self._save_raw_proxies(all_raw, merge_with_existing=False)
            alive_nodes, _ = self._run_health_check_pipeline(all_raw, is_interactive=False, save_to_active=True)
            return alive_nodes
        except Exception:
            return []

    # =========================================================================
    # MENU 2: PROXY COLLECTOR & SOURCES HUB
    # =========================================================================

    def handle_collector_hub(self) -> None:
        """Unified hub for collecting proxies (upstream, URL, file, paste) and managing upstream sources."""
        while True:
            self.views.render_banner()
            sources = self._load_sources()
            raw_nodes = self._load_raw_proxies()

            self.console.print(
                f"[dim]Status Collector: {len(sources)} Sumber Upstream Terdaftar | {len(raw_nodes)} Raw Proxies di Cache[/dim]\n"
            )

            choice = questionary.select(
                "Pilih aksi Pengumpulan & Sumber Proxy:",
                choices=[
                    "[1] Scrape Semua Sumber Upstream (Merge ke Raw Cache)",
                    "[2] Tambah & Simpan Sumber URL Baru (Bisa Langsung Fetch & Uji)",
                    "[3] Import dari File Lokal (.txt, .json, .yaml)",
                    "[4] Direct Paste Link Proxy via Terminal",
                    "[5] Kelola / Hapus Sumber Upstream yang Terdaftar",
                    "[6] Jalankan Health Check pada Seluruh Raw Cache Saat Ini",
                    "[0] Kembali ke Menu Utama",
                ],
                style=questionary.Style([("highlighted", "fg:cyan bold")]),
            ).ask()

            if choice is None or choice.startswith("[0]"):
                break

            if choice.startswith("[1]"):
                self._action_scrape_upstream()
            elif choice.startswith("[2]"):
                self._action_add_and_fetch_source()
            elif choice.startswith("[3]"):
                self._action_import_file()
            elif choice.startswith("[4]"):
                self._action_paste_links()
            elif choice.startswith("[5]"):
                self._action_manage_sources_list()
            elif choice.startswith("[6]"):
                self._action_check_raw_cache()

            questionary.text("Tekan Enter untuk melanjutkan...").ask()

    def _action_scrape_upstream(self) -> None:
        """Fetch from all upstream sources and merge into raw cache."""
        sources = self._load_sources()
        self.console.print(f"[bold cyan]Mengambil proxy dari {len(sources)} sumber upstream...[/bold cyan]")
        new_nodes = asyncio.run(self.collector.fetch_all_sources(sources))
        self._save_raw_proxies(new_nodes, merge_with_existing=True)
        total_raw = len(self._load_raw_proxies())
        self.views.render_status_panel(
            "SUKSES",
            f"Berhasil mengambil {len(new_nodes)} node dari upstream.\nTotal raw proxy dalam database: {total_raw} node.",
            style="green",
        )

    def _action_add_and_fetch_source(self) -> None:
        """Add a new source URL, save it permanently, and optionally fetch/test immediately."""
        name = questionary.text("Masukkan Nama / Label Sumber (Contoh: My-VIP-Subscription):").ask()
        if not name:
            return

        url = questionary.text("Masukkan URL Subscription / Upstream Source:").ask()
        if not url or not url.startswith("http"):
            self.views.render_status_panel("ERROR", "URL tidak valid. Harus diawali http:// atau https://", style="red")
            return

        stype = questionary.select(
            "Pilih Format / Tipe Sumber:",
            choices=[
                "base64 (Standard Base64 Subscription string)",
                "raw_lines (Plain text URI link per baris)",
                "raw_extract (Markdown / HTML text extractor)",
            ],
        ).ask()
        if not stype:
            return

        clean_type = stype.split()[0]
        new_source = {"name": name.strip(), "url": url.strip(), "type": clean_type}

        # Save to sources.json
        sources = self._load_sources()
        sources.append(new_source)
        self._save_sources(sources)
        self.views.render_status_panel("SUKSES", f"Sumber '{name}' berhasil disimpan ke data/sources.json!", style="green")

        # Ask to fetch & check immediately
        fetch_now = questionary.confirm("Apakah Anda ingin langsung mengambil & menguji node dari URL ini sekarang?").ask()
        if fetch_now:
            self.console.print("[bold cyan]Mengambil node dari sumber baru...[/bold cyan]")
            fetched = asyncio.run(self.collector.fetch_from_source(new_source))
            if not fetched:
                self.views.render_status_panel("PERINGATAN", "Tidak ada node proxy yang berhasil diambil dari URL ini.", style="yellow")
                return

            self.console.print(f"[green]Berhasil mengambil {len(fetched)} node. Menyimpan ke cache...[/green]")
            self._save_raw_proxies(fetched, merge_with_existing=True)

            check_now = questionary.confirm(f"Jalankan health check untuk {len(fetched)} node yang baru diambil ini?").ask()
            if check_now:
                self._run_health_check_pipeline(fetched, is_interactive=True, save_to_active=True)

    def _action_import_file(self) -> None:
        """Import raw proxy nodes from local file."""
        file_path = questionary.text("Masukkan path file lokal (Contoh: /root/proxies.txt atau config.yaml):").ask()
        if not file_path or not os.path.isfile(file_path):
            self.views.render_status_panel("ERROR", f"File tidak ditemukan: {file_path}", style="red")
            return

        imported = self.collector.import_from_file(file_path)
        if imported:
            self._save_raw_proxies(imported, merge_with_existing=True)
            self.views.render_status_panel(
                "SUKSES",
                f"Berhasil mengimpor {len(imported)} node dari {file_path} ke raw cache.",
                style="green",
            )
            if questionary.confirm("Langsung jalankan health check untuk node yang baru diimpor?").ask():
                self._run_health_check_pipeline(imported, is_interactive=True, save_to_active=True)
        else:
            self.views.render_status_panel("PERINGATAN", "Tidak ada link proxy yang valid ditemukan di dalam file tersebut.", style="yellow")

    def _action_paste_links(self) -> None:
        """Direct terminal paste of proxy links."""
        self.console.print("[bold cyan]Paste link proxy Anda di bawah ini (bisa multi-line). Masukkan baris kosong 'END' saat selesai:[/bold cyan]")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            except EOFError:
                break

        text = "\n".join(lines)
        nodes = self.collector.import_from_text(text)
        if nodes:
            self._save_raw_proxies(nodes, merge_with_existing=True)
            self.views.render_status_panel("SUKSES", f"Berhasil mengimpor {len(nodes)} node dari teks input.", style="green")
            if questionary.confirm("Langsung jalankan health check untuk node ini?").ask():
                self._run_health_check_pipeline(nodes, is_interactive=True, save_to_active=True)
        else:
            self.views.render_status_panel("PERINGATAN", "Tidak ada URI proxy valid yang terdeteksi.", style="yellow")

    def _action_manage_sources_list(self) -> None:
        """Manage / delete existing upstream sources."""
        sources = self._load_sources()
        if not sources:
            self.views.render_status_panel("INFO", "Belum ada sumber upstream yang tersimpan.", style="yellow")
            return

        choices = [f"[{i+1}] {s.get('name', 'Unknown')} ({s.get('type', 'raw')}) - {s.get('url', '')[:50]}" for i, s in enumerate(sources)]
        choices.append("[0] Batal")

        selected = questionary.select("Pilih sumber untuk dikelola / dihapus:", choices=choices).ask()
        if not selected or selected.startswith("[0]"):
            return

        idx = int(selected.split("]")[0][1:]) - 1
        src = sources[idx]

        action = questionary.select(
            f"Aksi untuk '{src.get('name')}':",
            choices=["[1] Uji & Ambil Node dari Sumber Ini Saja", "[2] Hapus Sumber Ini", "[0] Batal"],
        ).ask()

        if action and action.startswith("[1]"):
            self.console.print(f"[bold cyan]Mengambil node dari '{src.get('name')}'...[/bold cyan]")
            nodes = asyncio.run(self.collector.fetch_from_source(src))
            if nodes:
                self.views.render_status_panel("SUKSES", f"Berhasil mengambil {len(nodes)} node dari sumber ini.", style="green")
                self._save_raw_proxies(nodes, merge_with_existing=True)
                if questionary.confirm("Jalankan health check untuk node ini?").ask():
                    self._run_health_check_pipeline(nodes, is_interactive=True, save_to_active=True)
            else:
                self.views.render_status_panel("PERINGATAN", "Gagal mengambil node dari URL ini atau URL kosong.", style="yellow")

        elif action and action.startswith("[2]"):
            sources.pop(idx)
            self._save_sources(sources)
            self.views.render_status_panel("SUKSES", f"Sumber '{src.get('name')}' berhasil dihapus.", style="green")

    def _action_check_raw_cache(self) -> None:
        """Run health check on current raw cache."""
        raw_nodes = self._load_raw_proxies()
        if not raw_nodes:
            self.views.render_status_panel("PERINGATAN", "Database raw proxy masih kosong. Silakan kumpulkan proxy terlebih dahulu.", style="yellow")
            return
        self.console.print(f"[bold cyan]Menjalankan Health Check pada {len(raw_nodes)} raw nodes...[/bold cyan]")
        self._run_health_check_pipeline(raw_nodes, is_interactive=True, save_to_active=True)

    # =========================================================================
    # MENU 3: PROXY EXPLORER & LIVE FILTER (UNIFIED VIEW + FILTER + RUN)
    # =========================================================================

    def handle_proxy_explorer(self) -> None:
        """Interactive table explorer with real-time filtering, sorting, pagination, and direct runner binding."""
        page = 1
        page_size = 15
        active_filter: Dict[str, Any] = {"country": None, "protocol": None, "max_latency": None}
        current_sort = "latency"

        while True:
            self.views.render_banner()
            all_active = self._load_active_proxies()

            if not all_active:
                self.views.render_status_panel(
                    "DATABASE KOSONG",
                    "Belum ada proxy aktif yang terverifikasi.\nSilakan jalankan [1] Quick Update atau [2] Kumpulkan Proxy & Health Check.",
                    style="yellow",
                )
                questionary.text("Tekan Enter untuk kembali ke Menu Utama...").ask()
                break

            # Apply active filters
            displayed_nodes = self.exporter.filter_nodes(
                all_active,
                country=active_filter["country"],
                protocol=active_filter["protocol"],
                max_latency=active_filter["max_latency"],
            )

            # Apply sorting
            if current_sort == "latency":
                displayed_nodes.sort(key=lambda x: x.latency if x.latency > 0 else 999999)
            elif current_sort == "country":
                displayed_nodes.sort(key=lambda x: x.country_code or "ZZ")
            elif current_sort == "protocol":
                displayed_nodes.sort(key=lambda x: x.protocol or "")
            elif current_sort == "server":
                displayed_nodes.sort(key=lambda x: x.server or "")

            total_pages = max(1, (len(displayed_nodes) + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))

            filter_desc = []
            if active_filter["country"]:
                filter_desc.append(f"Negara: {active_filter['country']}")
            if active_filter["protocol"]:
                filter_desc.append(f"Protokol: {active_filter['protocol']}")
            if active_filter["max_latency"]:
                filter_desc.append(f"Max Latency: <{active_filter['max_latency']}ms")

            filter_str = f" [Filter: {', '.join(filter_desc)}]" if filter_desc else ""
            title_table = f"DAFTAR PROXY AKTIF{filter_str} (Urut: {current_sort.upper()})"

            self.views.render_proxy_table(
                displayed_nodes,
                title=title_table,
                page=page,
                page_size=page_size,
            )

            choices = [
                f"[1] Navigasi Halaman ({page}/{total_pages})",
                "[2] Filter Berdasarkan Negara / Protokol / Latensi",
                "[3] Reset Filter (Tampilkan Semua)",
                "[4] Urutkan Daftar (Sort by Latency, Country, Protocol, Server)",
                "[5] Lihat Detail Node Lengkap & Jalankan di Local Proxy",
                "[6] Ekspor Hasil Tampilan Ini ke File",
                "[0] Kembali ke Menu Utama",
            ]

            act = questionary.select("Pilih Aksi Explorer:", choices=choices).ask()
            if not act or act.startswith("[0]"):
                break

            if act.startswith("[1]"):
                pg_input = questionary.text(f"Pindah ke halaman (1-{total_pages}):", default=str(page)).ask()
                if pg_input and pg_input.isdigit():
                    page = int(pg_input)

            elif act.startswith("[2]"):
                c_in = questionary.text("Filter Kode Negara (Kosongkan jika tidak ada, misal: ID, SG, US):").ask()
                p_in = questionary.text("Filter Protokol (Kosongkan jika tidak ada, misal: VLESS, TROJAN, HYSTERIA2):").ask()
                l_in = questionary.text("Filter Latensi Maksimal ms (Kosongkan jika tidak ada, misal: 150):").ask()

                active_filter["country"] = c_in.strip().upper() if c_in and c_in.strip() else None
                active_filter["protocol"] = p_in.strip().lower() if p_in and p_in.strip() else None
                active_filter["max_latency"] = int(l_in.strip()) if l_in and l_in.strip().isdigit() else None
                page = 1

            elif act.startswith("[3]"):
                active_filter = {"country": None, "protocol": None, "max_latency": None}
                page = 1
                self.views.render_status_panel("INFO", "Filter berhasil di-reset.", style="cyan")
                time.sleep(0.5)

            elif act.startswith("[4]"):
                sort_choice = questionary.select(
                    "Pilih Kriteria Pengurutan:",
                    choices=[
                        "latency (Tercepat -> Terlambat)",
                        "country (Abjad Kode Negara)",
                        "protocol (Abjad Nama Protokol)",
                        "server (Abjad Server Host)",
                    ],
                ).ask()
                if sort_choice:
                    current_sort = sort_choice.split()[0]

            elif act.startswith("[5]"):
                self._action_view_node_detail_and_bind(displayed_nodes, page, page_size)

            elif act.startswith("[6]"):
                self._action_export_subset(displayed_nodes)

    def _action_view_node_detail_and_bind(self, nodes: List[ProxyNode], page: int, page_size: int) -> None:
        """View detailed configuration of a node and provide quick run binding."""
        start_idx = (page - 1) * page_size
        page_nodes = nodes[start_idx : start_idx + page_size]
        if not page_nodes:
            return

        choices = [f"[{i+1}] {n.name} ({n.protocol.upper()}) - {n.server}:{n.port}" for i, n in enumerate(page_nodes)]
        choices.append("[0] Batal")

        sel = questionary.select("Pilih node untuk melihat detail:", choices=choices).ask()
        if not sel or sel.startswith("[0]"):
            return

        node_idx = int(sel.split("]")[0][1:]) - 1
        node = page_nodes[node_idx]

        detail_text = Text()
        detail_text.append(f"Nama Node  : {node.name}\n", style="bold cyan")
        detail_text.append(f"Protokol   : {node.protocol.upper()}\n", style="bold yellow")
        detail_text.append(f"Server Host: {node.server}\n", style="white")
        detail_text.append(f"Port       : {node.port}\n", style="white")
        detail_text.append(f"Negara     : [{node.country_code}] {node.country_name}\n", style="green")
        detail_text.append(f"Latensi    : {node.latency} ms\n", style="bold green" if node.latency < 100 else "yellow")
        detail_text.append(f"ID Hash    : {node.id}\n\n", style="dim white")
        detail_text.append("Sing-box Outbound Config:\n", style="bold cyan")
        detail_text.append(json.dumps(node.config, indent=2), style="dim green")
        detail_text.append("\n\nRaw URI Link:\n", style="bold cyan")
        detail_text.append(node.raw_uri or "-", style="dim yellow")

        panel = Panel(detail_text, title=f"[bold cyan]DETAIL NODE - {node.name}[/bold cyan]", box=box.ASCII)
        self.console.print(panel)

        act = questionary.select(
            "Aksi untuk Node Ini:",
            choices=[
                "[1] Jalankan Node Ini Sebagai Local SOCKS5 / HTTP Proxy",
                "[2] Salin / Tampilkan Raw URI",
                "[0] Kembali",
            ],
        ).ask()

        if act and act.startswith("[1]"):
            self._start_runner_with_node(node)
        elif act and act.startswith("[2]"):
            self.console.print(Panel(Text(node.raw_uri, style="bold yellow"), title="RAW URI LINK", box=box.ASCII))
            questionary.text("Tekan Enter untuk melanjutkan...").ask()

    def _start_runner_with_node(self, node: ProxyNode) -> None:
        """Start local proxy runner using selected node."""
        cfg = self._load_config()
        socks_port = int(cfg.get("local_socks_port", 1080))
        http_port = int(cfg.get("local_http_port", 1081))

        self.console.print(f"[bold cyan]Menjalankan local proxy server untuk node '{node.name}'...[/bold cyan]")
        try:
            bm = BinaryManager()
            bin_path = bm.ensure_singbox()
            self.runner.bin_path = bin_path
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal memverifikasi sing-box: {e}", style="red")
            return

        if self.runner.is_running():
            self.runner.stop()

        success = self.runner.start(node, socks_port=socks_port, http_port=http_port)
        if success:
            self.views.render_status_panel(
                "LOCAL PROXY BERHASIL AKTIF",
                f"Node        : {node.name}\n"
                f"SOCKS5 Proxy: 127.0.0.1:{socks_port}\n"
                f"HTTP Proxy  : 127.0.0.1:{http_port}\n"
                f"Status      : [RUNNING] di latar belakang.",
                style="green",
            )
        else:
            self.views.render_status_panel("ERROR", "Gagal menjalankan local proxy daemon sing-box.", style="red")
        questionary.text("Tekan Enter untuk melanjutkan...").ask()

    # =========================================================================
    # MENU 4: EXPORT CENTER
    # =========================================================================

    def handle_export(self) -> None:
        """Dedicated export center supporting all format generators and filters."""
        self.views.render_banner()
        all_active = self._load_active_proxies()

        if not all_active:
            self.views.render_status_panel("PERINGATAN", "Tidak ada proxy aktif dalam database untuk diekspor.", style="yellow")
            questionary.text("Tekan Enter untuk kembali...").ask()
            return

        scope = questionary.select(
            "Pilih Cakupan Node yang Akan Diekspor:",
            choices=[
                f"[1] Ekspor Semua Proxy Aktif ({len(all_active)} node)",
                "[2] Ekspor dengan Filter Kustom (Negara, Protokol, Latensi)",
                "[0] Batal",
            ],
        ).ask()

        if not scope or scope.startswith("[0]"):
            return

        target_nodes = all_active
        if scope.startswith("[2]"):
            c_in = questionary.text("Filter Kode Negara (Kosongkan jika tidak ada, misal: ID, SG):").ask()
            p_in = questionary.text("Filter Protokol (Kosongkan jika tidak ada, misal: VLESS, HYSTERIA2):").ask()
            l_in = questionary.text("Filter Max Latency ms (Kosongkan jika tidak ada, misal: 150):").ask()

            c_val = c_in.strip().upper() if c_in and c_in.strip() else None
            p_val = p_in.strip().lower() if p_in and p_in.strip() else None
            l_val = int(l_in.strip()) if l_in and l_in.strip().isdigit() else None

            target_nodes = self.exporter.filter_nodes(all_active, country=c_val, protocol=p_val, max_latency=l_val)
            if not target_nodes:
                self.views.render_status_panel("INFO", "Tidak ada node yang cocok dengan kriteria filter tersebut.", style="yellow")
                questionary.text("Tekan Enter untuk kembali...").ask()
                return

        self._action_export_subset(target_nodes)

    def _action_export_subset(self, nodes: List[ProxyNode]) -> None:
        """Export a subset of nodes to chosen format."""
        fmt = questionary.select(
            f"Pilih Format Ekspor untuk {len(nodes)} node:",
            choices=[
                "[1] Raw Links .txt (Daftar URI link per baris)",
                "[2] Base64 Subscription (String Sub standar v2rayN/NekoBox)",
                "[3] Clash Meta / Mihomo YAML (Proxy Groups & Rules)",
                "[4] Sing-box JSON (Outbounds 1.9+ & URLTest Group)",
                "[5] Ekspor ke SEMUA Format Sekaligus",
                "[0] Batal",
            ],
        ).ask()

        if not fmt or fmt.startswith("[0]"):
            return

        os.makedirs(EXPORTS_DIR, exist_ok=True)
        exported_files = []

        if fmt.startswith("[1]") or fmt.startswith("[5]"):
            p = f"{EXPORTS_DIR}/proxies_raw.txt"
            self.exporter.export_raw(nodes, p)
            exported_files.append(p)

        if fmt.startswith("[2]") or fmt.startswith("[5]"):
            p = f"{EXPORTS_DIR}/subscription_base64.txt"
            self.exporter.export_base64(nodes, p)
            exported_files.append(p)

        if fmt.startswith("[3]") or fmt.startswith("[5]"):
            p = f"{EXPORTS_DIR}/clash_meta.yaml"
            self.exporter.export_clash(nodes, p)
            exported_files.append(p)

        if fmt.startswith("[4]") or fmt.startswith("[5]"):
            p = f"{EXPORTS_DIR}/singbox_config.json"
            self.exporter.export_singbox(nodes, p)
            exported_files.append(p)

        file_list = "\n".join([f"- {f}" for f in exported_files])
        self.views.render_status_panel(
            "EKSPOR BERHASIL",
            f"Berhasil mengekspor {len(nodes)} proxy ke:\n{file_list}",
            style="green",
        )
        questionary.text("Tekan Enter untuk melanjutkan...").ask()

    # =========================================================================
    # MENU 5: LOCAL PROXY RUNNER (SOCKS5 / HTTP DAEMON)
    # =========================================================================

    def handle_local_runner(self) -> None:
        """Local SOCKS5 / HTTP Proxy runner manager."""
        while True:
            self.views.render_banner()
            status = self.runner.get_status()
            self.views.render_runner_status(status)

            choices = []
            if status.get("status") == "RUNNING" or status.get("running"):
                choices.append("[1] Hentikan Local Proxy Server (Stop)")
                choices.append("[2] Ganti Node Proxy Aktif")
            else:
                choices.append("[1] Jalankan Local Proxy Server (Pilih Node)")

            choices.append("[0] Kembali ke Menu Utama")

            act = questionary.select("Pilih Aksi Local Proxy:", choices=choices).ask()
            if not act or act.startswith("[0]"):
                break

            if "Hentikan" in act:
                self.runner.stop()
                self.views.render_status_panel("SUKSES", "Local Proxy Server berhasil dihentikan.", style="yellow")
                time.sleep(0.5)

            elif "Jalankan" in act or "Ganti" in act:
                active_nodes = self._load_active_proxies()
                if not active_nodes:
                    self.views.render_status_panel(
                        "PERINGATAN",
                        "Belum ada proxy aktif. Silakan lakukan health check terlebih dahulu.",
                        style="yellow",
                    )
                    questionary.text("Tekan Enter...").ask()
                    continue

                # Node selection with clean prompt
                node_choices = [
                    f"[{i+1}] {n.name} ({n.protocol.upper()}) - {n.server}:{n.port}"
                    for i, n in enumerate(active_nodes[:50])
                ]
                node_choices.append("[0] Batal")

                selected_node = questionary.select("Pilih Node untuk dijalankan:", choices=node_choices).ask()
                if selected_node and not selected_node.startswith("[0]"):
                    idx = int(selected_node.split("]")[0][1:]) - 1
                    target_node = active_nodes[idx]
                    self._start_runner_with_node(target_node)

    # =========================================================================
    # MENU 6: AUTOMATION & SETTINGS (SCHEDULER & ENGINE CONFIG)
    # =========================================================================

    def handle_automation_and_settings(self) -> None:
        """Unified hub for background auto-scheduler and engine configuration."""
        while True:
            self.views.render_banner()
            cfg = self._load_config()
            sched_status = self.scheduler.get_status()

            self.views.render_scheduler_status(sched_status)

            config_text = Text()
            config_text.append(f"Concurrency Workers : {cfg.get('concurrency', 30)}\n", style="bold cyan")
            config_text.append(f"Request Timeout     : {cfg.get('timeout', 5000)} ms\n", style="bold cyan")
            config_text.append(f"Test URL Endpoint   : {cfg.get('test_url', '')}\n", style="bold cyan")
            config_text.append(f"Local SOCKS5 Port   : {cfg.get('local_socks_port', 1080)}\n", style="bold cyan")
            config_text.append(f"Local HTTP Port     : {cfg.get('local_http_port', 1081)}\n", style="bold cyan")
            config_text.append(f"Auto-Update Interval: {cfg.get('auto_update_interval_minutes', 60)} menit", style="bold cyan")

            panel = Panel(config_text, title="[bold cyan]PENGATURAN ENGINE CHECKER[/bold cyan]", box=box.ASCII)
            self.console.print(panel)

            choices = []
            if sched_status.get("status") == "RUNNING" or sched_status.get("active"):
                choices.append("[1] Matikan Auto-Scheduler Background")
            else:
                choices.append("[1] Aktifkan Auto-Scheduler Background")

            choices.extend(
                [
                    "[2] Ubah Interval Auto-Update Scheduler",
                    "[3] Ubah Concurrency Checker Workers",
                    "[4] Ubah Request Timeout Checker",
                    "[5] Ubah Test URL Endpoint",
                    "[6] Ubah Port Inbound Local Proxy (SOCKS5 / HTTP)",
                    "[0] Kembali ke Menu Utama",
                ]
            )

            act = questionary.select("Pilih Pengaturan:", choices=choices).ask()
            if not act or act.startswith("[0]"):
                break

            if act.startswith("[1]"):
                if self.scheduler.is_running():
                    self.scheduler.stop()
                    self.views.render_status_panel("SUKSES", "Auto-scheduler background berhasil dinonaktifkan.", style="yellow")
                else:
                    interval = float(cfg.get("auto_update_interval_minutes", 60))
                    self.scheduler.start(interval_minutes=interval, task_callback=self.handle_headless_update)
                    self.views.render_status_panel(
                        "SUKSES",
                        f"Auto-scheduler aktif! Pengecekan otomatis akan berjalan tiap {interval} menit.",
                        style="green",
                    )
                time.sleep(0.5)

            elif act.startswith("[2]"):
                val = questionary.text("Masukkan interval auto-update baru (dalam menit, misal: 30 atau 60):").ask()
                if val and val.isdigit() and int(val) > 0:
                    cfg["auto_update_interval_minutes"] = int(val)
                    self._save_config(cfg)
                    if self.scheduler.is_running():
                        self.scheduler.start(interval_minutes=int(val), task_callback=self.handle_headless_update)
                    self.views.render_status_panel("SUKSES", f"Interval berhasil diubah menjadi {val} menit.", style="green")
                    time.sleep(0.5)

            elif act.startswith("[3]"):
                val = questionary.text("Masukkan jumlah concurrency workers (10 - 100):", default=str(cfg.get("concurrency", 30))).ask()
                if val and val.isdigit():
                    cfg["concurrency"] = max(1, min(200, int(val)))
                    self._save_config(cfg)
                    self.views.render_status_panel("SUKSES", f"Concurrency diubah ke {cfg['concurrency']}.", style="green")
                    time.sleep(0.5)

            elif act.startswith("[4]"):
                val = questionary.text("Masukkan timeout koneksi dalam ms (1000 - 15000):", default=str(cfg.get("timeout", 5000))).ask()
                if val and val.isdigit():
                    cfg["timeout"] = int(val)
                    self._save_config(cfg)
                    self.views.render_status_panel("SUKSES", f"Timeout diubah ke {cfg['timeout']} ms.", style="green")
                    time.sleep(0.5)

            elif act.startswith("[5]"):
                val = questionary.text("Masukkan Test URL Connectivity Endpoint:", default=cfg.get("test_url", "")).ask()
                if val and val.startswith("http"):
                    cfg["test_url"] = val.strip()
                    self._save_config(cfg)
                    self.views.render_status_panel("SUKSES", "Test URL berhasil diperbarui.", style="green")
                    time.sleep(0.5)

            elif act.startswith("[6]"):
                s_port = questionary.text("Port Lokal SOCKS5:", default=str(cfg.get("local_socks_port", 1080))).ask()
                h_port = questionary.text("Port Lokal HTTP:", default=str(cfg.get("local_http_port", 1081))).ask()
                if s_port and s_port.isdigit() and h_port and h_port.isdigit():
                    cfg["local_socks_port"] = int(s_port)
                    cfg["local_http_port"] = int(h_port)
                    self._save_config(cfg)
                    self.views.render_status_panel("SUKSES", "Port local proxy berhasil diperbarui.", style="green")
                    time.sleep(0.5)

    # =========================================================================
    # APPLICATION EXIT & MAIN LOOP
    # =========================================================================

    def handle_exit(self) -> None:
        """Gracefully stop background processes and clean exit."""
        if self.runner.is_running():
            self.runner.stop()
        if self.scheduler.is_running():
            self.scheduler.stop()
        self.views.render_status_panel("INFO", "Aplikasi dihentikan. Sampai jumpa!", style="cyan")

    def run(self) -> None:
        """Main application interactive loop."""
        while True:
            self.views.render_banner()
            active_count = len(self._load_active_proxies())
            raw_count = len(self._load_raw_proxies())
            sources_count = len(self._load_sources())

            summary_text = (
                f"[dim]Database Status: {active_count} Proxy Aktif | "
                f"{raw_count} Raw Cache | {sources_count} Upstream Sources[/dim]\n"
            )
            self.console.print(summary_text)

            choice = questionary.select(
                "Pilih Menu Utama:",
                choices=[
                    "[1] Quick Update (Scrape Upstream + Health Check All - Safe Merge)",
                    "[2] Proxy Collector & Sources Hub (Scrape, Add URL, Import, Paste, Kelola Sumber)",
                    "[3] Proxy Explorer & Live Filter (Lihat Tabel, Filter, Sort, Detail, Run)",
                    "[4] Ekspor Proxy (Raw Links, Base64 Sub, Clash/Mihomo, Sing-box)",
                    "[5] Jalankan Local Proxy Server (SOCKS5/HTTP Runner)",
                    "[6] Otomatisasi & Pengaturan (Scheduler Background & Engine Settings)",
                    "[0] Keluar",
                ],
                style=questionary.Style([("highlighted", "fg:cyan bold")]),
            ).ask()

            if choice is None or choice.startswith("[0]"):
                self.handle_exit()
                break

            if choice.startswith("[1]"):
                self.handle_quick_update()
                questionary.text("Tekan Enter untuk melanjutkan...").ask()
            elif choice.startswith("[2]"):
                self.handle_collector_hub()
            elif choice.startswith("[3]"):
                self.handle_proxy_explorer()
            elif choice.startswith("[4]"):
                self.handle_export()
            elif choice.startswith("[5]"):
                self.handle_local_runner()
            elif choice.startswith("[6]"):
                self.handle_automation_and_settings()
