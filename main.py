#!/usr/bin/env python3
"""CLI Entry Point for Proxy Scraper & Checker TUI."""

import sys
import argparse
from tui.menu import TUIMenu
from core.exporter import ProxyExporter


def main():
    parser = argparse.ArgumentParser(
        description="Proxy Scraper & Checker TUI - Automated multi-protocol proxy manager"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run scraping and health check in non-interactive headless mode and export results",
    )
    parser.add_argument(
        "--check-now",
        action="store_true",
        help="Run one-click scrape and health check immediately",
    )
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help="Start background scheduler daemon before entering menu",
    )
    parser.add_argument(
        "--export-dir",
        type=str,
        default="data/exports",
        help="Directory to save export files in headless mode",
    )

    args = parser.parse_args()

    menu = TUIMenu()

    try:
        if args.headless:
            menu.console.print("[bold cyan]Running in Headless Mode...[/bold cyan]")
            alive_nodes = menu.handle_scrape_and_check_all()
            if alive_nodes:
                exporter = ProxyExporter()
                exporter.export_raw(alive_nodes, f"{args.export_dir}/proxies_raw.txt")
                exporter.export_base64(alive_nodes, f"{args.export_dir}/proxies_base64.txt")
                exporter.export_clash(alive_nodes, f"{args.export_dir}/clash.yaml")
                exporter.export_singbox(alive_nodes, f"{args.export_dir}/singbox.json")
                menu.console.print(
                    f"[bold green]Headless task complete. Exported {len(alive_nodes)} active nodes.[/bold green]"
                )
            sys.exit(0)

        if args.check_now:
            menu.handle_scrape_and_check_all()

        if args.scheduler:
            cfg = menu._load_config()
            interval = float(cfg.get("auto_update_interval_minutes", 60))
            menu.scheduler.start(
                interval_minutes=interval,
                task_callback=menu.handle_scrape_and_check_all,
            )

        # Launch interactive menu loop if not headless
        menu.run()

    except KeyboardInterrupt:
        menu.console.print(
            "\n[bold yellow][!] Program dihentikan oleh pengguna (Ctrl+C). Exiting...[/bold yellow]"
        )
        menu.handle_exit()
        sys.exit(0)
    except Exception as e:
        menu.console.print(f"\n[bold red][!] Error fatal: {e}[/bold red]")
        menu.handle_exit()
        sys.exit(1)


if __name__ == "__main__":
    main()
