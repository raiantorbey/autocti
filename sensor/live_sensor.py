"""
AutoCTI Live Network Sensor
---------------------------
Captures real packets on the Windows host, aggregates them into flows,
applies heuristic triage rules, and forwards suspicious flows to the
AutoCTI ingestion API.

Run:
    python sensor/live_sensor.py
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Dict, List, Optional, Tuple

import requests
from scapy.all import sniff, IP, TCP, UDP, conf

# ---------- config ----------
API_BASE = os.getenv("AUTOCTI_API", "http://localhost:8000")
USERNAME = os.getenv("AUTOCTI_USER", "admin")
PASSWORD = os.getenv("AUTOCTI_PASS", "Senior2026!")

FLOW_TIMEOUT_SEC = 10          # flush flows older than this
SCAN_PORT_THRESHOLD = 4        # >= this many distinct dst ports → port scan
BRUTE_FORCE_THRESHOLD = 10     # >= this many connections to same dst:port → brute force
MIN_OUTBOUND_BYTES_EXFIL = 50_000_000   # 50 MB outbound = suspicious

# IPs we don't care about
PRIVATE_NET_FILTER = False
SKIP_DST_PORTS = {53}          # DNS — too noisy

# ---------- helpers ----------

def is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def get_token() -> str:
    """Login to AutoCTI and return JWT."""
    r = requests.post(
        f"{API_BASE}/api/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ---------- flow aggregation ----------

@dataclass
class Flow:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    proto: str
    pkts: int = 0
    bytes_total: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def key(self) -> Tuple[str, str, int, int, str]:
        return (self.src_ip, self.dst_ip, self.src_port, self.dst_port, self.proto)


@dataclass
class HostStats:
    """Per source-IP statistics across all its recent flows."""
    distinct_dst_ports: set = field(default_factory=set)
    connections_per_target: Dict[Tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))
    outbound_bytes: int = 0


# ---------- sensor ----------

class LiveSensor:
    def __init__(self, iface: Optional[str] = None) -> None:
        self.iface = iface
        self.flows: Dict[Tuple, Flow] = {}
        self.lock = Lock()
        self.token: Optional[str] = None
        self.session = requests.Session()
        self._stop = False

    # ---- auth ----
    def _refresh_token(self) -> None:
        try:
            self.token = get_token()
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            print(f"[+] Authenticated to {API_BASE} as {USERNAME}")
        except Exception as e:
            print(f"[-] Login failed: {e}")
            sys.exit(1)

    # ---- packet handler ----
    def _on_packet(self, pkt) -> None:
        if not pkt.haslayer(IP):
            return
        ip = pkt[IP]
        if pkt.haslayer(TCP):
            l4 = pkt[TCP]; proto = "tcp"
        elif pkt.haslayer(UDP):
            l4 = pkt[UDP]; proto = "udp"
        else:
            return

        if l4.dport in SKIP_DST_PORTS:
            return

        # Skip purely private↔private noise (LAN chatter)
        if PRIVATE_NET_FILTER and is_private(ip.src) and is_private(ip.dst):
            return

        key = (ip.src, ip.dst, int(l4.sport), int(l4.dport), proto)
        now = time.time()
        with self.lock:
            f = self.flows.get(key)
            if f is None:
                f = Flow(ip.src, ip.dst, int(l4.sport), int(l4.dport), proto)
                self.flows[key] = f
            f.pkts += 1
            f.bytes_total += len(pkt)
            f.last_seen = now

    # ---- triage ----
    def _classify(self, host_flows: List[Flow]) -> List[dict]:
        """Return events to forward to AutoCTI for one source IP's flows."""
        if not host_flows:
            return []
        src = host_flows[0].src_ip
        stats = HostStats()
        for f in host_flows:
            stats.distinct_dst_ports.add(f.dst_port)
            stats.connections_per_target[(f.dst_ip, f.dst_port)] += 1
            if not is_private(f.dst_ip):
                stats.outbound_bytes += f.bytes_total

        events = []

        # Port-scan detection
        if len(stats.distinct_dst_ports) >= SCAN_PORT_THRESHOLD:
            target = host_flows[0].dst_ip
            events.append({
                "source": "live_sensor",
                "event_type": "port_scan",
                "src_ip": src,
                "dst_ip": target,
                "src_port": host_flows[0].src_port,
                "dst_port": host_flows[0].dst_port,
                "protocol": host_flows[0].proto,
                "severity": min(0.5 + len(stats.distinct_dst_ports) / 50, 0.95),
                "description": f"Live capture: {src} probed {len(stats.distinct_dst_ports)} distinct ports on {target} in {FLOW_TIMEOUT_SEC}s",
                "raw": {"distinct_ports": sorted(stats.distinct_dst_ports)},
            })

        # Brute-force detection
        for (dst_ip, dst_port), n in stats.connections_per_target.items():
            if n >= BRUTE_FORCE_THRESHOLD:
                events.append({
                    "source": "live_sensor",
                    "event_type": "brute_force",
                    "src_ip": src,
                    "dst_ip": dst_ip,
                    "dst_port": dst_port,
                    "protocol": "tcp",
                    "severity": min(0.5 + n / 100, 0.9),
                    "description": f"Live capture: {n} connections from {src} to {dst_ip}:{dst_port} in {FLOW_TIMEOUT_SEC}s",
                })

        # Possible exfiltration
        if stats.outbound_bytes >= MIN_OUTBOUND_BYTES_EXFIL:
            biggest = max(host_flows, key=lambda f: f.bytes_total)
            events.append({
                "source": "live_sensor",
                "event_type": "exfil",
                "src_ip": src,
                "dst_ip": biggest.dst_ip,
                "dst_port": biggest.dst_port,
                "protocol": biggest.proto,
                "severity": 0.85,
                "description": f"Live capture: {stats.outbound_bytes/1e6:.1f} MB outbound from {src} to public destinations in {FLOW_TIMEOUT_SEC}s",
            })

        return events

    # ---- forward ----
    def _forward(self, evt: dict) -> None:
        try:
            r = self.session.post(
                f"{API_BASE}/api/events/ingest",
                json=evt,
                timeout=120,
            )
            if r.status_code == 401:
                self._refresh_token()
                r = self.session.post(f"{API_BASE}/api/events/ingest", json=evt, timeout=120)
            if r.ok:
                inc = r.json()
                print(
                    f"[!] {evt['event_type']:14s} {evt['src_ip']} -> {evt['dst_ip']:15s} "
                    f"sev={evt['severity']:.2f}  →  incident risk={inc.get('risk_score', '?')} "
                    f"tactics={inc.get('tactics', [])}"
                )
            else:
                print(f"[-] Ingest failed {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[-] Ingest error: {e}")

    # ---- flush loop ----
    def _flush_loop(self) -> None:
        while not self._stop:
            time.sleep(FLOW_TIMEOUT_SEC)
            now = time.time()
            with self.lock:
                expired = [k for k, f in self.flows.items() if now - f.last_seen >= FLOW_TIMEOUT_SEC]
                expired_flows = [self.flows.pop(k) for k in expired]
            if not expired_flows:
                continue

            # Group by source IP
            by_src: Dict[str, List[Flow]] = defaultdict(list)
            for f in expired_flows:
                by_src[f.src_ip].append(f)

            print(f"[*] Window flush: {len(expired_flows)} flows from {len(by_src)} hosts")
            for src, flows in by_src.items():
                events = self._classify(flows)
                for evt in events:
                    self._forward(evt)

    # ---- run ----
    def run(self) -> None:
        self._refresh_token()
        Thread(target=self._flush_loop, daemon=True).start()
        print(f"[*] Capturing on iface={self.iface or 'default'} … (Ctrl+C to stop)")
        try:
            sniff(
                iface=self.iface,
                prn=self._on_packet,
                store=False,
                filter="ip",   # BPF filter
            )
        except KeyboardInterrupt:
            print("\n[*] Stopped.")
            self._stop = True


# ---------- main ----------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--iface", help="Network interface (default: auto)")
    p.add_argument("--list-ifaces", action="store_true", help="List available interfaces and exit")
    args = p.parse_args()

    if args.list_ifaces:
        from scapy.arch.windows import get_windows_if_list
        for w in get_windows_if_list():
            print(f"  {w.get('name', '?'):30s}  IPs={w.get('ips')}  desc={w.get('description', '')}")
        return

    sensor = LiveSensor(iface=args.iface)
    sensor.run()


if __name__ == "__main__":
    main()