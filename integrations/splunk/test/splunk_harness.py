"""Docker container and Splunk client for the TA tests.

Owns everything that talks to Splunk: creating, starting and removing the
container, waiting until it is ready, searching, and sending events in each
way the README describes. The streams (test/streams/*.py) hold the data and
the checks; test/test_splunk.py ties the two together.

Environment:
  SPLUNK_IMAGE           default: splunk/splunk:9.0.1
  SPLUNK_TEST_NAME       container name (default: g0s-splunk-ta-test). Set it
                         to run a second test beside another on the same host.
  SPLUNK_TEST_PORT_BASE  default 15000. The host ports are base+514 (tcp 5514),
                         base+515 (tcp 5515), base+516 (udp 5516),
                         base+3088 (HEC) and base+3089 (management), which at
                         the default are 15514, 15515, 15516, 18088 and 18089.
                         A different base shifts all of them. Two runs on one
                         host need bases that do not share a port: step by
                         1000 (e.g. 15000, 16000).
"""
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from collections import namedtuple

IMAGE = os.environ.get("SPLUNK_IMAGE", "splunk/splunk:9.0.1")
NAME = os.environ.get("SPLUNK_TEST_NAME", "g0s-splunk-ta-test")
PORT_BASE = int(os.environ.get("SPLUNK_TEST_PORT_BASE", "15000"))
if not 0 < PORT_BASE <= 65535 - 3089:
    sys.exit("error: SPLUNK_TEST_PORT_BASE must be between 1 and %d" % (65535 - 3089))
PASSWORD = "Synapse-test-1"
HEC_TOKEN = "11111111-2222-3333-4444-555555555555"
PORTS = {
    "tcp3164": PORT_BASE + 514,
    "tcp5424": PORT_BASE + 515,
    "udp": PORT_BASE + 516,
    "hec": PORT_BASE + 3088,
    "mgmt": PORT_BASE + 3089,
}

# One thing to send. kind is "file", "tcp", "udp", "hec_raw" or "hec_event".
Source = namedtuple("Source", "kind sourcetype lines")


def sh(*cmd, check=True):
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

ADMIN = "Basic " + b64encode(f"admin:{PASSWORD}".encode()).decode()
HEC = f"Splunk {HEC_TOKEN}"


def request(port, path, data=None, auth=None, timeout=30):
    req = urllib.request.Request(f"https://127.0.0.1:{port}{path}", data=data)
    if auth:
        req.add_header("Authorization", auth)
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read().decode()


created = False


def create(data_dir):
    """Create the container (not started) with `data_dir` mounted at /test-data."""
    global created
    running = sh("docker", "ps", "-q", "--filter", f"name=^{NAME}$").stdout.strip()
    if running:
        sys.exit(f"error: a container named {NAME} is running; it belongs to another "
                 "run. Set SPLUNK_TEST_NAME to a different name.")
    sh("docker", "rm", "-fv", NAME, check=False)
    sh("docker", "create", "--name", NAME,
       "-e", "SPLUNK_START_ARGS=--accept-license", "-e", f"SPLUNK_PASSWORD={PASSWORD}",
       "-e", f"SPLUNK_HEC_TOKEN={HEC_TOKEN}",
       "-p", f"127.0.0.1:{PORTS['mgmt']}:8089", "-p", f"127.0.0.1:{PORTS['hec']}:8088",
       "-p", f"127.0.0.1:{PORTS['tcp3164']}:5514", "-p", f"127.0.0.1:{PORTS['tcp5424']}:5515",
       "-p", f"127.0.0.1:{PORTS['udp']}:5516/udp",
       "-v", f"{data_dir}:/test-data:ro",
       IMAGE)
    created = True


def install(ta_dir, inputs_app_dir):
    # Copied in rather than mounted: the image's setup changes the owner of
    # everything under etc/apps, which fails on a read-only mount and leaves
    # files on the host that the user cannot delete on a writable one. The
    # image fills /opt/splunk/etc from /opt/splunk-etc on first start.
    sh("docker", "cp", ta_dir, f"{NAME}:/opt/splunk-etc/apps/TA-gen0sec-synapse")
    sh("docker", "cp", inputs_app_dir, f"{NAME}:/opt/splunk-etc/apps/g0s_test_inputs")


def start():
    sh("docker", "start", NAME)


def install_ta(ta_dir):
    """Replace the installed add-on's files with those of `ta_dir`. Files
    that `ta_dir` lacks are left; copy a whole add-on to replace it."""
    sh("docker", "cp", f"{ta_dir}/.", f"{NAME}:/opt/splunk/etc/apps/TA-gen0sec-synapse")


def startup_time():
    out = request(PORTS["mgmt"], "/services/server/info?output_mode=json", auth=ADMIN, timeout=5)
    return json.loads(out)["entry"][0]["content"]["startup_time"]


def inputs_listening():
    """True when splunkd listens on the TCP and UDP input ports. Probed from
    inside the container: Docker's proxy accepts a connection on a published
    port whether or not anything listens behind it."""
    for port in (5514, 5515):
        if sh("docker", "exec", NAME, "bash", "-c", f"exec 3<>/dev/tcp/127.0.0.1/{port}", check=False).returncode:
            return False
    udp = sh("docker", "exec", NAME, "netstat", "-lun", check=False)
    return udp.returncode == 0 and ":5516 " in udp.stdout


def restart(deadline_s=300):
    """Restart splunkd through its REST endpoint and wait until a new process
    answers on the management port and HEC, and listens on the input ports. (`splunk
    restart` through docker exec leaves splunkd dead.)"""
    before = startup_time()
    request(PORTS["mgmt"], "/services/server/control/restart", data=b"", auth=ADMIN)
    end = time.time() + deadline_s
    while time.time() < end:
        try:
            if startup_time() != before and hec_token_accepted() and inputs_listening():
                return
        except Exception:
            pass
        time.sleep(2)
    sys.exit("error: Splunk did not come back after a restart; see `docker logs %s`" % NAME)


def remove():
    """Remove the container with its volumes, but only one this run created."""
    if created:
        sh("docker", "rm", "-fv", NAME, check=False)


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
                if inputs_listening():
                    return
        except Exception:
            pass
        time.sleep(5)
    sys.exit("error: Splunk did not become ready; see `docker logs %s`" % NAME)


def search(query):
    body = urllib.parse.urlencode({"search": query, "output_mode": "json"}).encode()
    out = request(PORTS["mgmt"], "/services/search/jobs/export", data=body, auth=ADMIN, timeout=120)
    return [json.loads(l)["result"] for l in out.splitlines() if l.strip() and '"result"' in l]


def write_monitor_file(data_dir, source, lines):
    """Write `lines` where the monitor input reads the file whose Splunk
    `source` is the container path `source` (under /test-data)."""
    path = os.path.join(data_dir, os.path.relpath(source, "/test-data"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    # Splunk runs as its own user in the container; a strict umask would
    # leave the file unreadable to it.
    os.chmod(os.path.dirname(path), 0o755)
    os.chmod(path, 0o644)


def send_tcp(port, lines):
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(("\n".join(lines) + "\n").encode())


def send_udp(port, lines):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for l in lines:
            s.sendto(l.encode(), ("127.0.0.1", port))


def send_hec_raw(source, sourcetype, lines):
    q = urllib.parse.urlencode({"sourcetype": sourcetype, "source": source})
    request(PORTS["hec"], f"/services/collector/raw?{q}",
            data=("\n".join(lines) + "\n").encode(), auth=HEC)


def send_hec_event(source, sourcetype, lines):
    """auto_extract_timestamp=true and no `time`, as the README sets up
    AxoSyslog's splunk-hec-event(), so Splunk takes the record's own time."""
    events = "".join(json.dumps({"event": l, "sourcetype": sourcetype, "source": source})
                     for l in lines)
    request(PORTS["hec"], "/services/collector/event?auto_extract_timestamp=true",
            data=events.encode(), auth=HEC)
