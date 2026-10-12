"""Runs the Gen0Sec Fail2Ban action's commands, rendered by Fail2Ban itself,
against a local mock of the Signal API, and checks each exits 0 only on 200.

Needs Fail2Ban's Python package (the fail2ban package on Debian and Ubuntu).
Usage, from integrations/fail2ban/:  python3 test/test_action.py
"""
import json, subprocess, sys, threading, shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, '/usr/lib/python3/dist-packages')
from fail2ban.client.actionreader import ActionReader
from fail2ban.server.action import CommandAction
from fail2ban.server.ipdns import IPAddr

import os, tempfile
here = os.path.dirname(os.path.abspath(__file__))
basedir = tempfile.mkdtemp()
os.makedirs(f"{basedir}/action.d")
shutil.copy(os.path.join(here, "..", "gen0sec.conf"), f"{basedir}/action.d/gen0sec.conf")
reply = {"code": 200}; seen = []

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        seen.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        self.send_response(reply["code"]); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/v2/signal"

def render(cmd, ip="203.0.113.7", bantime=600):
    r = ActionReader("gen0sec", "sshd", {"g0stoken": "TESTKEY", "g0surl": url}, basedir=basedir)
    assert r.read(), "read failed"; r.getOptions({})
    a = CommandAction(None, "gen0sec")
    for k, v in r.getCombined().items():
        try: setattr(a, k, v)
        except Exception: pass
    if not getattr(a, cmd, ""):
        return None
    out = CommandAction.replaceTag(f"<{cmd}>", a._properties, conditional="family=inet4", cache=a._substCache)
    return CommandAction.replaceDynamicTags(out, {"ip": IPAddr(ip), "bantime": bantime, "failures": 5, "time": 0})

fails = 0
def check(name, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + name); fails += 0 if ok else 1

for cmd in ("actionban", "actionunban", "actionprolong"):
    c = render(cmd)
    check(f"{cmd} is defined", c is not None)
    if c is None: continue
    for code, want in ((200, 0), (206, 1), (403, 1), (500, 1)):
        reply["code"] = code; seen.clear()
        rc = subprocess.run(["/bin/sh", "-c", c], capture_output=True).returncode
        check(f"{cmd} on HTTP {code} exits {'0' if want == 0 else 'non-zero'} (rc={rc})", (rc == 0) == (want == 0))
        check(f"{cmd} on HTTP {code} reached the API with the key", len(seen) == 1 and seen[0][1] == "Bearer TESTKEY")
srv.shutdown()
# control: an unreachable API must also fail
c = render("actionban").replace(url, "http://127.0.0.1:1/v2/signal")
check("actionban with the API unreachable exits non-zero", subprocess.run(["/bin/sh", "-c", c], capture_output=True).returncode != 0)
sys.exit(1 if fails else 0)
