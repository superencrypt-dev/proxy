"""Rich TUI Views and Layout Component Renderers (Strictly No Emoji)."""

from typing import List, Optional, Dict, Any
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)

from core.models import ProxyNode
from tui.themes import (
    ASCII_BANNER,
    STYLE_HEADER,
    STYLE_BORDER,
    STYLE_MUTED,
)


class TUIViews:
    """Rich-based UI component renderer with clean text formatting."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def render_banner(self, console: Optional[Console] = None) -> None:
        """Render the clean ASCII text banner without any emojis."""
        c = console or self.console
        panel = Panel(
            Text(ASCII_BANNER, style=STYLE_HEADER),
            border_style=STYLE_BORDER,
            box=box.ASCII,
            expand=False,
        )
        c.print(panel)

    def render_proxy_table(
        self,
        nodes: List[ProxyNode],
        title: str = "DAFTAR PROXY AKTIF",
        page: int = 1,
        page_size: int = 20,
        console: Optional[Console] = None,
    ) -> None:
        """Render rich table listing active proxy nodes with pagination."""
        c = console or self.console

        if not nodes:
            panel = Panel(
                Text("Tidak ada proxy untuk ditampilkan.", style=STYLE_MUTED),
                title=f"[bold cyan]{title}[/bold cyan]",
                border_style=STYLE_BORDER,
                box=box.ASCII,
            )
            c.print(panel)
            return

        table = Table(
            title=title,
            title_style=STYLE_HEADER,
            box=box.ASCII,
            border_style=STYLE_BORDER,
            header_style="bold cyan",
            expand=True,
        )

        table.add_column("No", justify="right", style="cyan", no_wrap=True)
        table.add_column("Country", justify="center", style="bold yellow", no_wrap=True)
        table.add_column("Protocol", justify="center", style="green", no_wrap=True)
        table.add_column("Server", justify="left", no_wrap=True)
        table.add_column("Port", justify="right", style="cyan", no_wrap=True)
        table.add_column("Latency", justify="right", no_wrap=True)
        table.add_column("Status", justify="center", no_wrap=True)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_nodes = nodes[start_idx:end_idx]

        for idx, node in enumerate(page_nodes, start=start_idx + 1):
            cc = f"[{node.country_code or 'XX'}]"
            proto = node.protocol.upper() if node.protocol else "UNKNOWN"
            server = node.server or "-"
            port = str(node.port)

            if node.latency > 0:
                if node.latency < 100:
                    lat_str = f"[bold green]{node.latency}ms[/bold green]"
                elif node.latency < 300:
                    lat_str = f"[bold yellow]{node.latency}ms[/bold yellow]"
                else:
                    lat_str = f"[bold red]{node.latency}ms[/bold red]"
            else:
                lat_str = "[dim white]TIMEOUT[/dim white]"

            if node.is_alive:
                status_str = "[bold green][ONLINE][/bold green]"
            else:
                status_str = "[bold red][OFFLINE][/bold red]"

            table.add_row(str(idx), cc, proto, server, port, lat_str, status_str)

        c.print(table)

        total_pages = max(1, (len(nodes) + page_size - 1) // page_size)
        c.print(
            f"[dim white]Halaman {page}/{total_pages} (Total: {len(nodes)} node, Menampilkan {len(page_nodes)})[/dim white]"
        )

    def render_summary(
        self,
        total: int,
        alive: int,
        dead: int,
        duration_sec: float,
        console: Optional[Console] = None,
    ) -> None:
        """Render summary stats panel."""
        c = console or self.console
        rate = (alive / total * 100.0) if total > 0 else 0.0

        summary_text = Text()
        summary_text.append("Total Node Scraped : ", style="bold cyan")
        summary_text.append(f"{total}\n", style="bold white")
        summary_text.append("Proxy Aktif (Alive) : ", style="bold green")
        summary_text.append(f"{alive}\n", style="bold green")
        summary_text.append("Proxy Mati (Dead)   : ", style="bold red")
        summary_text.append(f"{dead}\n", style="bold red")
        summary_text.append("Durasi Check        : ", style="bold yellow")
        summary_text.append(f"{duration_sec:.2f} detik\n", style="bold yellow")
        summary_text.append("Success Rate        : ", style="bold cyan")
        summary_text.append(
            f"{rate:.1f}%", style="bold green" if rate > 50 else "bold yellow"
        )

        panel = Panel(
            summary_text,
            title="[bold cyan]RINGKASAN HEALTH CHECK[/bold cyan]",
            border_style=STYLE_BORDER,
            box=box.ASCII,
        )
        c.print(panel)

    def render_status_panel(
        self,
        title: str,
        message: str,
        style: str = "cyan",
        console: Optional[Console] = None,
    ) -> None:
        """Render a notification status panel with specified title and style."""
        c = console or self.console
        panel = Panel(
            Text(message, style="white"),
            title=f"[bold {style}]{title}[/bold {style}]",
            border_style=style,
            box=box.ASCII,
        )
        c.print(panel)

    def render_runner_status(
        self,
        runner_status: Dict[str, Any],
        console: Optional[Console] = None,
    ) -> None:
        """Render local proxy runner status dashboard panel."""
        c = console or self.console
        is_running = runner_status.get("running", False)

        content = Text()
        if is_running:
            content.append("Status Process    : ", style="bold cyan")
            content.append("[AKTIF / RUNNING]\n", style="bold green")
            content.append("PID               : ", style="bold cyan")
            content.append(f"{runner_status.get('pid', '-')}\n", style="white")
            content.append("Node Aktif        : ", style="bold cyan")
            content.append(
                f"{runner_status.get('node_name', '-')}\n", style="bold yellow"
            )
            content.append("Target Server     : ", style="bold cyan")
            content.append(
                f"{runner_status.get('server', '-')}:{runner_status.get('port', '-')}\n",
                style="white",
            )
            content.append("Protocol          : ", style="bold cyan")
            content.append(
                f"{str(runner_status.get('protocol', '-')).upper()}\n", style="green"
            )
            content.append("SOCKS5 Inbound    : ", style="bold cyan")
            content.append(
                f"127.0.0.1:{runner_status.get('socks_port', 1080)}\n",
                style="bold green",
            )
            content.append("HTTP Inbound      : ", style="bold cyan")
            content.append(
                f"127.0.0.1:{runner_status.get('http_port', 1081)}", style="bold green"
            )
            border = "green"
        else:
            content.append("Status Process    : ", style="bold cyan")
            content.append("[TIDAK AKTIF / STOPPED]\n", style="bold red")
            content.append("Keterangan        : ", style="bold cyan")
            content.append(
                "Local proxy runner server sedang tidak berjalan.", style="dim white"
            )
            border = "red"

        panel = Panel(
            content,
            title="[bold cyan]STATUS LOCAL PROXY RUNNER[/bold cyan]",
            border_style=border,
            box=box.ASCII,
        )
        c.print(panel)

    def render_scheduler_status(
        self,
        sched_status: Dict[str, Any],
        console: Optional[Console] = None,
    ) -> None:
        """Render scheduler status panel."""
        c = console or self.console
        is_active = sched_status.get("active", False)

        content = Text()
        if is_active:
            content.append("Status Scheduler  : ", style="bold cyan")
            content.append("[AKTIF]\n", style="bold green")
            content.append("Interval Auto-Run : ", style="bold cyan")
            content.append(
                f"{sched_status.get('interval_minutes', 60)} menit\n",
                style="bold yellow",
            )
            content.append("Terakhir Dijalankan: ", style="bold cyan")
            content.append(
                f"{sched_status.get('last_run', 'Belum Pernah')}\n", style="white"
            )
            content.append("Jadwal Berikutnya : ", style="bold cyan")
            content.append(f"{sched_status.get('next_run', '-')}", style="white")
            border = "green"
        else:
            content.append("Status Scheduler  : ", style="bold cyan")
            content.append("[TIDAK AKTIF]\n", style="bold yellow")
            content.append("Keterangan        : ", style="bold cyan")
            content.append(
                "Auto-scheduler background job sedang nonaktif.", style="dim white"
            )
            border = "yellow"

        panel = Panel(
            content,
            title="[bold cyan]STATUS AUTO-SCHEDULER[/bold cyan]",
            border_style=border,
            box=box.ASCII,
        )
        c.print(panel)

    def create_progress_bar(self, console: Optional[Console] = None) -> Progress:
        """Return rich Progress instance for live check progress without emojis."""
        c = console or self.console
        return Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(bar_width=40),
            TaskProgressColumn("[bold yellow]{task.percentage:>3.0f}%[/bold yellow]"),
            TextColumn("[green]{task.completed}/{task.total}[/green]"),
            TimeRemainingColumn(),
            console=c,
            expand=False,
        )
