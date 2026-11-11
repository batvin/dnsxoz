#!/usr/bin/env python3
"""
Server Optimization & DNS Test Panel (v2)
-----------------------------------------
Dashboard with:
  - Live server resource monitoring
  - DNS latency tests + best DNS selection/apply
  - Mirror speed tests (apt, pip, ...)
  - Network optimization (BBR, sysctl)
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
    {"name": "Cloudflare Secondary", "ip": "1.0.0.1"},
    {"name": "Google", "ip": "8.8.8.8"},
    {"name": "Google Secondary", "ip": "8.8.4.4"},
    {"name": "Quad9", "ip": "9.9.9.9"},
    {"name": "OpenDNS", "ip": "208.67.222.222"},
    {"name": "Shecan", "ip": "178.22.122.100"},
    {"name": "Shecan Secondary", "ip": "185.51.200.2"},
    {"name": "Electro", "ip": "78.157.42.100"},
    {"name": "Electro Secondary", "ip": "78.157.42.101"},
]

TEST_DOMAINS = ["google.com", "github.com", "cloudflare.com", "pypi.org"]

MIRRORS = {
    "apt": [
        {"name": "Ubuntu Official", "url": "http://archive.ubuntu.com/ubuntu/"},
        {"name": "Ubuntu Archive IR", "url": "http://ir.archive.ubuntu.com/ubuntu/"},
        {"name": "Ubuntu Mirror (DE)", "url": "http://de.archive.ubuntu.com/ubuntu/"},
        {"name": "Ubuntu Mirror (NL)", "url": "http://nl.archive.ubuntu.com/ubuntu/"},
        {"name": "Ubuntu Mirror (TR)", "url": "http://tr.archive.ubuntu.com/ubuntu/"},
        {"name": "Ubuntu Mirror (RU)", "url": "http://ru.archive.ubuntu.com/ubuntu/"},
        {"name": "Debian Official", "url": "http://deb.debian.org/debian/"},
        {"name": "Debian Mirror IR", "url": "http://mirror.ir/debian/"},
        {"name": "Tsinghua Ubuntu", "url": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"},
        {"name": "Aliyun Ubuntu", "url": "https://mirrors.aliyun.com/ubuntu/"},
    ],
    "pip": [
        {"name": "PyPI Official", "url": "https://pypi.org/simple/", "host": "pypi.org"},
        {"name": "PyPI python.org", "url": "https://pypi.python.org/simple/", "host": "pypi.python.org"},
        {"name": "Tsinghua (tuna)", "url": "https://pypi.tuna.tsinghua.edu.cn/simple/", "host": "pypi.tuna.tsinghua.edu.cn"},
        {"name": "Aliyun", "url": "https://mirrors.aliyun.com/pypi/simple/", "host": "mirrors.aliyun.com"},
        {"name": "USTC", "url": "https://pypi.mirrors.ustc.edu.cn/simple/", "host": "pypi.mirrors.ustc.edu.cn"},
        {"name": "Douban", "url": "https://pypi.douban.com/simple/", "host": "pypi.douban.com"},
        {"name": "Huawei Cloud", "url": "https://mirrors.huaweicloud.com/repository/pypi/simple/", "host": "mirrors.huaweicloud.com"},
        {"name": "Tencent Cloud", "url": "https://mirrors.cloud.tencent.com/pypi/simple/", "host": "mirrors.cloud.tencent.com"},
        {"name": "NetEase", "url": "https://mirrors.163.com/pypi/simple/", "host": "mirrors.163.com"},
        {"name": "Baidu", "url": "https://mirror.baidu.com/pypi/simple/", "host": "mirror.baidu.com"},
        {"name": "SJTU", "url": "https://mirror.sjtu.edu.cn/pypi/web/simple/", "host": "mirror.sjtu.edu.cn"},
        {"name": "BFSU", "url": "https://mirrors.bfsu.edu.cn/pypi/web/simple/", "host": "mirrors.bfsu.edu.cn"},
    ],
    "npm": [
        {"name": "npm Official", "url": "https://registry.npmjs.org/"},
        {"name": "npmmirror (China)", "url": "https://registry.npmmirror.com/"},
        {"name": "Yarn Official", "url": "https://registry.yarnpkg.com/"},
        {"name": "Huawei npm", "url": "https://mirrors.huaweicloud.com/repository/npm/"},
        {"name": "Tencent npm", "url": "https://mirrors.cloud.tencent.com/npm/"},
    ],
}

PANEL_VENV_PIP = "/opt/server-panel/venv/bin/pip"

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


def run_cmd(cmd, timeout=15):
    try:
        out = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return out.stdout.strip(), out.stderr.strip(), out.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1


def load_results():
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "optimization": None,
        "dns_tests": None,
        "mirror_tests": None,
        "applied_dns": None,
    }


def save_results(data):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_cpu_usage():
    def read_cpu():
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        values = [int(x) for x in parts[1:8]]
        idle = values[3] + values[4]
        total = sum(values)
        return idle, total

    idle1, total1 = read_cpu()
    time.sleep(0.35)
    idle2, total2 = read_cpu()
    idle_delta = idle2 - idle1
    total_delta = total2 - total1
    if total_delta == 0:
        return 0.0
    usage = 100.0 * (1.0 - idle_delta / total_delta)
    return round(max(0.0, min(100.0, usage)), 1)


def get_mem_info():
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.strip().split()[0])
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = total - available
    return {
        "total_mb": round(total / 1024, 1),
        "used_mb": round(used / 1024, 1),
        "available_mb": round(available / 1024, 1),
        "percent": round(100.0 * used / total, 1) if total else 0,
    }


def get_disk_info():
    out, _, code = run_cmd("df -B1 / | tail -1")
    if code != 0 or not out:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}
    parts = out.split()
    total = int(parts[1])
    used = int(parts[2])
    free = int(parts[3])
    return {
        "total_gb": round(total / (1024 ** 3), 2),
        "used_gb": round(used / (1024 ** 3), 2),
        "free_gb": round(free / (1024 ** 3), 2),
        "percent": round(100.0 * used / total, 1) if total else 0,
    }


def get_load_avg():
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        return {"1m": float(parts[0]), "5m": float(parts[1]), "15m": float(parts[2])}
    except Exception:
        return {"1m": 0, "5m": 0, "15m": 0}


def get_network_info():
    rx = tx = 0
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line or line.strip().startswith("lo:"):
                    continue
                parts = line.split(":")
                nums = parts[1].split()
                rx += int(nums[0])
                tx += int(nums[8])
    except Exception:
        pass
    return {"rx_gb": round(rx / (1024 ** 3), 2), "tx_gb": round(tx / (1024 ** 3), 2)}


def get_system_info():
    hostname = socket.gethostname()
    out, _, _ = run_cmd("uptime -p")
    cpu_out, _, _ = run_cmd("grep -c ^processor /proc/cpuinfo")
    dns_out, _, _ = run_cmd("grep -E '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}'")
    current_dns = [x.strip() for x in dns_out.splitlines() if x.strip()] if dns_out else []
    return {
        "hostname": hostname,
        "os": f"{platform.system()} {platform.release()}",
        "uptime": out or "unknown",
        "cpu_cores": int(cpu_out) if cpu_out.isdigit() else 0,
        "current_dns": current_dns,
    }


def get_resources():
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "cpu_percent": get_cpu_usage(),
        "memory": get_mem_info(),
        "disk": get_disk_info(),
        "load": get_load_avg(),
        "network": get_network_info(),
        "system": get_system_info(),
    }


def apply_optimizations():
    log = []
    before = {}
    for key in SYSCTL_TWEAKS:
        out, _, _ = run_cmd(f"sysctl -n {key} 2>/dev/null")
        before[key] = out

    conf_path = "/etc/sysctl.d/99-server-panel.conf"
    with open(conf_path, "w") as f:
        f.write("# Managed by server-panel — speed optimization tweaks\n")
        for k, v in SYSCTL_TWEAKS.items():
            f.write(f"{k} = {v}\n")
    log.append(f"wrote {conf_path}")

    out, err, code = run_cmd("sysctl --system")
    log.append("sysctl --system applied" if code == 0 else f"sysctl error: {err}")

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


def test_dns_server(server, domain):
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

    results.sort(key=lambda r: (r["avg_ms"] is None, r["avg_ms"] or 9999))

    data = load_results()
    data["dns_tests"] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": results,
        "best": results[0] if results and results[0]["avg_ms"] is not None else None,
    }
    save_results(data)
    return data["dns_tests"]


def apply_dns(primary_ip, secondary_ip=None):
    resolv = "/etc/resolv.conf"
    backup = "/etc/resolv.conf.panel-backup"
    log = []

    if os.path.exists(resolv) and not os.path.exists(backup):
        shutil.copy2(resolv, backup)
        log.append(f"backup created: {backup}")

    lines = [
        "# Managed by server-panel",
        f"nameserver {primary_ip}",
    ]
    if secondary_ip:
        lines.append(f"nameserver {secondary_ip}")
    lines.append("options timeout:2 attempts:3")

    with open(resolv, "w") as f:
        f.write("\n".join(lines) + "\n")
    log.append(f"wrote {resolv} → {primary_ip}" + (f", {secondary_ip}" if secondary_ip else ""))

    if shutil.which("resolvectl"):
        run_cmd(f"resolvectl dns $(ip route | grep default | awk '{{print $5}}' | head -1) {primary_ip} {secondary_ip or ''}")
        log.append("tried resolvectl update")

    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "primary": primary_ip,
        "secondary": secondary_ip,
        "log": log,
    }
    data = load_results()
    data["applied_dns"] = result
    save_results(data)
    return result


def test_mirror_url(url, timeout=8):
    start = time.time()
    out, err, code = run_cmd(
        f'curl -s -o /dev/null -w "%{{http_code}} %{{time_total}}" -m {timeout} -L "{url}"',
        timeout=timeout + 2,
    )
    elapsed_ms = round((time.time() - start) * 1000, 1)
    if code != 0 or not out:
        return {"ok": False, "time_ms": None, "http_code": None, "error": err or "failed"}
    parts = out.split()
    http_code = parts[0] if parts else "?"
    try:
        time_total = round(float(parts[1]) * 1000, 1) if len(parts) > 1 else elapsed_ms
    except ValueError:
        time_total = elapsed_ms
    ok = http_code.startswith("2") or http_code.startswith("3")
    return {
        "ok": ok,
        "time_ms": time_total if ok else None,
        "http_code": http_code,
        "error": None if ok else f"HTTP {http_code}",
    }


def run_mirror_tests(category=None):
    categories = [category] if category and category in MIRRORS else list(MIRRORS.keys())
    all_results = {}

    for cat in categories:
        results = []
        for mirror in MIRRORS[cat]:
            r = test_mirror_url(mirror["url"])
            entry = {"name": mirror["name"], "url": mirror["url"], "host": mirror.get("host"), **r}
            results.append(entry)
        results.sort(key=lambda x: (x["time_ms"] is None, x["time_ms"] or 99999))
        all_results[cat] = {
            "results": results,
            "best": results[0] if results and results[0].get("ok") else None,
        }

    data = load_results()
    data["mirror_tests"] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "categories": all_results,
    }
    save_results(data)
    return data["mirror_tests"]


def apply_pip_mirror(index_url, host=None, scope="venv"):
    log = []
    if not host:
        host = index_url.split("//", 1)[-1].split("/")[0]

    targets = []
    if scope in ("venv", "both"):
        targets.append(("venv", PANEL_VENV_PIP))
    if scope in ("system", "both"):
        sys_pip = shutil.which("pip3") or shutil.which("pip")
        if sys_pip:
            targets.append(("system", sys_pip))
        else:
            log.append("system pip not found, skipped")

    if not targets:
        raise RuntimeError("No pip binary found to configure")

    for label, pip_bin in targets:
        if label == "venv" and not os.path.exists(pip_bin):
            log.append(f"{label}: {pip_bin} missing — skip")
            continue
        cmds = [
            f'"{pip_bin}" config set global.index-url {index_url}',
            f'"{pip_bin}" config set global.trusted-host {host}',
            f'"{pip_bin}" config set global.timeout 1000',
        ]
        for c in cmds:
            out, err, code = run_cmd(c)
            if code == 0:
                log.append(f"{label}: ok — {c}")
            else:
                log.append(f"{label}: fail — {c} ({err or out})")

    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "category": "pip",
        "index_url": index_url,
        "host": host,
        "scope": scope,
        "log": log,
    }
    data = load_results()
    data["applied_mirror"] = result
    save_results(data)
    return result


def apply_npm_mirror(registry_url):
    log = []
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on system")
    out, err, code = run_cmd(f'npm config set registry {registry_url}')
    if code == 0:
        log.append(f"npm registry set to {registry_url}")
    else:
        raise RuntimeError(err or out or "npm config failed")
    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "category": "npm",
        "registry": registry_url,
        "log": log,
    }
    data = load_results()
    data["applied_mirror"] = result
    save_results(data)
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/resources")
def api_resources():
    try:
        return jsonify({"ok": True, "data": get_resources()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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


@app.route("/api/dns-apply", methods=["POST"])
def api_dns_apply():
    body = request.get_json(silent=True) or {}
    primary = body.get("primary")
    secondary = body.get("secondary")
    if not primary:
        return jsonify({"ok": False, "error": "primary DNS IP required"}), 400
    try:
        result = apply_dns(primary, secondary)
        return jsonify({"ok": True, "result": result})
    except PermissionError:
        return jsonify({"ok": False, "error": "Need root to write /etc/resolv.conf"}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mirror-test", methods=["POST"])
def api_mirror_test():
    if not shutil.which("curl"):
        return jsonify({"ok": False, "error": "'curl' not found."}), 500
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    try:
        result = run_mirror_tests(category)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mirror-apply", methods=["POST"])
def api_mirror_apply():
    body = request.get_json(silent=True) or {}
    category = body.get("category", "pip")
    url = body.get("url")
    host = body.get("host")
    scope = body.get("scope", "venv")
    if not url:
        return jsonify({"ok": False, "error": "url required"}), 400
    try:
        if category == "pip":
            result = apply_pip_mirror(url, host=host, scope=scope)
        elif category == "npm":
            result = apply_npm_mirror(url)
        else:
            return jsonify({
                "ok": False,
                "error": "اعمال خودکار فقط برای pip و npm است. برای apt باید sources.list را دستی تغییر دهید."
            }), 400
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PANEL_PORT", 8088))
    app.run(host="0.0.0.0", port=port, debug=False)
