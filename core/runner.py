import os
import json
import time
import socket
import tempfile
import subprocess
from typing import Dict, Any, Optional

from core.models import ProxyNode
from core.binary_manager import BinaryManager


class LocalProxyRunner:
    """Manages the local sing-box daemon process for forwarding traffic through a selected proxy node."""

    def __init__(self, bin_path: Optional[str] = None) -> None:
        self.bin_path = bin_path
        self.process: Optional[subprocess.Popen] = None
        self.current_node: Optional[ProxyNode] = None
        self.socks_port: int = 1080
        self.http_port: int = 1081
        self.config_path: Optional[str] = None

    def _generate_runner_config(
        self, node: ProxyNode, socks_port: int = 1080, http_port: int = 1081
    ) -> Dict[str, Any]:
        """Generates a sing-box JSON configuration with SOCKS5 and HTTP inbounds."""
        outbound = dict(node.config) if node.config else {}
        if "tag" not in outbound:
            outbound["tag"] = "proxy-out"

        return {
            "log": {
                "level": "warn",
                "disabled": False,
            },
            "inbounds": [
                {
                    "type": "socks",
                    "tag": "socks-in",
                    "listen": "127.0.0.1",
                    "listen_port": socks_port,
                },
                {
                    "type": "http",
                    "tag": "http-in",
                    "listen": "127.0.0.1",
                    "listen_port": http_port,
                },
            ],
            "outbounds": [outbound],
        }

    def _check_port_open(
        self,
        host_or_port: Any = "127.0.0.1",
        port: Optional[int] = None,
        timeout: float = 0.5,
    ) -> bool:
        """Checks if a TCP port is open and listening."""
        if isinstance(host_or_port, int):
            actual_host = "127.0.0.1"
            actual_port = host_or_port
        else:
            actual_host = str(host_or_port)
            actual_port = port if port is not None else 1080

        try:
            with socket.create_connection((actual_host, actual_port), timeout=timeout):
                return True
        except (socket.error, OSError):
            return False

    def start(self, node: ProxyNode, socks_port: int = 1080, http_port: int = 1081) -> bool:
        """Starts the sing-box background process for the target proxy node."""
        if self.is_running():
            self.stop()

        bin_exec = self.bin_path
        if not bin_exec or not os.path.exists(bin_exec):
            try:
                bm = BinaryManager()
                bin_exec = bm.ensure_singbox()
            except Exception:
                bin_exec = self.bin_path or "sing-box"

        cfg = self._generate_runner_config(node, socks_port=socks_port, http_port=http_port)

        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(cfg, f, indent=2)
                self.config_path = f.name
        except Exception:
            return False

        try:
            self.process = subprocess.Popen(
                [bin_exec, "run", "-c", self.config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            if self.config_path and os.path.exists(self.config_path):
                os.remove(self.config_path)
                self.config_path = None
            return False

        time.sleep(0.2)

        if self.process.poll() is not None:
            if self.config_path and os.path.exists(self.config_path):
                os.remove(self.config_path)
                self.config_path = None
            self.process = None
            return False

        if not self._check_port_open(socks_port):
            self.stop()
            return False

        self.current_node = node
        self.socks_port = socks_port
        self.http_port = http_port
        return True

    def stop(self) -> bool:
        """Stops the running sing-box process and cleans up temporary config files."""
        if self.process:
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2.0)
                except Exception:
                    try:
                        self.process.kill()
                        self.process.wait(timeout=1.0)
                    except Exception:
                        pass
            self.process = None

        if self.config_path and os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except OSError:
                pass
            self.config_path = None

        self.current_node = None
        return True

    def is_running(self) -> bool:
        """Returns True if the proxy process is alive."""
        return self.process is not None and self.process.poll() is None

    def get_status(self) -> Dict[str, Any]:
        """Returns status dictionary of the local proxy runner."""
        if self.is_running():
            node_data = self.current_node.to_dict() if hasattr(self.current_node, "to_dict") else self.current_node
            return {
                "status": "RUNNING",
                "node": node_data,
                "socks_port": self.socks_port,
                "http_port": self.http_port,
                "pid": self.process.pid if self.process else None,
            }
        return {
            "status": "STOPPED",
            "node": None,
            "socks_port": self.socks_port,
            "http_port": self.http_port,
            "pid": None,
        }
