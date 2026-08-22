import os
import sys
import time
import socket
import threading
import psutil
from typing import List, Dict, Optional
from zeroconf import Zeroconf, ServiceInfo, IPVersion

class MDNSAdvertiser:
    """Multi-Interface mDNS Broadcaster for AirPlay & RAOP.
    Ensures seamless discovery across Wi-Fi, Windows Mobile Hotspot (192.168.137.x),
    and iPhone Personal Hotspot (172.20.10.x / 192.168.43.x).
    """

    def __init__(self):
        self.server_name: str = "CastScreen-PC"
        self.port: int = 7000
        self.mac_address: str = self._get_mac_address()
        self.mac_hex: str = self.mac_address.replace(":", "")
        self.zeroconf_instances: Dict[str, Zeroconf] = {}
        self.registered_services: Dict[str, List[ServiceInfo]] = {}
        self.is_running: bool = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @staticmethod
    def _get_mac_address() -> str:
        """Get the primary physical MAC address."""
        try:
            stats = psutil.net_if_stats()
            for iface, addrs in psutil.net_if_addrs().items():
                if stats.get(iface) and stats[iface].isup:
                    for addr in addrs:
                        if addr.family == psutil.AF_LINK and addr.address and ":" in addr.address:
                            # Avoid 00:00:00...
                            if not addr.address.startswith("00:00:00"):
                                return addr.address.upper()
        except Exception:
            pass
        return "4C:1D:96:BA:B1:75"

    @staticmethod
    def get_active_ipv4_list() -> List[str]:
        """Get all valid active IPv4 addresses (Wi-Fi, Hotspot, Ethernet)."""
        valid_ips = []
        try:
            stats = psutil.net_if_stats()
            for iface, addrs in psutil.net_if_addrs().items():
                if not stats.get(iface) or not stats[iface].isup:
                    continue
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # Skip loopback, APIPA, and virtual WSL networks from default advertisement
                        if not ip.startswith("127.") and not ip.startswith("169.254.") and not ip.startswith("172.27."):
                            valid_ips.append(ip)
        except Exception:
            pass
        
        # If no IP found, fallback to any non-loopback IP
        if not valid_ips:
            try:
                for iface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                            valid_ips.append(addr.address)
            except Exception:
                pass

        return list(set(valid_ips))

    def _build_service_infos(self, ip: str) -> List[ServiceInfo]:
        """Build AirPlay, AirPlayScreenCapture, and RAOP service records for a specific IP."""
        addr_bytes = [socket.inet_aton(ip)]
        
        airplay_props = {
            'deviceid': self.mac_address,
            'features': '0x5A7FFFF7,0x1E',
            'flags': '0x4',
            'model': 'AppleTV3,2',
            'pk': 'b07727d6f6cd6e08b58ede525ec3cdeaa252ad9f683feb212ef8a205246554e7',
            'pi': '2e388006-13ba-4041-9a67-25dd4a43d536',
            'srcvers': '220.68',
            'vv': '2'
        }

        raop_props = {
            'ch': '2',
            'cn': '0,1,2,3',
            'da': 'true',
            'et': '0,3,5',
            'ft': '0x5A7FFFF7,0x1E',
            'md': '0,1,2',
            'am': 'AppleTV3,2',
            'pk': 'b07727d6f6cd6e08b58ede525ec3cdeaa252ad9f683feb212ef8a205246554e7',
            'sf': '0x4',
            'sm': 'false',
            'sv': 'false',
            'tp': 'UDP',
            'vn': '65537',
            'vs': '220.68',
            'vv': '2'
        }

        # 1. _airplay._tcp.local. (AirPlay Mirroring & Control)
        s_airplay = ServiceInfo(
            '_airplay._tcp.local.',
            f'{self.server_name}._airplay._tcp.local.',
            addresses=addr_bytes,
            port=self.port,
            properties=airplay_props,
            server=f'{self.server_name}.local.'
        )

        # 2. _raop._tcp.local. (Remote Audio Output Protocol & Streaming)
        s_raop = ServiceInfo(
            '_raop._tcp.local.',
            f'{self.mac_hex}@{self.server_name}._raop._tcp.local.',
            addresses=addr_bytes,
            port=self.port,
            properties=raop_props,
            server=f'{self.server_name}.local.'
        )

        return [s_airplay, s_raop]

    def _register_on_ip(self, ip: str):
        """Register services bound specifically to a network interface."""
        try:
            if ip in self.zeroconf_instances:
                return

            zc = Zeroconf(interfaces=[ip])
            services = self._build_service_infos(ip)
            for s in services:
                zc.register_service(s)

            self.zeroconf_instances[ip] = zc
            self.registered_services[ip] = services
            print(f"[MDNSAdvertiser] Đã kích hoạt AirPlay mDNS trên giao diện IP: {ip}")
        except Exception as e:
            print(f"[MDNSAdvertiser] Lỗi đăng ký trên IP {ip}: {e}")

    def _unregister_on_ip(self, ip: str):
        """Unregister services for a disconnected interface."""
        try:
            if ip in self.zeroconf_instances:
                zc = self.zeroconf_instances.pop(ip)
                zc.unregister_all_services()
                zc.close()
            if ip in self.registered_services:
                self.registered_services.pop(ip)
            print(f"[MDNSAdvertiser] Đã hủy đăng ký mDNS trên IP: {ip}")
        except Exception as e:
            pass

    def start(self, server_name: str, port: int = 7000):
        """Start advertising across all active network interfaces."""
        with self._lock:
            if self.is_running:
                self.stop()

            self.server_name = server_name.strip() or "CastScreen-PC"
            self.port = port
            self.is_running = True

            # Register on all active IPs
            active_ips = self.get_active_ipv4_list()
            for ip in active_ips:
                self._register_on_ip(ip)

            # Start network change monitor thread
            self.monitor_thread = threading.Thread(target=self._monitor_network_changes, daemon=True)
            self.monitor_thread.start()

    def _monitor_network_changes(self):
        """Periodically check for new network adapters (e.g. Hotspot turned ON)."""
        while self.is_running:
            try:
                time.sleep(3.0)
                if not self.is_running:
                    break

                active_ips = set(self.get_active_ipv4_list())
                current_ips = set(self.zeroconf_instances.keys())

                # Add new interfaces (e.g., Mobile Hotspot just activated)
                for new_ip in active_ips - current_ips:
                    with self._lock:
                        self._register_on_ip(new_ip)

                # Remove defunct interfaces
                for dead_ip in current_ips - active_ips:
                    with self._lock:
                        self._unregister_on_ip(dead_ip)

            except Exception:
                pass

    def stop(self):
        """Stop advertising and clean up all Zeroconf instances."""
        with self._lock:
            self.is_running = False
            for ip, zc in list(self.zeroconf_instances.items()):
                try:
                    zc.unregister_all_services()
                    zc.close()
                except Exception:
                    pass
            self.zeroconf_instances.clear()
            self.registered_services.clear()
            print("[MDNSAdvertiser] Đã dừng toàn bộ dịch vụ mDNS quảng bá.")
