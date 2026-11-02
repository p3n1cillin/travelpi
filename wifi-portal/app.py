#!/usr/bin/env python3
"""
TravelPi WiFi Portal
--------------------
Always-on web GUI served on the AP (default http://192.168.50.1/) so you can
pick and join an upstream WiFi (e.g. hotel) on the client dongle (wlan1) *before*
the Pi has any internet. Uses NetworkManager (nmcli) under the hood.

Runs as root (needs nmcli to manage WiFi). The page is fully self-contained
(inline CSS/JS, no external assets) because there is no internet when you first
open it.
"""
import ipaddress
import subprocess
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
WIFI_IF = "wlan1"          # hotel-side client dongle
PORT = 80


# Every state-changing request must carry this header. A page on another site
# cannot add a custom header to a cross-origin request without a CORS preflight,
# which this server never answers, so forms, <img> tags and fetch() from other
# sites are all refused. The bundled page sends it on every call.
CSRF_HEADER = "X-TravelPi"


def host_allowed(host_header):
    """True for the names this service is really reached by: an IP address,
    a single-label name (localhost, travelpi), *.local or *.ts.net. Anything
    else is a DNS-rebinding attempt: a public name pointed at the Pi so a
    hostile page counts as same-origin."""
    if not host_header:
        return False
    host = host_header.strip()
    if host.startswith("["):
        host = host[1:host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    host = host.lower().rstrip(".")
    return bool(host) and ("." not in host or host.endswith((".local", ".ts.net")))


@app.before_request
def refuse_cross_site():
    if not host_allowed(request.headers.get("Host")):
        return jsonify(ok=False, message="Unrecognised Host header"), 403
    if request.method != "GET" and request.headers.get(CSRF_HEADER) != "1":
        return jsonify(ok=False, message=f"Missing {CSRF_HEADER} header"), 403
    return None


def run(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa
        return 124, "", str(e)


def nmcli(*args, timeout=20):
    return run(["nmcli"] + list(args), timeout=timeout)


def split_terse(line):
    """Split an nmcli -t line on unescaped colons (nmcli escapes ':' as '\\:')."""
    out, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            out.append(cur)
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    out.append(cur)
    return out


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/api/status")
def status():
    st = {"device": WIFI_IF, "state": "unknown", "connection": ""}
    _, out, _ = nmcli("-t", "-f", "DEVICE,STATE,CONNECTION", "dev")
    for line in out.splitlines():
        p = split_terse(line)
        if len(p) >= 3 and p[0] == WIFI_IF:
            st = {"device": p[0], "state": p[1], "connection": p[2]}
    ip = ""
    _, out, _ = nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", WIFI_IF)
    for line in out.splitlines():
        if line.startswith("IP4.ADDRESS"):
            ip = line.split(":", 1)[1]
            break
    # WAN currently used for the default route
    _, out, _ = run(["ip", "route", "get", "1.1.1.1"])
    wan = ""
    if out:
        parts = out.split()
        if "dev" in parts:
            wan = parts[parts.index("dev") + 1]
    rc, _, _ = run(["ping", "-c", "1", "-W", "2", "1.1.1.1"])
    return jsonify(wlan1=st, ip=ip, wan=wan, internet=(rc == 0))


@app.route("/api/scan", methods=["POST"])
def scan():
    nmcli("dev", "wifi", "rescan", "ifname", WIFI_IF, timeout=25)
    _, out, _ = nmcli("-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE",
                      "dev", "wifi", "list", "ifname", WIFI_IF, timeout=15)
    nets = {}
    for line in out.splitlines():
        p = split_terse(line)
        if len(p) < 3 or not p[0]:
            continue
        ssid = p[0]
        sig = int(p[1]) if p[1].isdigit() else 0
        sec = p[2] or "Open"
        in_use = (len(p) > 3 and p[3].strip() == "*")
        if ssid not in nets or sig > nets[ssid]["signal"]:
            nets[ssid] = {"ssid": ssid, "signal": sig, "security": sec, "in_use": in_use}
    return jsonify(networks=sorted(nets.values(), key=lambda n: -n["signal"]))


@app.route("/api/connect", methods=["POST"])
def connect():
    data = request.get_json(force=True, silent=True) or {}
    ssid = (data.get("ssid") or "").strip()
    password = data.get("password") or ""
    if not ssid:
        return jsonify(ok=False, message="SSID required"), 400
    args = ["dev", "wifi", "connect", ssid, "ifname", WIFI_IF]
    if password:
        args = ["dev", "wifi", "connect", ssid, "password", password, "ifname", WIFI_IF]
    rc, out, err = nmcli(*args, timeout=45)
    return jsonify(ok=(rc == 0), message=(out or err).strip())


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    rc, out, err = nmcli("dev", "disconnect", WIFI_IF)
    return jsonify(ok=(rc == 0), message=(out or err).strip())


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TravelPi WiFi</title>
<style>
:root{color-scheme:dark light}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
     background:#0f1220;color:#e8ebf5}
header{padding:18px 16px;background:#171a2e;border-bottom:1px solid #262a45}
h1{margin:0;font-size:18px}
.sub{opacity:.7;font-size:13px;margin-top:4px}
main{padding:16px;max-width:640px;margin:0 auto}
.card{background:#171a2e;border:1px solid #262a45;border-radius:12px;padding:14px;margin-bottom:14px}
.status{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.dot{width:10px;height:10px;border-radius:50%;background:#e0524b}
.dot.ok{background:#3fb950}
button{background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:10px 14px;
       font-size:14px;cursor:pointer}
button.secondary{background:#2a2f4c}
button:disabled{opacity:.5;cursor:default}
ul{list-style:none;margin:0;padding:0}
li{display:flex;justify-content:space-between;align-items:center;padding:11px 8px;
   border-bottom:1px solid #23273f;cursor:pointer;border-radius:8px}
li:hover{background:#1e2238}
.ssid{font-weight:600}
.meta{opacity:.65;font-size:12px}
.bars{font-variant-numeric:tabular-nums;opacity:.8;font-size:12px;margin-left:8px}
input{width:100%;padding:10px;border-radius:8px;border:1px solid #2a2f4c;
      background:#0f1220;color:#e8ebf5;font-size:14px;margin:8px 0}
.row{display:flex;gap:8px}
.msg{font-size:13px;margin-top:8px;min-height:18px}
.lock{opacity:.6;font-size:12px}
</style></head>
<body>
<header><h1>TravelPi WiFi</h1><div class="sub">Pick the upstream network for the travel router</div></header>
<main>
  <div class="card">
    <div class="status">
      <span class="dot" id="dot"></span>
      <span id="statusText">Checking…</span>
    </div>
    <div class="meta" id="statusDetail"></div>
  </div>

  <div class="card">
    <div class="row">
      <button id="scanBtn" onclick="scan()">Scan networks</button>
      <button class="secondary" onclick="disconnectWifi()">Disconnect</button>
    </div>
    <div class="msg" id="scanMsg"></div>
    <ul id="list"></ul>
  </div>

  <div class="card" id="connectCard" style="display:none">
    <div id="pickSsid" class="ssid"></div>
    <input id="pw" type="password" placeholder="WiFi password (leave blank if open)" autocomplete="off">
    <div class="row">
      <button onclick="doConnect()">Connect</button>
      <button class="secondary" onclick="hideConnect()">Cancel</button>
    </div>
    <div class="msg" id="connMsg"></div>
  </div>
</main>
<script>
let picked=null;
async function api(path,opts={}){opts.headers=Object.assign({'X-TravelPi':'1'},opts.headers||{});const r=await fetch(path,opts);return r.json();}
function bars(s){const n=Math.max(0,Math.min(4,Math.round(s/25)));return "▂▄▆█".slice(0,n)+"·".repeat(4-n);}
async function refresh(){
  try{const s=await api('/api/status');
    const dot=document.getElementById('dot');
    const ok=s.internet;dot.className='dot'+(ok?' ok':'');
    document.getElementById('statusText').textContent=
      ok?('Online via '+(s.wan||'?')):(s.wlan1.state==='connected'?'Connected, no internet yet':'Not connected');
    document.getElementById('statusDetail').textContent=
      (s.wlan1.connection?('SSID: '+s.wlan1.connection+'  '):'')+(s.ip?('IP: '+s.ip):'');
  }catch(e){}
}
async function scan(){
  const b=document.getElementById('scanBtn');b.disabled=true;
  document.getElementById('scanMsg').textContent='Scanning…';
  try{const r=await api('/api/scan',{method:'POST'});
    const ul=document.getElementById('list');ul.innerHTML='';
    (r.networks||[]).forEach(n=>{
      const li=document.createElement('li');li.onclick=()=>pick(n);
      li.innerHTML='<span><span class="ssid">'+esc(n.ssid)+'</span> '+
        (n.security&&n.security!=='Open'?'<span class="lock">🔒</span>':'')+
        (n.in_use?' <span class="meta">(current)</span>':'')+
        '</span><span class="bars">'+bars(n.signal)+'</span>';
      ul.appendChild(li);
    });
    document.getElementById('scanMsg').textContent=(r.networks||[]).length+' networks';
  }catch(e){document.getElementById('scanMsg').textContent='Scan failed';}
  b.disabled=false;
}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function pick(n){picked=n;document.getElementById('connectCard').style.display='block';
  document.getElementById('pickSsid').textContent=n.ssid;
  document.getElementById('pw').value='';document.getElementById('connMsg').textContent='';
  document.getElementById('pw').focus();}
function hideConnect(){document.getElementById('connectCard').style.display='none';}
async function doConnect(){
  const pw=document.getElementById('pw').value;
  document.getElementById('connMsg').textContent='Connecting…';
  try{const r=await api('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ssid:picked.ssid,password:pw})});
    document.getElementById('connMsg').textContent=r.ok?'Connected ✔':('Failed: '+(r.message||''));
    if(r.ok){setTimeout(()=>{hideConnect();refresh();},1200);}
  }catch(e){document.getElementById('connMsg').textContent='Error';}
}
async function disconnectWifi(){await api('/api/disconnect',{method:'POST'});refresh();}
refresh();setInterval(refresh,5000);
</script>
</body></html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
