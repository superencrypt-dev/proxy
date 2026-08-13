import os
import json
import time
import uuid
import socket
import inspect
import tempfile
import asyncio
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Callable, Dict, Any

import aiohttp

from core.models import ProxyNode
from core.geoip import GeoIPResolver
from core.binary_manager import BinaryManager


class ProxyChecker:
    """Concurrent Health Checker Engine using sing-box subprocess instances."""

    def __init__(
        self,
        concurrency: int = 10,
        timeout: float = 5.0,
        test_url: str = "http://cp.cloudflare.com/generate_204",
        fallback_test_url: str = "https://www.gstatic.com/generate_204",
        binary_path: Optional[str] = None,
        enable_fast_ping: bool = False,
        fast_ping_timeout: float = 1.0,
    ) -> None:
        self.concurrency = max(1, concurrency)
        # Normalize timeout if specified in milliseconds (e.g., 3000 -> 3.0 seconds)
        self.timeout = timeout / 1000.0 if timeout > 50 else float(timeout)
        self.test_url = test_url
        self.fallback_test_url = fallback_test_url
        self.binary_path = binary_path
        self.enable_fast_ping = enable_fast_ping
        self.fast_ping_timeout = (
            fast_ping_timeout / 1000.0 if fast_ping_timeout > 50 else float(fast_ping_timeout)
        )
        self.geoip_resolver = GeoIPResolver()

    def _find_free_port(self) -> int:
        """Finds an available ephemeral port on 127.0.0.1."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _build_temp_config(self, node: ProxyNode, inbound_port: int) -> Dict[str, Any]:
        """Generates a minimal sing-box JSON configuration for testing node connectivity."""
        outbound = dict(node.config) if node.config else {}
        if "tag" not in outbound:
            outbound["tag"] = "proxy-out"

        return {
            "log": {
                "level": "warn",
                "disabled": True,
            },
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": inbound_port,
                }
            ],
            "outbounds": [outbound],
        }

    async def _fast_tcp_ping(self, host: str, port: int, timeout: float) -> bool:
        """Fast TCP handshake pre-flight probe."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _wait_for_port(self, port: int, timeout: float = 1.0) -> bool:
        """Polls local inbound port until it is accepting connections or timeout occurs."""
        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < timeout:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                return True
            except (OSError, ConnectionRefusedError):
                await asyncio.sleep(0.02)
        return False

    async def _http_get_check(self, inbound_port: int, url: str, timeout: float) -> float:
        """Performs HTTP GET request via local proxy and returns round-trip latency in milliseconds."""
        proxy_url = f"http://127.0.0.1:{inbound_port}"
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        start_time = time.perf_counter()
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(url, proxy=proxy_url, allow_redirects=True) as response:
                if response.status in (200, 204, 301, 302):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return round(elapsed_ms, 2)
                else:
                    raise Exception(f"HTTP GET returned non-success status code {response.status}")

    async def check_single_node(
        self, node: ProxyNode, binary_path: Optional[str] = None
    ) -> ProxyNode:
        """Checks health and latency of a single proxy node using sing-box subprocess."""
        now_str = datetime.now(timezone.utc).isoformat()
        bin_path = binary_path or self.binary_path
        if not bin_path:
            bin_path = BinaryManager().ensure_singbox()

        if self.enable_fast_ping:
            ping_ok = await self._fast_tcp_ping(node.server, node.port, self.fast_ping_timeout)
            if not ping_ok:
                node.is_alive = False
                node.latency = -1
                node.last_checked = now_str
                return node

        inbound_port = self._find_free_port()
        cfg = self._build_temp_config(node, inbound_port)

        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, f"sb_{uuid.uuid4().hex[:8]}.json")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                bin_path,
                "run",
                "-c",
                temp_file,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            ready = await self._wait_for_port(inbound_port, timeout=1.0)
            if not ready or proc.returncode is not None:
                node.is_alive = False
                node.latency = -1
                node.last_checked = now_str
                return node

            latency = None
            try:
                latency = await self._http_get_check(inbound_port, self.test_url, timeout=self.timeout)
            except Exception:
                if self.fallback_test_url:
                    try:
                        latency = await self._http_get_check(
                            inbound_port, self.fallback_test_url, timeout=self.timeout
                        )
                    except Exception:
                        latency = None

            if latency is not None and latency >= 0:
                node.is_alive = True
                node.latency = int(round(latency))
                node.last_checked = now_str
            else:
                node.is_alive = False
                node.latency = -1
                node.last_checked = now_str
        except Exception:
            node.is_alive = False
            node.latency = -1
            node.last_checked = now_str
        finally:
            if proc is not None:
                try:
                    if proc.returncode is None:
                        proc.terminate()
                        try:
                            await asyncio.wait_for(proc.wait(), timeout=0.5)
                        except asyncio.TimeoutError:
                            proc.kill()
                            await proc.wait()
                except Exception:
                    pass
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

        return node

    async def check_nodes(
        self,
        nodes: List[ProxyNode],
        on_progress: Optional[Callable[[int, int, ProxyNode], None]] = None,
    ) -> Tuple[List[ProxyNode], List[ProxyNode]]:
        """Checks multiple proxy nodes concurrently.

        Args:
            nodes: List of ProxyNode objects.
            on_progress: Optional progress callback(completed_count, total_count, last_checked_node).

        Returns:
            Tuple of (alive_nodes, dead_nodes).
        """
        if not nodes:
            return [], []

        sem = asyncio.Semaphore(self.concurrency)
        completed_count = 0
        total_count = len(nodes)
        lock = asyncio.Lock()

        async def _worker(node: ProxyNode) -> ProxyNode:
            nonlocal completed_count
            async with sem:
                res_node = await self.check_single_node(node)
                if res_node.is_alive:
                    cc, name = await self.geoip_resolver.resolve_country_async(res_node.server)
                    res_node.country_code = cc
                    res_node.country_name = name
                    res_node.name = self.geoip_resolver.standardize_name(res_node)

                async with lock:
                    completed_count += 1
                    if on_progress:
                        try:
                            if inspect.iscoroutinefunction(on_progress):
                                await on_progress(completed_count, total_count, res_node)
                            else:
                                on_progress(completed_count, total_count, res_node)
                        except Exception:
                            pass
                return res_node

        tasks = [_worker(node) for node in nodes]
        results = await asyncio.gather(*tasks)

        alive_nodes = [n for n in results if n.is_alive]
        dead_nodes = [n for n in results if not n.is_alive]

        return alive_nodes, dead_nodes
