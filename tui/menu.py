"""Interactive TUI Menu Component for Proxy Scraper & Checker (Strictly No Emoji)."""

import os
import sys
import json
import time
import asyncio
from typing import List, Dict, Any, Optional
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
        collector = ProxyCollector()
        if os.path.exists(RAW_PROXIES_FILE):
            return collector.import_from_file(RAW_PROXIES_FILE)
        return []

    def _save_raw_proxies(self, nodes: List[ProxyNode]) -> None:
        """Save raw nodes to data/proxies_raw.txt."""
        try:
            raw_uris = [n.raw_uri for n in nodes if n.raw_uri]
            with open(RAW_PROXIES_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(raw_uris) + "\n")
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal menyimpan raw proxies: {e}", style="red")

    def handle_scrape_and_check_all(self) -> List[ProxyNode]:
        """One-click update: Scrape all sources, run health check, save active & raw, render summary."""
        self.views.render_banner()
        self.console.print("[bold cyan][1/3] Menyiapkan environment & binary sing-box...[/bold cyan]")
        try:
            bm = BinaryManager()
            bm.ensure_singbox()
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal mengunduh/menyiapkan binary sing-box: {e}", style="red")
            return []

        self.console.print("[bold cyan][2/3] Mengumpulkan proxy dari seluruh sumber upstream...[/bold cyan]")
        sources = self._load_sources()
        collector = ProxyCollector()

        start_time = time.time()
        raw_nodes = asyncio.run(collector.fetch_all_sources(sources))
        self.console.print(f"[bold green]Berhasil mengumpulkan {len(raw_nodes)} raw node unik.[/bold green]")
        self._save_raw_proxies(raw_nodes)

        if not raw_nodes:
            self.views.render_status_panel("WARNING", "Tidak ada proxy yang dapat diambil dari sumber upstream.", style="yellow")
            return []

        self.console.print(f"[bold cyan][3/3] Menjalankan health check ({len(raw_nodes)} nodes)...[/bold cyan]")
        cfg = self._load_config()
        checker = ProxyChecker(
            concurrency=cfg.get("concurrency", 30),
            timeout=cfg.get("timeout", 5000),
            test_url=cfg.get("test_url", "http://cp.cloudflare.com/generate_204"),
            fallback_test_url=cfg.get("backup_test_url", "https://www.gstatic.com/generate_204"),
        )

        progress = self.views.create_progress_bar()
        alive_nodes: List[ProxyNode] = []
        dead_nodes: List[ProxyNode] = []

        with progress:
            task_id = progress.add_task("Health Checking...", total=len(raw_nodes))

            def on_prog(completed: int, total: int, last_node: ProxyNode):
                progress.update(task_id, completed=completed)

            alive_nodes, dead_nodes = asyncio.run(checker.check_nodes(raw_nodes, on_progress=on_prog))

        duration = time.time() - start_time
        alive_nodes.sort(key=lambda x: x.latency if x.latency > 0 else 999999)

        self._save_active_proxies(alive_nodes)
        self.views.render_summary(
            total=len(raw_nodes),
            alive=len(alive_nodes),
            dead=len(dead_nodes),
            duration_sec=duration,
        )
        return alive_nodes

    def handle_collect_proxies(self) -> List[ProxyNode]:
        """Sub-menu for proxy collection (Public sources, Custom URL, File import, Direct paste)."""
        self.views.render_banner()
        choice = questionary.select(
            "Pilih Metode Pengumpulkan Proxy:",
            choices=[
                "[1] Scrape Publik Upstream Sources",
                "[2] Input Custom URL Subscription",
                "[3] Import File (TXT / JSON / YAML)",
                "[4] Direct Paste Proxy Links",
                "[0] Kembali ke Menu Utama",
            ],
        ).ask()

        if choice is None or choice.startswith("[0]"):
            return []

        collector = ProxyCollector()
        existing_raw = self._load_raw_proxies()
        new_nodes: List[ProxyNode] = []

        if choice.startswith("[1]"):
            sources = self._load_sources()
            self.console.print("[bold cyan]Mengambil proxy dari sumber upstream...[/bold cyan]")
            new_nodes = asyncio.run(collector.fetch_all_sources(sources))
        elif choice.startswith("[2]"):
            url = questionary.text("Masukkan URL Subscription / Proxy Link:").ask()
            if url and url.strip():
                self.console.print("[bold cyan]Mengambil proxy dari URL...[/bold cyan]")
                new_nodes = asyncio.run(collector.fetch_from_source({"url": url.strip(), "name": "Custom"}))
        elif choice.startswith("[3]"):
            path = questionary.text("Masukkan Path File (.txt / .json / .yaml / .yml):").ask()
            if path and path.strip() and os.path.exists(path.strip()):
                self.console.print("[bold cyan]Membaca proxy dari file...[/bold cyan]")
                new_nodes = collector.import_from_file(path.strip())
            else:
                self.views.render_status_panel("ERROR", f"File tidak ditemukan: {path}", style="red")
                return []
        elif choice.startswith("[4]"):
            raw_text = questionary.text("Paste raw proxy links / text di sini:").ask()
            if raw_text and raw_text.strip():
                new_nodes = collector.import_from_text(raw_text.strip())

        all_nodes = collector.deduplicate(existing_raw + new_nodes)
        self._save_raw_proxies(all_nodes)
        self.views.render_status_panel(
            "PENGUMPULAN SUCCESS",
            f"Ditemukan {len(new_nodes)} node baru. Total Raw Cache: {len(all_nodes)} node.",
            style="green",
        )
        return all_nodes

    def handle_health_check(self) -> List[ProxyNode]:
        """Runs health check on raw/existing proxies and updates active list."""
        self.views.render_banner()
        raw_nodes = self._load_raw_proxies()
        if not raw_nodes:
            raw_nodes = self._load_active_proxies()

        if not raw_nodes:
            self.views.render_status_panel(
                "WARNING", "Belum ada proxy raw/aktif. Silakan kumpulkan proxy terlebih dahulu.", style="yellow"
            )
            return []

        try:
            bm = BinaryManager()
            bm.ensure_singbox()
        except Exception as e:
            self.views.render_status_panel("ERROR", f"Gagal mengunduh/menyiapkan binary sing-box: {e}", style="red")
            return []

        self.console.print(f"[bold cyan]Menjalankan health check pada {len(raw_nodes)} node...[/bold cyan]")
        cfg = self._load_config()
        checker = ProxyChecker(
            concurrency=cfg.get("concurrency", 30),
            timeout=cfg.get("timeout", 5000),
            test_url=cfg.get("test_url", "http://cp.cloudflare.com/generate_204"),
            fallback_test_url=cfg.get("backup_test_url", "https://www.gstatic.com/generate_204"),
        )

        progress = self.views.create_progress_bar()
        start_time = time.time()
        alive_nodes: List[ProxyNode] = []
        dead_nodes: List[ProxyNode] = []

        with progress:
            task_id = progress.add_task("Checking Proxies...", total=len(raw_nodes))

            def on_prog(completed: int, total: int, last_node: ProxyNode):
                progress.update(task_id, completed=completed)

            alive_nodes, dead_nodes = asyncio.run(checker.check_nodes(raw_nodes, on_progress=on_prog))

        duration = time.time() - start_time
        alive_nodes.sort(key=lambda x: x.latency if x.latency > 0 else 999999)

        self._save_active_proxies(alive_nodes)
        self.views.render_summary(
            total=len(raw_nodes),
            alive=len(alive_nodes),
            dead=len(dead_nodes),
            duration_sec=duration,
        )
        return alive_nodes

    def handle_view_proxies(self) -> None:
        """Displays paginated table of active proxies with details & sorting options."""
        active_nodes = self._load_active_proxies()
        if not active_nodes:
            self.views.render_banner()
            self.views.render_status_panel("INFO", "Belum ada proxy aktif tersimpan. Lakukan Scrape/Check dahulu.", style="yellow")
            return

        page = 1
        page_size = 20
        sort_by = "latency"

        while True:
            self.views.render_banner()

            nodes_to_show = list(active_nodes)
            if sort_by == "latency":
                nodes_to_show.sort(key=lambda x: x.latency if x.latency > 0 else 999999)
            elif sort_by == "country":
                nodes_to_show.sort(key=lambda x: x.country_code or "ZZ")
            elif sort_by == "protocol":
                nodes_to_show.sort(key=lambda x: x.protocol or "")
            elif sort_by == "server":
                nodes_to_show.sort(key=lambda x: x.server or "")

            total_pages = max(1, (len(nodes_to_show) + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))

            self.views.render_proxy_table(
                nodes=nodes_to_show,
                title=f"DAFTAR PROXY AKTIF (Sorted by {sort_by.upper()})",
                page=page,
                page_size=page_size,
            )

            actions = []
            if page < total_pages:
                actions.append("[n] Next Page")
            if page > 1:
                actions.append("[p] Previous Page")
            actions.extend([
                "[s] Sort Options (Latency / Country / Protocol / Server)",
                "[d] Detail Proxy Node",
                "[0] Kembali ke Menu Utama",
            ])

            choice = questionary.select("Pilih aksi navigasi:", choices=actions).ask()

            if choice is None or choice.startswith("[0]"):
                break
            elif choice.startswith("[n]"):
                page += 1
            elif choice.startswith("[p]"):
                page -= 1
            elif choice.startswith("[s]"):
                sort_choice = questionary.select(
                    "Urutkan Berdasarkan:",
                    choices=[
                        "Latency (Tercepat)",
                        "Country (Kode Negara)",
                        "Protocol (Jenis Protokol)",
                        "Server (Host / IP)",
                    ],
                ).ask()
                if sort_choice:
                    if "Latency" in sort_choice:
                        sort_by = "latency"
                    elif "Country" in sort_choice:
                        sort_by = "country"
                    elif "Protocol" in sort_choice:
                        sort_by = "protocol"
                    elif "Server" in sort_choice:
                        sort_by = "server"
            elif choice.startswith("[d]"):
                idx_str = questionary.text(f"Masukkan nomor proxy (1 - {len(nodes_to_show)}):").ask()
                if idx_str and idx_str.isdigit():
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(nodes_to_show):
                        node = nodes_to_show[idx]
                        self._render_node_detail(node)
                        questionary.text("Tekan Enter untuk kembali...").ask()

    def _render_node_detail(self, node: ProxyNode) -> None:
        """Render detailed breakdown panel for a specific ProxyNode."""
        content = Text()
        content.append("Node ID       : ", style="bold cyan")
        content.append(f"{node.id}\n", style="white")
        content.append("Name          : ", style="bold cyan")
        content.append(f"{node.name}\n", style="bold yellow")
        content.append("Protocol      : ", style="bold cyan")
        content.append(f"{node.protocol.upper()}\n", style="bold green")
        content.append("Server        : ", style="bold cyan")
        content.append(f"{node.server}\n", style="white")
        content.append("Port          : ", style="bold cyan")
        content.append(f"{node.port}\n", style="white")
        content.append("Country       : ", style="bold cyan")
        content.append(f"[{node.country_code}] {node.country_name}\n", style="bold yellow")
        content.append("Latency       : ", style="bold cyan")
        content.append(f"{node.latency} ms\n", style="bold green" if node.latency < 300 else "bold red")
        content.append("Last Checked  : ", style="bold cyan")
        content.append(f"{node.last_checked}\n\n", style="dim white")
        content.append("Raw URI:\n", style="bold cyan")
        content.append(f"{node.raw_uri}\n\n", style="dim white")
        content.append("Sing-box Outbound Config:\n", style="bold cyan")
        content.append(f"{json.dumps(node.config, indent=2)}", style="green")

        panel = Panel(
            content,
            title="[bold cyan]DETAIL PROXY NODE[/bold cyan]",
            border_style="cyan",
            box=box.ASCII,
        )
        self.console.print(panel)

    def handle_export(self) -> None:
        """Lets user choose export format and apply optional filters."""
        self.views.render_banner()
        active_nodes = self._load_active_proxies()
        if not active_nodes:
            self.views.render_status_panel("WARNING", "Belum ada proxy aktif untuk diekspor. Scrape/Check dahulu.", style="yellow")
            return

        choice = questionary.select(
            "Pilih Format Ekspor Proxy:",
            choices=[
                "[1] Raw Proxy Links (.txt)",
                "[2] Base64 Subscription (.txt)",
                "[3] Clash / Mihomo Configuration (.yaml)",
                "[4] Sing-box Configuration (.json)",
                "[0] Kembali",
            ],
        ).ask()

        if choice is None or choice.startswith("[0]"):
            return

        country = questionary.text("Filter Negara (misal: SG, US, ID atau tekan Enter untuk Semua):").ask()
        protocol = questionary.text("Filter Protokol (misal: trojan, vless, vmess, ss, hy2 atau Enter):").ask()
        max_lat_str = questionary.text("Max Latency ms (misal: 300, 500 atau Enter untuk Tanpa Batas):").ask()

        country_filter = country.strip() if country and country.strip() else None
        protocol_filter = protocol.strip() if protocol and protocol.strip() else None
        max_latency_filter = int(max_lat_str.strip()) if max_lat_str and max_lat_str.strip().isdigit() else None

        filtered_nodes = self.exporter.filter_nodes(
            active_nodes,
            country=country_filter,
            protocol=protocol_filter,
            max_latency=max_latency_filter,
        )

        if not filtered_nodes:
            self.views.render_status_panel("WARNING", "Tidak ada proxy yang memenuhi kriteria filter.", style="yellow")
            return

        default_filenames = {
            "[1]": "data/exports/proxies_raw.txt",
            "[2]": "data/exports/proxies_base64.txt",
            "[3]": "data/exports/clash.yaml",
            "[4]": "data/exports/singbox.json",
        }

        key = choice[:3]
        default_file = default_filenames.get(key, "data/exports/output.txt")
        out_path = questionary.text(f"Masukkan path file output (Default: {default_file}):").ask()
        output_file = out_path.strip() if out_path and out_path.strip() else default_file

        if choice.startswith("[1]"):
            saved_path = self.exporter.export_raw(filtered_nodes, output_file)
        elif choice.startswith("[2]"):
            saved_path = self.exporter.export_base64(filtered_nodes, output_file)
        elif choice.startswith("[3]"):
            saved_path = self.exporter.export_clash(filtered_nodes, output_file)
        elif choice.startswith("[4]"):
            saved_path = self.exporter.export_singbox(filtered_nodes, output_file)
        else:
            return

        self.views.render_status_panel(
            "EKSPOR SUCCESS",
            f"Berhasil mengekspor {len(filtered_nodes)} node proxy ke:\n{saved_path}",
            style="green",
        )

    def handle_local_runner(self) -> None:
        """Start / Stop local proxy runner daemon forwarding traffic through selected node."""
        self.views.render_banner()
        runner_status = self.runner.get_status()
        self.views.render_runner_status(runner_status)

        if self.runner.is_running():
            choice = questionary.select(
                "Pilih Aksi Local Proxy Server:",
                choices=[
                    "[1] Hentikan Local Proxy Server (Stop Daemon)",
                    "[2] Ganti Active Proxy Node",
                    "[0] Kembali",
                ],
            ).ask()

            if choice and choice.startswith("[1]"):
                self.runner.stop()
                self.views.render_status_panel("RUNNER", "Local proxy daemon dihentikan.", style="yellow")
                return
            elif choice and choice.startswith("[2]"):
                self.runner.stop()
            else:
                return

        active_nodes = self._load_active_proxies()
        if not active_nodes:
            self.views.render_status_panel("WARNING", "Belum ada proxy aktif. Lakukan Health Check terlebih dahulu.", style="yellow")
            return

        active_nodes.sort(key=lambda x: x.latency if x.latency > 0 else 999999)

        node_choices = [
            f"[{idx+1}] {n.name} ({n.latency}ms)" for idx, n in enumerate(active_nodes[:20])
        ]
        node_choices.append("[0] Batal")

        sel_node = questionary.select("Pilih proxy node untuk local daemon:", choices=node_choices).ask()
        if not sel_node or sel_node.startswith("[0]"):
            return

        idx = int(sel_node.split("]")[0].replace("[", "")) - 1
        target_node = active_nodes[idx]

        cfg = self._load_config()
        socks_p = questionary.text(f"Masukkan Port SOCKS5 Local (Default: {cfg.get('local_socks_port', 1080)}):").ask()
        http_p = questionary.text(f"Masukkan Port HTTP Local (Default: {cfg.get('local_http_port', 1081)}):").ask()

        socks_port = int(socks_p.strip()) if socks_p and socks_p.strip().isdigit() else cfg.get("local_socks_port", 1080)
        http_port = int(http_p.strip()) if http_p and http_p.strip().isdigit() else cfg.get("local_http_port", 1081)

        self.console.print("[bold cyan]Menjalankan local proxy server sing-box...[/bold cyan]")
        success = self.runner.start(target_node, socks_port=socks_port, http_port=http_port)

        if success:
            self.views.render_runner_status(self.runner.get_status())
        else:
            self.views.render_status_panel("ERROR", "Gagal menjalankan local proxy daemon sing-box.", style="red")

    def handle_scheduler(self) -> None:
        """Start / Stop auto-scheduler periodic background job."""
        self.views.render_banner()
        sched_status = self.scheduler.get_status()
        self.views.render_scheduler_status(sched_status)

        if self.scheduler.is_running():
            choice = questionary.select(
                "Pilih Aksi Auto-Scheduler:",
                choices=[
                    "[1] Hentikan Auto-Scheduler",
                    "[2] Ubah Interval Pengecekan",
                    "[0] Kembali",
                ],
            ).ask()

            if choice and choice.startswith("[1]"):
                self.scheduler.stop()
                self.views.render_status_panel("SCHEDULER", "Auto-scheduler background job dihentikan.", style="yellow")
                return
            elif choice and choice.startswith("[2]"):
                self.scheduler.stop()
            else:
                return

        choice = questionary.select(
            "Pilih Aksi Auto-Scheduler:",
            choices=[
                "[1] Jalankan Auto-Scheduler Background Job",
                "[0] Kembali",
            ],
        ).ask()

        if not choice or choice.startswith("[0]"):
            return

        cfg = self._load_config()
        default_interval = cfg.get("auto_update_interval_minutes", 60)
        inv_str = questionary.text(f"Masukkan interval pengecekan otomatis dalam menit (Default: {default_interval}):").ask()
        interval = float(inv_str.strip()) if inv_str and inv_str.strip().replace(".", "", 1).isdigit() else float(default_interval)

        self.console.print(f"[bold cyan]Memulai Auto-Scheduler (Interval: {interval} menit)...[/bold cyan]")
        self.scheduler.start(
            interval_minutes=interval,
            task_callback=self.handle_scrape_and_check_all,
            on_log=lambda msg: self.console.print(f"[dim cyan]{msg}[/dim cyan]"),
        )
        self.views.render_scheduler_status(self.scheduler.get_status())

    def handle_settings(self) -> None:
        """Edit concurrency, timeout, test URL, and manage upstream sources."""
        while True:
            self.views.render_banner()
            cfg = self._load_config()

            choice = questionary.select(
                "Pengaturan & Kelola Upstream Sources:",
                choices=[
                    f"[1] Ubah Concurrency Checker (Current: {cfg.get('concurrency', 30)})",
                    f"[2] Ubah Timeout Check (ms) (Current: {cfg.get('timeout', 5000)} ms)",
                    f"[3] Ubah Target Test URL (Current: {cfg.get('test_url', '')})",
                    "[4] Kelola Upstream Sources (Tambah/Hapus/Lihat Sumber)",
                    "[0] Kembali ke Menu Utama",
                ],
            ).ask()

            if choice is None or choice.startswith("[0]"):
                break
            elif choice.startswith("[1]"):
                val = questionary.text(f"Masukkan Concurrency baru (1 - 200, Current: {cfg.get('concurrency', 30)}):").ask()
                if val and val.strip().isdigit():
                    cfg["concurrency"] = int(val.strip())
                    self._save_config(cfg)
                    self.views.render_status_panel("SUCCESS", f"Concurrency diubah menjadi: {cfg['concurrency']}", style="green")
            elif choice.startswith("[2]"):
                val = questionary.text(f"Masukkan Timeout baru dalam ms (Current: {cfg.get('timeout', 5000)}):").ask()
                if val and val.strip().isdigit():
                    cfg["timeout"] = int(val.strip())
                    self._save_config(cfg)
                    self.views.render_status_panel("SUCCESS", f"Timeout diubah menjadi: {cfg['timeout']} ms", style="green")
            elif choice.startswith("[3]"):
                val = questionary.text(f"Masukkan Test URL baru (Current: {cfg.get('test_url', '')}):").ask()
                if val and val.strip():
                    cfg["test_url"] = val.strip()
                    self._save_config(cfg)
                    self.views.render_status_panel("SUCCESS", f"Test URL diubah menjadi: {cfg['test_url']}", style="green")
            elif choice.startswith("[4]"):
                self._handle_sources_management()

    def _handle_sources_management(self) -> None:
        """Submenu to view, add, or delete upstream subscription sources."""
        while True:
            self.views.render_banner()
            sources = self._load_sources()

            self.console.print("[bold cyan]Daftar Upstream Sources Currently Active:[/bold cyan]")
            for idx, src in enumerate(sources, 1):
                self.console.print(f" [{idx}] {src.get('name', 'Source')} -> {src.get('url', '')}")

            choice = questionary.select(
                "Pilih Aksi Upstream Sources:",
                choices=[
                    "[1] Tambah Upstream Source Baru",
                    "[2] Hapus Upstream Source",
                    "[0] Kembali",
                ],
            ).ask()

            if choice is None or choice.startswith("[0]"):
                break
            elif choice.startswith("[1]"):
                name = questionary.text("Masukkan Nama Source:").ask()
                url = questionary.text("Masukkan URL Source:").ask()
                stype = questionary.select("Pilih Tipe Source:", choices=["base64", "raw_lines", "raw_extract", "clash_yaml"]).ask()
                if name and url:
                    sources.append({"name": name.strip(), "url": url.strip(), "type": stype or "raw_lines"})
                    self._save_sources(sources)
                    self.views.render_status_panel("SUCCESS", f"Source '{name}' berhasil ditambahkan.", style="green")
            elif choice.startswith("[2]"):
                if not sources:
                    self.views.render_status_panel("WARNING", "Tidak ada source untuk dihapus.", style="yellow")
                    continue
                del_choices = [f"[{idx}] {s.get('name')}" for idx, s in enumerate(sources, 1)]
                del_choices.append("[0] Batal")
                sel_del = questionary.select("Pilih Source yang ingin dihapus:", choices=del_choices).ask()
                if sel_del and not sel_del.startswith("[0]"):
                    d_idx = int(sel_del.split("]")[0].replace("[", "")) - 1
                    removed = sources.pop(d_idx)
                    self._save_sources(sources)
                    self.views.render_status_panel("SUCCESS", f"Source '{removed.get('name')}' dihapus.", style="green")

    def handle_exit(self) -> None:
        """Clean shutdown handler: stops daemon process and scheduler."""
        if self.runner.is_running():
            self.runner.stop()
        if self.scheduler.is_running():
            self.scheduler.stop()
        self.views.render_status_panel("EXIT", "Terima kasih telah menggunakan Proxy Scraper & Checker TUI.", style="cyan")

    def run(self) -> None:
        """Main interactive menu loop."""
        while True:
            self.views.render_banner()
            choice = questionary.select(
                "Pilih menu utama:",
                choices=[
                    "[1] Scrape & Auto-Check Semua Sumber (One-Click Update)",
                    "[2] Kumpulkan Proxy (Scrape Publik / Input Custom URL / File / Paste)",
                    "[3] Jalankan Health Check & Filter Proxy Aktif",
                    "[4] Lihat Daftar Proxy Aktif (Tabel Rapi, Detail & Pagination)",
                    "[5] Ekspor Proxy (Raw Links, Base64 Sub, Clash/Mihomo, Sing-box)",
                    "[6] Jalankan Local Proxy Server (SOCKS5/HTTP di Localhost)",
                    "[7] Auto-Scheduler (Pengecekan Berkala di Background)",
                    "[8] Pengaturan & Kelola Sumber Upstream",
                    "[0] Keluar",
                ],
            ).ask()

            if choice is None or choice.startswith("[0]"):
                self.handle_exit()
                break
            elif choice.startswith("[1]"):
                self.handle_scrape_and_check_all()
            elif choice.startswith("[2]"):
                self.handle_collect_proxies()
            elif choice.startswith("[3]"):
                self.handle_health_check()
            elif choice.startswith("[4]"):
                self.handle_view_proxies()
            elif choice.startswith("[5]"):
                self.handle_export()
            elif choice.startswith("[6]"):
                self.handle_local_runner()
            elif choice.startswith("[7]"):
                self.handle_scheduler()
            elif choice.startswith("[8]"):
                self.handle_settings()
