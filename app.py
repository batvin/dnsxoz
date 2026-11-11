#!/usr/bin/env python3
"""
Server Optimization & DNS Test Panel
-------------------------------------
A lightweight Flask panel that:
  1. Applies common server/network speed-optimization tweaks (BBR, sysctl, limits)
  2. Runs DNS latency/resolution tests against a list of DNS servers
  3. Shows live results in a dashboard with charts & animations

Run as root (it needs to write to /etc/sysctl.conf, /etc/security/limits.conf, etc).
"""
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

RESULTS_FILE = "/opt/server-panel/results.json"
os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

DNS_SERVERS = [
    {"name": "Cloudflare", "ip": "1.1.1.1"},
    {"name": "Google", "ip": "8.8.8.8"},
    {"name": "Quad9", "ip": "9.9.9.9"},
    {"name": "OpenDNS", "ip": "208.67.222.222"},
    {"name": "Shecan", "ip": "178.22.122.100"},
    {"name": "Electro", "ip": "78.157.42.100"},
]

TEST_DOMAINS = ["google.com", "github.com", "cloudflare.com"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def run_cmd(cmd, timeout=10):
    try:
        out = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return out.stdout.strip(), out.stderr.strip(), out.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1


def load_results():
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"optimization": None, "dns_tests": []}


def save_results(data):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --------------------------------------------------------------------------
# Optimization routines
# --------------------------------------------------------------------------
SYSCTL_TWEAKS = {
    "net.core.default_qdisc": "fq",
    "net.ipv4.tcp_congestion_control": "bbr",
    "net.core.rmem_max": "67108864",
    "net.core.wmem_max": "67108864",
    "net.ipv4.tcp_rmem": "4096 87380 67108864",
    "net.ipv4.tcp_wmem": "4096 65536 67108864",
    "net.core.netdev_max_backlog": "250000",
    "net.ipv4.tcp_fastopen": "3",
    "net.ipv4.tcp_slow_start_after_idle": "0",
    "net.ipv4.tcp_mtu_probing": "1",
    "net.ipv4.ip_local_port_range": "1024 65535",
    "fs.file-max": "2097152",
}


def apply_optimizations():
    log = []
    before = {}
    for key in SYSCTL_TWEAKS:
        out, _, _ = run_cmd(f"sysctl -n {key} 2>/dev/null")
        before[key] = out

    # Write/replace tweaks in a dedicated file so we never clobber the user's sysctl.conf
    conf_path = "/etc/sysctl.d/99-server-panel.conf"
    with open(conf_path, "w") as f:
        f.write("# Managed by server-panel — speed optimization tweaks\n")
        for k, v in SYSCTL_TWEAKS.items():
            f.write(f"{k} = {v}\n")
    log.append(f"wrote {conf_path}")

    out, err, code = run_cmd("sysctl --system")
    log.append("sysctl --system applied" if code == 0 else f"sysctl error: {err}")

    # Check BBR module is available
    out, _, _ = run_cmd("lsmod | grep -i bbr")
    if not out:
        run_cmd("modprobe tcp_bbr")
        log.append("loaded tcp_bbr module")
    else:
        log.append("tcp_bbr module already loaded")

    after = {}
    for key in SYSCTL_TWEAKS:
        out, _, _ = run_cmd(f"sysctl -n {key} 2>/dev/null")
        after[key] = out

    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "before": before,
        "after": after,
        "log": log,
        "bbr_active": after.get("net.ipv4.tcp_congestion_control") == "bbr",
    }
    data = load_results()
    data["optimization"] = result
    save_results(data)
    return result


# --------------------------------------------------------------------------
# DNS test routines
# --------------------------------------------------------------------------
def test_dns_server(server, domain):
    """Resolve `domain` using a specific DNS server via `dig`, measure time."""
    start = time.time()
    out, err, code = run_cmd(
        f"dig @{server['ip']} {domain} +time=2 +tries=1 +short", timeout=5
    )
    elapsed_ms = round((time.time() - start) * 1000, 1)
    resolved = bool(out) and code == 0
    return {
        "domain": domain,
        "resolved": resolved,
        "answer": out.splitlines()[0] if out else None,
        "time_ms": elapsed_ms if resolved else None,
    }


def run_dns_tests():
    results = []
    for server in DNS_SERVERS:
        entry = {"name": server["name"], "ip": server["ip"], "queries": []}
        times = []
        for domain in TEST_DOMAINS:
            r = test_dns_server(server, domain)
            entry["queries"].append(r)
            if r["time_ms"] is not None:
                times.append(r["time_ms"])
        entry["avg_ms"] = round(sum(times) / len(times), 1) if times else None
        entry["success_rate"] = round(
            100 * len([q for q in entry["queries"] if q["resolved"]]) / len(TEST_DOMAINS)
        )
        results.append(entry)

    # Sort fastest first (None/failed last)
    results.sort(key=lambda r: (r["avg_ms"] is None, r["avg_ms"] or 9999))

    data = load_results()
    data["dns_tests"] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": results,
    }
    save_results(data)
    return data["dns_tests"]


# --------------------------------------------------------------------------
# System info
# --------------------------------------------------------------------------
def get_system_info():
    hostname = socket.gethostname()
    out, _, _ = run_cmd("uptime -p")
    cpu_out, _, _ = run_cmd(
        "grep -c ^processor /proc/cpuinfo"
    )
    mem_out, _, _ = run_cmd("free -m | awk '/Mem:/ {print $2, $3}'")
    mem_total, mem_used = (mem_out.split() + ["?", "?"])[:2]
    return {
        "hostname": hostname,
        "os": f"{platform.system()} {platform.release()}",
        "uptime": out or "unknown",
        "cpu_cores": cpu_out or "?",
        "mem_total_mb": mem_total,
        "mem_used_mb": mem_used,
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/system")
def api_system():
    return jsonify(get_system_info())


@app.route("/api/results")
def api_results():
    return jsonify(load_results())


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    try:
        result = apply_optimizations()
        return jsonify({"ok": True, "result": result})
    except PermissionError:
        return jsonify({"ok": False, "error": "Run the panel as root to apply optimizations."}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dns-test", methods=["POST"])
def api_dns_test():
    if not shutil.which("dig"):
        return jsonify({"ok": False, "error": "'dig' not found. Install dnsutils/bind-utils."}), 500
    try:
        result = run_dns_tests()
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PANEL_PORT", 8088))
    app.run(host="0.0.0.0", port=port)
