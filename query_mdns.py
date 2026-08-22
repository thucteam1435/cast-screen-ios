import time
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

def on_service_state_change(zeroconf, service_type, name, state_change):
    if state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if info:
            print(f"Service {name} added, addresses: {[socket.inet_ntoa(a) for a in info.addresses]}, port: {info.port}, server: {info.server}")
            
import socket
zeroconf = Zeroconf()
browser = ServiceBrowser(zeroconf, "_airplay._tcp.local.", handlers=[on_service_state_change])
time.sleep(5)
zeroconf.close()
