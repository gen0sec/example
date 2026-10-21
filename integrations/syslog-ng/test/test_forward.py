"""Test of synapse-forward.conf in two AxoSyslog containers.

The sender container runs the shipped config. Its host and port point at a
receiver container, which writes every datagram it gets, unparsed, to a file.
Inside the sender, test/emit.py sends Synapse's wire format to /dev/log and to
UDP 127.0.0.1:514, one datagram per message, as Synapse 0.8.8 does:

    <PRI>Mmm DD HH:MM:SS synapse[PID]: message

The test then checks that each message that should arrive did, with its
priority, program, pid and text unchanged, and that the one above the UDP
ceiling did not.

Needs docker. Usage, from integrations/syslog-ng/:  python3 test/test_forward.py
Environment:
  AXOSYSLOG_IMAGE  default: ghcr.io/axoflow/axosyslog:4.29.0

  --controls    instead of one run, make each broken copy of the config in
                CONTROLS and run the test on it. A control is killed when the
                run reports a problem that matches its `must_fail`. Prints
                killed or survived per control; exit 1 if any survived.
                `make test-syslog-ng-controls` runs it.
  --config FILE the config to test (default: ../synapse-forward.conf)
  -v            print what the receiver got and the sender's log
Exit status: 0 when every check passes (every control killed), 1 otherwise.
"""
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.environ.get("AXOSYSLOG_IMAGE", "ghcr.io/axoflow/axosyslog:4.29.0")
CONF = os.path.join(HERE, "..", "synapse-forward.conf")
RECEIVER_CONF = """@version: 4.26
source s_in { network(ip("0.0.0.0") port(1514) transport("udp") log-msg-size(131072) flags(no-parse)); };
destination d_file { file("/var/log/received.log" template("$MSG\\n")); };
log { source(s_in); destination(d_file); };
"""
RECEIVER_PORT = 1514
SENDER_HOSTNAME = "g0s-sender"
# <PRI>Mmm DD HH:MM:SS HOST synapse[PID]: TEXT, as forwarded. The day is
# space-padded here, unlike on Synapse's wire.
LINE = re.compile(r"^<(\d+)>[A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d (\S+) synapse\[(\d+)\]: (.*)$", re.S)

# outcome: "full" (arrives unchanged) or "truncated" (arrives cut to the UDP
# datagram ceiling).
Case = namedtuple("Case", "name mode pri text outcome")
UDP_MAX = 65507
Control = namedtuple("Control", "name pattern replacement must_fail")

# Each pattern must match exactly once in the config, so a control cannot
# pass because the config moved on from it.
CONTROLS = [
    Control("system() source removed", r"^\s*system\(\);\n", "",
            re.compile(r"^unix .*not delivered")),
    Control("localhost UDP source removed", r"^\s*network\(ip\(\"127\.0\.0\.1\"\).*\n", "",
            re.compile(r"^udp .*not delivered")),
    Control("filter matches another program", r'program\("synapse"\)', 'program("other")',
            re.compile(r"^unix .*not delivered")),
    Control("destination port changed", r"^(    network\(\"`synapse_remote_host`\" transport\(\"udp\"\) )port\(`synapse_remote_port`\)", r"\1port(9)",
            re.compile(r"^unix .*not delivered")),
    # Proves the test sees local truncation: a log-msg-size below the record
    # sizes cuts them before they are forwarded.
    Control("log-msg-size cut to 8192", r"^(@define synapse_remote_port .*)$",
            r"\1\noptions { log-msg-size(8192); };",
            re.compile(r"^unix record-16k: not delivered")),
]


def sh(*cmd, check=True, input=None):
    return subprocess.run(cmd, check=check, capture_output=True, text=True, input=input)


def records():
    with open(os.path.join(HERE, "samples", "access.jsonl")) as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def padded(record, size):
    """The record with one extra header, so it is `size` bytes of valid JSON."""
    rec = json.loads(record)
    rec["http"]["headers"]["x-pad"] = ""
    base = len(json.dumps(rec, separators=(",", ":"), ensure_ascii=False).encode())
    rec["http"]["headers"]["x-pad"] = "a" * (size - base)
    out = json.dumps(rec, separators=(",", ":"), ensure_ascii=False)
    assert len(out.encode()) == size
    return out


def cases():
    recs = records()
    out = []
    app = [("app-error", 27, "ERROR synapse: upstream connection failed"),
           ("app-info", 30, "INFO synapse: configuration reloaded")]
    for mode in ("unix", "udp"):
        for name, pri, text in app:
            out.append(Case(f"{mode} {name}", mode, pri, text, "full"))
        for i, rec in enumerate(recs):
            out.append(Case(f"{mode} record-{i}", mode, 30, rec, "full"))
        for label, size in (("16k", 16 * 1024), ("60k", 60 * 1024)):
            out.append(Case(f"{mode} record-{label}", mode, 30, padded(recs[0], size), "full"))
    # Above the UDP datagram ceiling of 65,507 bytes.
    out.append(Case("unix record-70k", "unix", 30, padded(recs[0], 70 * 1024), "truncated"))
    # Sent last on each path: once they arrive, anything sent before them has.
    for mode in ("unix", "udp"):
        out.append(Case(f"{mode} sentinel", mode, 30, "INFO synapse: sentinel", "full"))
    return out


def wire(case, pid):
    ts = time.strftime("%b %d %H:%M:%S")
    return f"<{case.pri}>{ts} synapse[{pid}]: {case.text}"


class Run:
    """Containers and network of one run. Only what this run created, by the
    names it recorded, is removed."""

    def __init__(self):
        self.tag = "g0s-syslogng-%d-%s" % (os.getpid(), secrets.token_hex(3))
        self.net = self.tag + "-net"
        self.recv = self.tag + "-recv"
        self.send = self.tag + "-send"
        self.created = []  # ("container"|"network", name)
        self.tmp = tempfile.mkdtemp(prefix=self.tag)

    def start(self, conf_text):
        os.chmod(self.tmp, 0o755)
        recv_conf = os.path.join(self.tmp, "receiver.conf")
        send_conf = os.path.join(self.tmp, "sender.conf")
        for path, text in ((recv_conf, RECEIVER_CONF), (send_conf, conf_text)):
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o644)
        sh("docker", "network", "create", self.net)
        self.created.append(("network", self.net))
        for name, conf, extra in (
                (self.recv, recv_conf, []),
                (self.send, send_conf, ["--hostname", SENDER_HOSTNAME,
                                        "-v", f"{os.path.join(HERE, 'emit.py')}:/emit.py:ro"])):
            sh("docker", "run", "-d", "--name", name, "--network", self.net, *extra,
               "-v", f"{conf}:/etc/syslog-ng/syslog-ng.conf:ro", IMAGE,
               "-F", "-e", "-f", "/etc/syslog-ng/syslog-ng.conf")
            self.created.append(("container", name))
        for name in (self.recv, self.send):
            self.wait_up(name)

    def exec(self, name, *cmd, check=True, input=None):
        return sh("docker", "exec", "-i", name, *cmd, check=check, input=input)

    def wait_up(self, name, deadline_s=30):
        """Ready when syslog-ng answers its control socket and, best effort,
        the sockets it should listen on exist. Probed inside the container: a
        host connect to a published port succeeds with nothing listening."""
        end = time.time() + deadline_s
        while time.time() < end:
            if self.exec(name, "syslog-ng-ctl", "stats", check=False).returncode == 0:
                break
            time.sleep(0.5)
        else:
            sys.exit("error: syslog-ng did not start in %s; see `docker logs %s`" % (name, name))
        end = time.time() + 5
        probe = "test -S /dev/log || grep -q ':0202 ' /proc/net/udp"
        if name == self.recv:
            probe = "grep -q ':05EA ' /proc/net/udp"
        while time.time() < end:
            if self.exec(name, "sh", "-c", probe, check=False).returncode == 0:
                return
            time.sleep(0.5)

    def received(self):
        out = self.exec(self.recv, "sh", "-c", "cat /var/log/received.log 2>/dev/null; true")
        return out.stdout.split("\n")

    def sender_log(self):
        r = sh("docker", "logs", self.send, check=False)
        return r.stdout + r.stderr

    def stats(self):
        return self.exec(self.send, "syslog-ng-ctl", "stats", check=False).stdout

    def cleanup(self):
        for kind, name in reversed(self.created):
            if kind == "container":
                sh("docker", "rm", "-f", "-v", name, check=False)
            else:
                sh("docker", "network", "rm", name, check=False)
        self.created = []
        for f in os.listdir(self.tmp):
            os.unlink(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)


def set_remote(conf, run):
    """Point the config's two @define lines at the receiver."""
    for key, value in (("synapse_remote_host", '"%s"' % run.recv),
                       ("synapse_remote_port", str(RECEIVER_PORT))):
        conf, n = re.subn(r"^(@define %s ).*$" % key, lambda m: m.group(1) + value, conf, flags=re.M)
        if n != 1:
            sys.exit("error: the config must have exactly one `@define %s`" % key)
    return conf


def run_test(conf_text, verbose=False, quiet=False, deadline_s=20):
    """Run every case against `conf_text`; return a list of problems."""
    run = Run()
    problems = []
    try:
        conf_text = set_remote(conf_text, run) if "@define" in conf_text else conf_text
        run.start(conf_text)
        sent = []
        batch = []
        for i, case in enumerate(cases()):
            pid = 1000 + i
            batch.append({"mode": case.mode, "data": wire(case, pid)})
            sent.append((case, pid))
        results = json.loads(run.exec(run.send, "python3", "/emit.py", input=json.dumps(batch)).stdout)
        end = time.time() + deadline_s
        lines = []
        while time.time() < end:
            lines = run.received()
            if sum(1 for l in lines if l) >= len(sent):
                break
            time.sleep(1)
        lines = run.received()
        if verbose:
            print("sender results:", {c.name: r for (c, _), r in zip(sent, results) if r != "ok"})
            print("receiver got %d lines, sizes %s" % (len(lines) - 1, sorted(len(l) for l in lines if l)))
        got = {}
        cut = {}
        for l in lines:
            m = LINE.match(l)
            if m:
                got[(m.group(2), m.group(4))] = (int(m.group(1)), int(m.group(3)))
                if len(l.encode()) == UDP_MAX:
                    cut[m.group(2)] = m.group(4)
        for (case, pid), res in zip(sent, results):
            host = SENDER_HOSTNAME if case.mode == "unix" else "localhost"
            hit = got.get((host, case.text))
            if case.outcome == "full":
                if hit is None:
                    problems.append("%s: not delivered (sender: %s)" % (case.name, res))
                elif hit[0] != case.pri:
                    problems.append("%s: priority %d, want %d" % (case.name, hit[0], case.pri))
                elif case.mode == "udp" and hit[1] != pid:
                    problems.append("%s: pid %d, want %d" % (case.name, hit[1], pid))
            else:
                body = cut.get(host)
                if hit is not None:
                    problems.append("%s: delivered whole, over the UDP ceiling" % case.name)
                elif body is None or not case.text.startswith(body):
                    problems.append("%s: no datagram of %d bytes holding its start" % (case.name, UDP_MAX))
        if verbose or (problems and not quiet):
            print("--- sender stats (destination and source counters)")
            print("\n".join(l for l in run.stats().splitlines() if "dst." in l or "src." in l))
            print("--- sender log")
            print(run.sender_log().strip()[-3000:])
    finally:
        run.cleanup()
    return problems


def main():
    args = sys.argv[1:]
    verbose = "-v" in args
    conf_path = os.path.abspath(args[args.index("--config") + 1]) if "--config" in args else os.path.abspath(CONF)
    with open(conf_path) as f:
        conf_text = f.read()
    if "--controls" not in args:
        problems = run_test(conf_text, verbose)
        for p in problems:
            print("FAIL " + p)
        print("%d problem(s)" % len(problems) if problems else "ok")
        return 1 if problems else 0
    survived = 0
    for c in CONTROLS:
        broken, n = re.subn(c.pattern, c.replacement, conf_text, flags=re.M)
        if n != 1:
            sys.exit("error: control %r matched %d times, want 1" % (c.name, n))
        problems = run_test(broken, verbose, quiet=True)
        killed = any(c.must_fail.search(p) for p in problems)
        print("%s: %s" % ("killed" if killed else "SURVIVED", c.name))
        if not killed:
            survived += 1
            for p in problems:
                print("   saw: " + p)
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
