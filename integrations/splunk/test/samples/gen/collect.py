"""Turns the raw output of the generate.sh runs into the files under samples/.
Nothing is written that Synapse did not produce. It only
  - replaces the two container addresses with documentation addresses,
  - drops lines whose shape an earlier line already shows.
Each stream lists the shapes it MUST keep. If Synapse did not produce one,
this script exits non-zero and writes no sample for that stream: a stale file
from an earlier run is removed, never kept."""
import ipaddress
import json
import os
import re
import sys

work, out = sys.argv[1], sys.argv[2]
errors = []
OUTPUTS = []  # every sample path this script owns


def read(run, part, name):
    p = os.path.join(work, run, part, name)
    if not os.path.exists(p):
        return []
    text = open(p, "rb").read().decode("utf-8")
    ips = json.load(open(os.path.join(work, run, "ips.json")))
    text = text.replace(ips["synapse"], "192.0.2.10").replace(ips["client"], "198.51.100.20")
    return text.splitlines()


def jd(l):
    try:
        return json.loads(l)
    except ValueError:
        return {}


def select(lines, key=None, required=(), head=0):
    """Lines to keep, in their order: the first `head`, the first match of each
    required shape, and the first line of every other `key` value."""
    keep, bad = set(range(min(head, len(lines)))), []
    for name, pred in required:
        i = next((i for i, l in enumerate(lines) if pred(l)), None)
        if i is None:
            bad.append(name)
        else:
            keep.add(i)
    seen = set()
    for i, l in enumerate(lines):
        if key and key(l) not in seen:
            seen.add(key(l))
            keep.add(i)
    return [lines[i] for i in sorted(keep)], bad


def write(rel, lines, bad=()):
    OUTPUTS.append(rel)
    path = os.path.join(out, rel)
    if os.path.exists(path):
        os.remove(path)
    if not lines:
        errors.append("%s: Synapse produced no output" % rel)
        return
    if bad:
        errors.append("%s: required shape missing: %s" % (rel, ", ".join(bad)))
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("%5d lines  %s" % (len(lines), rel))


def emit(rel, lines, **kw):
    kept, bad = select(lines, **kw)
    write(rel, kept, bad)


def shape(l):
    return re.sub(r"\d+", "N", l)[:60]


def attrs(l):
    return {a["key"]: str(list(a["value"].values())[0]) for a in jd(l).get("attributes", [])}


def has(s):
    return lambda l: s in l


def pri(n):
    return lambda l: l.startswith("<%d>" % n)


def fp_key(l):
    skip = {"timestamp", "src_ip", "src_port", "dst_ip", "dst_port"}
    return tuple(sorted(k for k in jd(l) if k not in skip))


def eve_key(l):
    d = jd(l)
    return (d.get("event_type"), d.get("alert", {}).get("signature_id"),
            d.get("stats", {}).get("worker"), tuple(sorted(d)))


def kind(l):
    return tuple(l.split("|")[4:6])


def status(code):
    return lambda l: jd(l).get("response", {}).get("status") == code


def blocked(l):
    return jd(l).get("response", {}).get("status") == 403 and bool(jd(l).get("remediation"))


emit("access/access.log", read("a", "s", "access.log"),
     key=lambda l: (jd(l)["http"].get("path"), jd(l).get("response", {}).get("status")),
     required=[("WAF 403 block with remediation", blocked), ("429 rate limit", status(429)),
               ("UTF-8 path", has('"path":"/café"'))])
app_req = [("ERROR line", lambda l: " ERROR " in l or '"level":"ERROR"' in l),
           ("WARN line", lambda l: " WARN " in l or '"level":"WARN"' in l)]
emit("app/app.text.log", read("a", "s", "app.log"), required=app_req, head=20)
emit("app/app.json.log", read("b", "s", "app.log"), required=app_req, head=20)
emit("app/error.log", read("a", "s", "error.log"), key=lambda l: l)
sysl = read("a", "d", "syslog.raw")
emit("syslog/syslog.raw", sysl, key=lambda l: object() if l.startswith("<27>") else l[:3] + shape(l.split("]: ", 1)[-1])[:28], required=[
    ("PRI 27", pri(27)), ("PRI 28", pri(28)), ("PRI 30", pri(30)),
    ("duplicated ERROR pair", lambda l: sum(x == l for x in sysl) > 1 and l.startswith("<27>"))])
emit("events/events.text.log", read("a", "s", "events.log"), key=lambda l: l,
     required=[("ratelimit", has("[waf/ratelimit]")), ("ids notice", has("[ids/notice]"))])
emit("events/events.json.log", read("b", "s", "events.log"), key=lambda l: l,
     required=[("ids with nested eve", lambda l: "eve" in jd(l))])
emit("events/events.cef.log", read("c", "s", "events.log"), key=lambda l: l,
     required=[("CEF line", lambda l: l.startswith("CEF:0|"))])
emit("eve/eve.json", read("a", "s", "eve.json"), key=eve_key, required=(
    [("alert sid 1000001", has('"signature_id":1000001')), ("alert sid 1000002", has('"signature_id":1000002'))]
    + [("stats worker thalamus_ids_afpacket", lambda l: jd(l).get("stats", {}).get("worker") == "thalamus_ids_afpacket")]))
emit("eventbridge/eventbridge.log", read("a", "s", "eventbridge.log"), key=fp_key,
     required=[(k, has('"%s"' % k)) for k in ("ja4t", "ja4ts", "ja4", "ja4s", "asn_org")])
emit("telemetry/telemetry.log", read("a", "s", "telemetry.log"), key=lambda l: attrs(l).get("synapse.rule_id"),
     required=[(r, (lambda r: lambda l: attrs(l).get("synapse.rule_id") == r)(r))
               for r in ("waf-block-admin", "waf-ratelimit-login", "sid:1000001", "sid:1000002")])
cefreq = [("http_access", has("|http_access|")), ("waf block", has("|waf-block-")), ("ids", has("|sid:1000001|"))]
emit("cef/cef.file.log", read("a", "s", "cef.log"), key=kind, required=cefreq)
emit("cef/cef.udp-rfc5424.raw", read("a", "d", "cef-udp.raw"), key=kind, required=cefreq)
emit("cef/cef.udp-rfc3164.raw", read("c", "d", "cef-udp.raw"), key=kind, required=cefreq)


def tcp_frames():
    """Keep the first frame of each kind. The address replacement changes a
    frame's length, so the octet count is written again for each kept frame."""
    rel = "cef/cef.tcp-octet-counted.raw"
    OUTPUTS.append(rel)
    path = os.path.join(out, rel)
    if os.path.exists(path):
        os.remove(path)
    p = os.path.join(work, "b", "d", "cef-tcp.raw")
    if not os.path.exists(p):
        errors.append("%s: Synapse produced no output" % rel)
        return
    data = open(p, "rb").read()
    ips = json.load(open(os.path.join(work, "b", "ips.json")))
    kept, seen, i = [], set(), 0
    while i < len(data):
        m = re.compile(rb"(\d+) ").match(data, i)
        if not m:
            errors.append("%s: not octet-counted at offset %d" % (rel, i))
            return
        end = m.end() + int(m.group(1))
        body = data[m.end():end].decode("utf-8")
        body = body.replace(ips["synapse"], "192.0.2.10").replace(ips["client"], "198.51.100.20")
        if kind(body) not in seen:
            seen.add(kind(body))
            kept.append("%d %s" % (len(body.encode("utf-8")), body))
        i = end
    if not kept:
        errors.append("%s: no frames" % rel)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("".join(kept))
    print("%5d frames %s" % (len(kept), rel))


tcp_frames()

OK_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "127.0.0.0/8", "0.0.0.0/32")]
V4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
V6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")


def leaks(text):
    found = []
    for m in V4.finditer(text):
        try:
            a = ipaddress.ip_address(m.group(0))
        except ValueError:
            continue
        if not any(a in n for n in OK_NETS):
            found.append(m.group(0))
    for m in V6.finditer(text):
        s = m.group(0)
        if s.count(":") < 2 or re.fullmatch(r"[\d:]+", s) and re.fullmatch(r"\d{1,2}(:\d{2}){1,2}", s):
            continue  # a clock time
        try:
            ipaddress.IPv6Address(s)
        except ValueError:
            continue
        found.append(s)
    return found


for rel in OUTPUTS:
    p = os.path.join(out, rel)
    if os.path.exists(p):
        found = sorted(set(leaks(open(p, encoding="utf-8").read())))
        for a in found:
            errors.append("%s: address left in the sample: %s" % (rel, a))
        if found:
            os.remove(p)

if errors:
    print("collect failed:\n  " + "\n  ".join(errors), file=sys.stderr)
    sys.exit(1)
