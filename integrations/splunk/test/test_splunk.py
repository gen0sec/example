"""End-to-end test of TA-gen0sec-synapse in a real Splunk 9.0.1.

Starts splunk/splunk:9.0.1 in docker with the add-on installed, sends the
sample access records in every way the README describes, then checks what
Splunk made of each one: its sourcetype, its timestamp, that _raw is the
record's JSON, and the CIM fields.

Ingest paths covered:
  /test-data/syslog-3164.log  file written by AxoSyslog (BSD header), read by a monitor input
  /test-data/plain.jsonl      file with the JSON only, read by a monitor input
  tcp:5514                    AxoSyslog network() (RFC 3164, newline framed)
  tcp:5515                    AxoSyslog network(flags(syslog-protocol)) (RFC 5424, newline framed)
  hec-raw                     AxoSyslog splunk-hec-raw() (its default ISO-date header),
                              sourcetype gen0sec:synapse
  hec-event                   AxoSyslog splunk-hec-event() as the README sets it up:
                              sourcetype gen0sec:synapse:access, time("") so no
                              `time` is sent, and auto_extract_timestamp=true so
                              Splunk takes the record's own time. (With a `time`,
                              Splunk 9.0.1 keeps it and ignores the record's.)

The header variants also carry one synapse application log line, which must
keep the input sourcetype and stay out of the access sourcetype.

Needs docker. Usage, from integrations/splunk/:  python3 test/test_splunk.py
Environment:
  TA_DIR        the add-on to install (default: ./TA-gen0sec-synapse)
  SPLUNK_IMAGE  default: splunk/splunk:9.0.1
  KEEP=1        leave the container running after the test
Exit status: 0 when every check passes, 1 otherwise.
"""
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TA_DIR = os.path.abspath(os.environ.get("TA_DIR", os.path.join(HERE, "..", "TA-gen0sec-synapse")))
IMAGE = os.environ.get("SPLUNK_IMAGE", "splunk/splunk:9.0.1")
NAME = "g0s-splunk-ta-test"
PASSWORD = "Synapse-test-1"
HEC_TOKEN = "11111111-2222-3333-4444-555555555555"
PORTS = {"mgmt": 18089, "hec": 18088, "tcp3164": 15514, "tcp5424": 15515}

# Sent exactly as stored, so the bytes Splunk sees are the bytes Synapse wrote.
RAW_LINES = open(os.path.join(HERE, "samples", "records.jsonl")).read().splitlines()
RECORDS = [json.loads(l) for l in RAW_LINES]
APP_LINE = "WARN synapse_proxy::bgservice - Failed to load upstreams configuration"

# What Splunk must show for each record. Written out by hand rather than
# derived from the records, so a wrong mapping cannot agree with itself.
EXPECTED = {
    "req_1792506501384797276": {
        "src": "127.0.0.1", "src_port": "33450", "dest": "127.0.0.1", "dest_port": "18443",
        "http_method": "GET", "uri_path": "/config.yaml", "site": "app.local", "status": "200",
        "action": "allowed", "synapse_mode": "proxy", "http_user_agent": "curl/8.5.0",
        "bytes_in": "0", "bytes_out": "402", "duration": "11.708",
        "url": "https://app.local:18443/config.yaml", "vendor": "Gen0Sec", "product": "Synapse",
    },
    "pt_1792506501398845833": {
        "src": "127.0.0.1", "src_port": "33452", "dest": "127.0.0.1", "dest_port": "18443",
        "http_method": None, "uri_path": None, "site": "db.local", "status": "0",
        "action": "allowed", "synapse_mode": "passthrough", "http_user_agent": None,
        "bytes_in": "720", "bytes_out": "7068", "duration": "3.163375",
        "url": None, "vendor": "Gen0Sec", "product": "Synapse",
    },
    "req_1792506501488163778": {
        "src_port": "33502", "http_method": "GET", "status": "200", "action": "allowed",
        "synapse_mode": "proxy",
        "http_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36",
        "duration": "1.27",
    },
    "req_1792506501500000001": {
        "uri_path": "/admin", "status": "403", "action": "blocked", "synapse_mode": "proxy",
        "url": "https://app.local:18443/admin",
    },
    # A challenge stops the request before the upstream, as a block does.
    "req_1792506501500000002": {
        "uri_path": "/login", "status": "403", "action": "blocked", "synapse_mode": "proxy",
    },
    "req_1792506501500000003": {
        "uri_path": "/search", "uri_query": "q=synapse&page=2", "status": "200", "action": "allowed",
        "url": "https://app.local:18443/search?q=synapse&page=2",
    },
    "req_1792506501500000004": {
        "src": "127.0.0.1", "http_method": None, "uri_path": None, "uri_query": None, "url": None,
        "site": None, "http_user_agent": None, "status": "400", "action": "allowed",
        "synapse_mode": "proxy",
    },
    # Its request body puts everything after `http` past Splunk's default
    # 5000-byte limit for automatic JSON extraction.
    "req_1792506501500000005": {
        "src": "127.0.0.1", "dest_port": "18443", "http_method": "POST", "uri_path": "/admin/upload",
        "site": "app.local", "status": "403", "action": "blocked", "synapse_mode": "proxy",
        "bytes_in": "8192", "duration": "11.708", "http_content_type": "text/plain",
    },
}
FIELDS = sorted({f for e in EXPECTED.values() for f in e})


# The headers' time is hours away from the records' own, so the test can tell
# which one Splunk used: records take their own time, app lines the header's.
HEADER_TIME = (10, 20, 9, 0, 5)  # month, day, hour, minute, second (UTC)


def header_3164(rec):
    return "<30>Oct 20 09:00:05 synapse-host synapse[1]: "


def header_3164_file(rec):
    return "Oct 20 09:00:05 synapse-host synapse[1]: "


def header_5424(rec):
    return "<30>1 2026-10-20T09:00:05.000000+00:00 synapse-host synapse 1 - - "


def header_hec_raw(rec):
    return "2026-10-20T09:00:05+00:00 synapse-host synapse[1]: "


def lines(header=None):
    """Each record as one line, after `header` when given. A header variant
    also carries one app log line, as Synapse's syslog stream does."""
    prefix = header(None) if header else ""
    out = [prefix + l for l in RAW_LINES]
    if header:
        out.insert(1, prefix + APP_LINE)
    return out


# Paths that carry a syslog header: the host must come from it.
HEADER_HOST = "synapse-host"
HEADERED = {"/test-data/syslog-3164.log", "tcp:5514", "tcp:5515", "hec-raw"}

SOURCES = {
    "/test-data/syslog-3164.log": lines(header_3164_file),
    "/test-data/plain.jsonl": lines(None),
    "tcp:5514": lines(header_3164),
    "tcp:5515": lines(header_5424),
    "hec-raw": lines(header_hec_raw),
    "hec-event": lines(None),
}


def sh(*cmd, check=True):
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def request(port, path, data=None, auth=None, timeout=30):
    req = urllib.request.Request(f"https://127.0.0.1:{port}{path}", data=data)
    if auth:
        req.add_header("Authorization", auth)
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read().decode()


ADMIN = "Basic " + b64encode(f"admin:{PASSWORD}".encode()).decode()
HEC = f"Splunk {HEC_TOKEN}"


def hec_token_accepted():
    """An empty post is refused with 400 "No data" once the token exists, and
    with 403 before it does."""
    try:
        request(PORTS["hec"], "/services/collector/event", data=b"", auth=HEC, timeout=5)
        return True
    except urllib.error.HTTPError as e:
        return e.code == 400


def wait_ready(deadline_s=600):
    # splunkd answers while the image is still provisioning (and restarts it
    # once more), so wait for the image's own health check to pass as well.
    end = time.time() + deadline_s
    while time.time() < end:
        health = sh("docker", "inspect", "-f", "{{.State.Health.Status}}", NAME, check=False).stdout.strip()
        try:
            if health == "healthy" and hec_token_accepted():
                request(PORTS["mgmt"], "/services/server/info", auth=ADMIN, timeout=5)
                return
        except Exception:
            pass
        time.sleep(5)
    sys.exit("error: Splunk did not become ready; see `docker logs %s`" % NAME)


def search(query):
    body = urllib.parse.urlencode({"search": query, "output_mode": "json"}).encode()
    out = request(PORTS["mgmt"], "/services/search/jobs/export", data=body, auth=ADMIN, timeout=120)
    return [json.loads(l)["result"] for l in out.splitlines() if l.strip() and '"result"' in l]


def send():
    for port, src in ((PORTS["tcp3164"], "tcp:5514"), (PORTS["tcp5424"], "tcp:5515")):
        with socket.create_connection(("127.0.0.1", port)) as s:
            s.sendall(("\n".join(SOURCES[src]) + "\n").encode())
    q = urllib.parse.urlencode({"sourcetype": "gen0sec:synapse", "source": "hec-raw"})
    request(PORTS["hec"], f"/services/collector/raw?{q}",
            data=("\n".join(SOURCES["hec-raw"]) + "\n").encode(), auth=HEC)
    events = "".join(json.dumps({
        "event": l, "sourcetype": "gen0sec:synapse:access", "source": "hec-event",
    }) for l in SOURCES["hec-event"])
    request(PORTS["hec"], "/services/collector/event?auto_extract_timestamp=true",
            data=events.encode(), auth=HEC)


def epoch(ts):
    whole, frac = ts.rstrip("Z").split(".")
    t = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return round(t + float("0." + frac), 6)


def collect(deadline_s=180):
    want = {src: len(ls) for src, ls in SOURCES.items()}
    query = ("search index=main source IN (%s) | eval raw=_raw, t=_time | table source sourcetype host t raw request_id %s"
             % (",".join(f'"{s}"' for s in SOURCES), " ".join(FIELDS)))
    end = time.time() + deadline_s
    while True:
        rows = search(query)
        got = {}
        for r in rows:
            got.setdefault(r["source"], []).append(r)
        if all(len(got.get(s, [])) >= n for s, n in want.items()) or time.time() > end:
            return got
        time.sleep(5)


def check(got):
    fails = []
    for src, sent in SOURCES.items():
        rows = got.get(src, [])
        if len(rows) != len(sent):
            fails.append(f"{src}: {len(rows)} events, sent {len(sent)}")
        app = [r for r in rows if APP_LINE in r.get("raw", "")]
        if any(l.endswith(APP_LINE) for l in sent):
            if len(app) != 1 or app[0]["sourcetype"] != "gen0sec:synapse":
                fails.append(f"{src}: app log line: {[a['sourcetype'] for a in app]}, want one gen0sec:synapse")
            else:
                # An RFC 3164 header has no year, so compare without it.
                got_t = tuple(time.gmtime(float(app[0]["t"]))[1:6])
                if got_t != HEADER_TIME:
                    fails.append(f"{src}: app log line _time {got_t}, want the header's {HEADER_TIME}")
        for rec in RECORDS:
            rid = rec["request_id"]
            match = [r for r in rows if f'"request_id":"{rid}"' in r.get("raw", "")]
            where = f"{src} {rid}"
            if len(match) != 1:
                fails.append(f"{where}: found {len(match)} events")
                continue
            r = match[0]
            if r["sourcetype"] != "gen0sec:synapse:access":
                fails.append(f"{where}: sourcetype {r['sourcetype']}")
            try:
                if json.loads(r["raw"]) != rec:
                    fails.append(f"{where}: _raw JSON differs from the record")
            except ValueError:
                fails.append(f"{where}: _raw is not pure JSON: {r['raw'][:80]!r}")
            if abs(float(r["t"]) - epoch(rec["timestamp"])) > 0.001:
                fails.append(f"{where}: _time {r['t']}, want {epoch(rec['timestamp'])}")
            if src in HEADERED and r.get("host") != HEADER_HOST:
                fails.append(f"{where}: host {r.get('host')!r}, want {HEADER_HOST!r}")
            if r.get("request_id") != rid:
                fails.append(f"{where}: request_id field {r.get('request_id')!r}")
            for field, want in EXPECTED[rid].items():
                have = r.get(field)
                if have != want:
                    fails.append(f"{where}: {field}={have!r}, want {want!r}")
    return fails


def main():
    if not os.path.isdir(TA_DIR):
        sys.exit(f"error: add-on not found at {TA_DIR}")
    work = tempfile.mkdtemp(prefix="g0s-splunk-")
    data = os.path.join(work, "test-data")
    inputs = os.path.join(work, "g0s_test_inputs", "default")
    os.makedirs(data)
    os.makedirs(inputs)
    for src in ("/test-data/syslog-3164.log", "/test-data/plain.jsonl"):
        with open(os.path.join(data, os.path.basename(src)), "w") as f:
            f.write("\n".join(SOURCES[src]) + "\n")
    with open(os.path.join(inputs, "inputs.conf"), "w") as f:
        f.write("[monitor:///test-data]\nindex = main\nsourcetype = gen0sec:synapse\n\n"
                "[tcp://5514]\nindex = main\nsourcetype = gen0sec:synapse\nconnection_host = none\n\n"
                "[tcp://5515]\nindex = main\nsourcetype = gen0sec:synapse\nconnection_host = none\n")
    os.chmod(work, 0o755)
    for root, dirs, files in os.walk(work):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)

    try:
        sh("docker", "rm", "-f", NAME, check=False)
        sh("docker", "create", "--name", NAME,
           "-e", "SPLUNK_START_ARGS=--accept-license", "-e", f"SPLUNK_PASSWORD={PASSWORD}",
           "-e", f"SPLUNK_HEC_TOKEN={HEC_TOKEN}",
           "-p", f"127.0.0.1:{PORTS['mgmt']}:8089", "-p", f"127.0.0.1:{PORTS['hec']}:8088",
           "-p", f"127.0.0.1:{PORTS['tcp3164']}:5514", "-p", f"127.0.0.1:{PORTS['tcp5424']}:5515",
           "-v", f"{data}:/test-data:ro",
           IMAGE)
        # Copied in rather than mounted: the image's setup changes the owner of
        # everything under etc/apps, which fails on a read-only mount and leaves
        # files on the host that the user cannot delete on a writable one. The
        # image fills /opt/splunk/etc from /opt/splunk-etc on first start.
        sh("docker", "cp", TA_DIR, f"{NAME}:/opt/splunk-etc/apps/TA-gen0sec-synapse")
        sh("docker", "cp", os.path.dirname(inputs), f"{NAME}:/opt/splunk-etc/apps/g0s_test_inputs")
        sh("docker", "start", NAME)
        print(f"waiting for {IMAGE} ...", flush=True)
        wait_ready()
        send()
        fails = check(collect())
    finally:
        if os.environ.get("KEEP") != "1":
            sh("docker", "rm", "-f", NAME, check=False)
            shutil.rmtree(work, ignore_errors=True)
    total = sum(len(v) for v in SOURCES.values())
    if fails:
        print(f"FAIL: {len(fails)} problem(s) across {total} events")
        for f in fails:
            print("  " + f)
        return 1
    print(f"PASS: {total} events over {len(SOURCES)} ingest paths, all fields as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
