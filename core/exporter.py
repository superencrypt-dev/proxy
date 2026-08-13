import os
import copy
import json
import base64
import yaml
from typing import List, Optional, Dict, Any
from core.models import ProxyNode


class ProxyExporter:
    """Multi-format proxy exporter supporting raw links, base64 subscriptions,
    Clash Meta / Mihomo YAML, and Sing-box JSON format.
    """

    def filter_nodes(
        self,
        nodes: List[ProxyNode],
        country: Optional[str] = None,
        protocol: Optional[str] = None,
        max_latency: Optional[int] = None,
    ) -> List[ProxyNode]:
        """Filters nodes by country code/name, protocol, and maximum latency."""
        filtered = []
        for node in nodes:
            if country:
                c_str = country.strip().upper()
                c_name = country.strip().lower()
                node_cc = (node.country_code or "").strip().upper()
                node_cn = (node.country_name or "").strip().lower()
                if node_cc != c_str and c_name not in node_cn:
                    continue

            if protocol:
                p_str = protocol.strip().lower()
                node_p = (node.protocol or "").strip().lower()
                if node_p != p_str:
                    continue

            if max_latency is not None and max_latency > 0:
                if node.latency <= 0 or node.latency > max_latency:
                    continue

            filtered.append(node)
        return filtered

    def _ensure_dir(self, file_path: str) -> None:
        """Ensures that the parent directory for file_path exists."""
        dir_name = os.path.dirname(os.path.abspath(file_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def export_raw(self, nodes: List[ProxyNode], output_path: str) -> str:
        """Writes clean raw URI links line by line to output_path."""
        self._ensure_dir(output_path)
        raw_uris = [n.raw_uri for n in nodes if n.raw_uri]
        content = "\n".join(raw_uris)
        if content:
            content += "\n"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path

    def export_base64(self, nodes: List[ProxyNode], output_path: str) -> str:
        """Encodes raw URI links in standard base64 subscription format."""
        self._ensure_dir(output_path)
        raw_uris = [n.raw_uri for n in nodes if n.raw_uri]
        plain_text = "\n".join(raw_uris)
        b64_encoded = base64.b64encode(plain_text.encode("utf-8")).decode("utf-8")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(b64_encoded + "\n")
        return output_path

    def _node_to_clash_proxy(self, node: ProxyNode) -> Dict[str, Any]:
        """Converts a ProxyNode into a Clash Meta / Mihomo compatible proxy dictionary."""
        cfg = node.config if isinstance(node.config, dict) else {}
        proto = (node.protocol or cfg.get("type", "")).lower()

        clash_type = proto
        if proto in ("shadowsocks", "ss"):
            clash_type = "ss"
        elif proto in ("hysteria2", "hy2"):
            clash_type = "hysteria2"
        elif proto in ("hysteria", "hy1"):
            clash_type = "hysteria"

        p_dict: Dict[str, Any] = {
            "name": node.name or cfg.get("tag", "Proxy"),
            "type": clash_type,
            "server": node.server or cfg.get("server", ""),
            "port": int(node.port or cfg.get("server_port", 443)),
        }

        if clash_type == "trojan":
            p_dict["password"] = cfg.get("password", "")
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["sni"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))
                if tls_cfg.get("alpn"):
                    p_dict["alpn"] = tls_cfg["alpn"]
            if cfg.get("transport"):
                t_cfg = cfg["transport"]
                t_type = t_cfg.get("type", "")
                if t_type == "ws":
                    p_dict["network"] = "ws"
                    ws_opts = {}
                    if t_cfg.get("path"):
                        ws_opts["path"] = t_cfg["path"]
                    if t_cfg.get("headers"):
                        ws_opts["headers"] = t_cfg["headers"]
                    if ws_opts:
                        p_dict["ws-opts"] = ws_opts
                elif t_type == "grpc":
                    p_dict["network"] = "grpc"
                    if t_cfg.get("service_name"):
                        p_dict["grpc-opts"] = {"grpc-service-name": t_cfg["service_name"]}

        elif clash_type == "vless":
            p_dict["uuid"] = cfg.get("uuid", "")
            p_dict["cipher"] = "auto"
            if cfg.get("flow"):
                p_dict["flow"] = cfg["flow"]
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["tls"] = True
                p_dict["servername"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))
                if tls_cfg.get("reality"):
                    r_cfg = tls_cfg["reality"]
                    ropts = {}
                    if r_cfg.get("public_key"):
                        ropts["public-key"] = r_cfg["public_key"]
                    if r_cfg.get("short_id"):
                        ropts["short-id"] = r_cfg["short_id"]
                    if ropts:
                        p_dict["reality-opts"] = ropts
                if tls_cfg.get("utls"):
                    p_dict["client-fingerprint"] = tls_cfg["utls"].get("fingerprint", "chrome")
            if cfg.get("transport"):
                t_cfg = cfg["transport"]
                t_type = t_cfg.get("type", "")
                if t_type == "ws":
                    p_dict["network"] = "ws"
                    ws_opts = {}
                    if t_cfg.get("path"):
                        ws_opts["path"] = t_cfg["path"]
                    if t_cfg.get("headers"):
                        ws_opts["headers"] = t_cfg["headers"]
                    if ws_opts:
                        p_dict["ws-opts"] = ws_opts
                elif t_type == "grpc":
                    p_dict["network"] = "grpc"
                    if t_cfg.get("service_name"):
                        p_dict["grpc-opts"] = {"grpc-service-name": t_cfg["service_name"]}

        elif clash_type == "vmess":
            p_dict["uuid"] = cfg.get("uuid", "")
            p_dict["alterId"] = int(cfg.get("alter_id", 0))
            p_dict["cipher"] = cfg.get("security", "auto")
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["tls"] = True
                p_dict["servername"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))
            if cfg.get("transport"):
                t_cfg = cfg["transport"]
                t_type = t_cfg.get("type", "")
                if t_type == "ws":
                    p_dict["network"] = "ws"
                    ws_opts = {}
                    if t_cfg.get("path"):
                        ws_opts["path"] = t_cfg["path"]
                    if t_cfg.get("headers"):
                        ws_opts["headers"] = t_cfg["headers"]
                    if ws_opts:
                        p_dict["ws-opts"] = ws_opts

        elif clash_type == "ss":
            p_dict["cipher"] = cfg.get("method", "aes-256-gcm")
            p_dict["password"] = cfg.get("password", "")
            if cfg.get("plugin"):
                p_dict["plugin"] = cfg["plugin"]
                if cfg.get("plugin_opts"):
                    p_dict["plugin-opts"] = cfg["plugin_opts"]

        elif clash_type == "tuic":
            p_dict["uuid"] = cfg.get("uuid", "")
            if cfg.get("password"):
                p_dict["password"] = cfg["password"]
            p_dict["ip"] = node.server
            if cfg.get("congestion_control"):
                p_dict["congestion-controller"] = cfg["congestion_control"]
            if cfg.get("udp_relay_mode"):
                p_dict["udp-relay-mode"] = cfg["udp_relay_mode"]
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["sni"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))

        elif clash_type == "hysteria2":
            if cfg.get("auth"):
                p_dict["password"] = cfg["auth"]
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["sni"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))
            if cfg.get("obfs"):
                obfs = cfg["obfs"]
                if isinstance(obfs, dict):
                    if obfs.get("type"):
                        p_dict["obfs"] = obfs["type"]
                    if obfs.get("password"):
                        p_dict["obfs-password"] = obfs["password"]

        elif clash_type == "hysteria":
            if cfg.get("auth_str"):
                p_dict["auth-str"] = cfg["auth_str"]
            if cfg.get("up_mbps"):
                p_dict["up"] = cfg["up_mbps"]
            if cfg.get("down_mbps"):
                p_dict["down"] = cfg["down_mbps"]
            if cfg.get("obfs"):
                p_dict["obfs"] = cfg["obfs"]
            if cfg.get("tls"):
                tls_cfg = cfg["tls"]
                p_dict["sni"] = tls_cfg.get("server_name", node.server)
                p_dict["skip-cert-verify"] = bool(tls_cfg.get("insecure", False))

        return p_dict

    def export_clash(self, nodes: List[ProxyNode], output_path: str) -> str:
        """Generates complete Clash Meta / Mihomo YAML configuration."""
        self._ensure_dir(output_path)
        proxies = [self._node_to_clash_proxy(n) for n in nodes]
        proxy_names = [p["name"] for p in proxies]
        target_list = proxy_names if proxy_names else ["DIRECT"]

        proxy_groups = [
            {
                "name": "Auto-Select",
                "type": "url-test",
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": list(target_list),
            },
            {
                "name": "Fallback",
                "type": "fallback",
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": 300,
                "proxies": list(target_list),
            },
            {
                "name": "Manual Select",
                "type": "select",
                "proxies": ["Auto-Select", "Fallback"] + list(target_list),
            },
            {
                "name": "Load-Balance",
                "type": "load-balance",
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": 300,
                "proxies": list(target_list),
            },
        ]

        rules = [
            "GEOIP,LAN,DIRECT",
            "MATCH,Manual Select",
        ]

        clash_config = {
            "proxies": proxies,
            "proxy-groups": proxy_groups,
            "rules": rules,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(clash_config, f, sort_keys=False, allow_unicode=True)

        return output_path

    def export_singbox(self, nodes: List[ProxyNode], output_path: str) -> str:
        """Generates complete Sing-box JSON configuration."""
        self._ensure_dir(output_path)
        proxy_outbounds = []
        proxy_tags = []

        for node in nodes:
            if node.config and isinstance(node.config, dict):
                outbound_cfg = copy.deepcopy(node.config)
            else:
                outbound_cfg = {
                    "type": node.protocol,
                    "server": node.server,
                    "server_port": int(node.port),
                }
            outbound_cfg["tag"] = node.name
            proxy_outbounds.append(outbound_cfg)
            proxy_tags.append(node.name)

        select_targets = ["auto"] + proxy_tags if proxy_tags else ["direct"]
        auto_targets = proxy_tags if proxy_tags else ["direct"]

        outbounds = [
            {
                "type": "selector",
                "tag": "select",
                "outbounds": select_targets,
                "default": select_targets[0],
            },
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": auto_targets,
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": "3m",
                "tolerance": 50,
            },
        ]
        outbounds.extend(proxy_outbounds)
        outbounds.append({"type": "direct", "tag": "direct"})
        outbounds.append({"type": "block", "tag": "block"})

        singbox_config = {
            "log": {
                "level": "info",
                "timestamp": True,
            },
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": 2080,
                }
            ],
            "outbounds": outbounds,
            "route": {
                "rules": [
                    {
                        "protocol": "dns",
                        "outbound": "select",
                    },
                    {
                        "ip_is_private": True,
                        "outbound": "direct",
                    },
                ],
                "auto_detect_interface": True,
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(singbox_config, f, indent=2, ensure_ascii=True)

        return output_path
