import concurrent.futures
import ctypes
import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
from urllib.parse import urlsplit, urlunsplit

from module import gloval_value as g

# 同時探索数と探索するネットワークの上限
search_workers = 16
search_max_addresses = 1024
search_lock = threading.Lock()
arp_lock = threading.Lock()
arp_library = None
send_arp_func = None

"""
 MACアドレスの表記を統一
"""
def NormalizeMAC(mac_addr):
    if not mac_addr:
        return ""
    if not isinstance(mac_addr, str):
        raise ValueError("Invalid MAC address.")
    value = mac_addr.replace(':', '').replace('-', '').strip().lower()
    if not re.fullmatch(r'[0-9a-f]{12}', value):
        raise ValueError("Invalid MAC address.")
    return value

"""
 同じLANにある探索先を取得(Windows)
"""
def GetSearchHosts(host_ip):
    if os.name != 'nt':
        raise OSError("MAC address search requires Windows.")
    target = ipaddress.IPv4Address(host_ip)
    command = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.AddressState -eq 'Preferred' } | "
        "Select-Object IPAddress,PrefixLength | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=10, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    interfaces = json.loads(result.stdout.decode('utf-8-sig'))
    if isinstance(interfaces, dict):
        interfaces = [interfaces]
    networks = []
    local_ips = {item["IPAddress"] for item in interfaces}
    for item in interfaces:
        network = ipaddress.IPv4Network(
            f'{item["IPAddress"]}/{item["PrefixLength"]}', strict=False
        )
        if target in network:
            networks.append((network, item["IPAddress"]))
    if not networks:
        raise ValueError("Camera address is outside the local LAN.")
    # VPNなどと重なる場合は最も範囲の狭いネットワークを使用
    network, local_ip = max(networks, key=lambda item: item[0].prefixlen)
    if network.num_addresses > search_max_addresses:
        raise ValueError("Local network is too large to search.")
    return local_ip, [str(ip) for ip in network.hosts() if str(ip) not in local_ips]

"""
 ARPで対象IPのMACアドレスを取得(管理者権限・追加ライブラリ不要)
"""
def GetMACAddress(host_ip, local_ip):
    if not g.thread_running:
        return ""
    global arp_library, send_arp_func
    # DLLはプロセス内で一度だけ読み込む(探索ごとの参照増加を防ぐ)
    with arp_lock:
        if send_arp_func is None:
            arp_library = ctypes.WinDLL("iphlpapi.dll")
            send_arp_func = arp_library.SendARP
            send_arp_func.argtypes = [
                ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong)
            ]
            send_arp_func.restype = ctypes.c_ulong
    send_arp = send_arp_func
    dest = int.from_bytes(socket.inet_aton(host_ip), 'little')
    source = int.from_bytes(socket.inet_aton(local_ip), 'little')
    address = (ctypes.c_ubyte * 6)()
    length = ctypes.c_ulong(6)
    result = send_arp(dest, source, address, ctypes.byref(length))
    if result != 0 or length.value != 6:
        return ""
    return bytes(address).hex()

"""
 接続先と同じLANからMACアドレスが一致するIPを探索
"""
def FindIP_FromMAC(mac_addr, host_ip):
    target = NormalizeMAC(mac_addr)
    if not target:
        return None
    # 複数カメラが同時に切断しても探索を重ねない
    while not search_lock.acquire(timeout=0.1):
        if not g.thread_running:
            return None
    try:
        if not g.thread_running:
            return None
        local_ip, hosts = GetSearchHosts(host_ip)
        with concurrent.futures.ThreadPoolExecutor(max_workers=search_workers) as executor:
            # 一度に全アドレスを投入せず、停止時の未処理分を抑える
            for offset in range(0, len(hosts), search_workers):
                if not g.thread_running:
                    return None
                batch = hosts[offset:offset + search_workers]
                futures = {executor.submit(GetMACAddress, ip, local_ip): ip for ip in batch}
                for future in concurrent.futures.as_completed(futures):
                    if future.result() == target and g.thread_running:
                        return futures[future]
        return None
    finally:
        search_lock.release()

"""
 RTSPアドレスの接続先IPだけを変更
"""
def ReplaceRTSPHost(addr, host_ip):
    parts = urlsplit(addr)
    auth, separator, host = parts.netloc.rpartition('@')
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = (auth + separator if separator else "") + host_ip + port
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
