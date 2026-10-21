"""The access log stream: Synapse's JSON access records, sent in every way the
README describes, then checked for sourcetype, timestamp, _raw and CIM fields.

Ingest paths covered:
  /test-data/access/syslog-3164.log  file written by AxoSyslog (BSD header), read by a monitor input
  /test-data/access/plain.jsonl      file with the JSON only, read by a monitor input
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
"""
import json
import os
import re
import time
from datetime import datetime, timezone

from splunk_harness import Source

HERE = os.path.dirname(os.path.abspath(__file__))

# Sent exactly as stored, so the bytes Splunk sees are the bytes Synapse wrote.
RAW_LINES = open(os.path.join(HERE, "..", "samples", "records.jsonl")).read().splitlines()
RECORDS = [json.loads(l) for l in RAW_LINES]


# Records as a relay (a log pipeline that parses and re-writes the JSON) sends
# them. Derived from the sample records above; each gets the base record's
# request_id plus a suffix naming its shape, and is the same JSON otherwise.
#   sorted-spaced   json.dumps(sort_keys=True): event_type is not first
#   sorted-compact  the same, without the spaces
#   spaced          spaces around every separator and after the opening brace
def _spaced(rec):
    return "{ " + json.dumps(rec, separators=(" , ", " : "))[1:]


SHAPES = {
    "sorted-spaced": lambda rec: json.dumps(rec, sort_keys=True),
    "sorted-compact": lambda rec: json.dumps(rec, sort_keys=True, separators=(",", ":")),
    "spaced": _spaced,
}
# The first record, the blocked one and the 8 KiB one.
RELAY_BASES = (0, 3, 7)


def _derive(rec, shape, text):
    d = dict(rec)
    d["request_id"] = rec["request_id"] + "-" + shape
    return d, text(d)


RELAYED = [_derive(RECORDS[i], shape, text) for i in RELAY_BASES for shape, text in SHAPES.items()]
# The first record with request headers named like its own fields, as a
# client can send them. Sorted, the headers come before the record's own
# `request_id` and `timestamp`. In Synapse's own order they come after them.
_HDR = json.loads(json.dumps(RECORDS[0]))
_HDR["http"]["headers"] = {"timestamp": "2026-10-19T14:28:21.384797166Z", "request_id": "req_forged"}
RELAYED += [
    _derive(_HDR, "hdr-native", lambda r: json.dumps(r, separators=(",", ":"))),
    _derive(_HDR, "hdr-sorted-compact", SHAPES["sorted-compact"]),
    _derive(_HDR, "hdr-sorted-spaced", SHAPES["sorted-spaced"]),
]
# The first record with an error, an object that sorts before `event_type`.
# Its message holds a quote, a backslash and braces.
_ERR = dict(RECORDS[0], error={"source": "upstream", "error_type": "ConnectRefused",
                                "message": 'Failed to connect to "10.0.0.1:80" {no route} \\ x'})
RELAYED += [
    _derive(_ERR, "err-sorted-compact", SHAPES["sorted-compact"]),
    _derive(_ERR, "err-sorted-spaced", SHAPES["sorted-spaced"]),
]
# The same with a long message, the length of a stack trace: plain, and with
# a quote, a backslash and braces spread through it. A REGEX transform stops at
# Splunk's PCRE depth limit; the record must still be routed.
_LONG = "connect failed: upstream refused the connection after retry. " * 70
_ERR_LONG = dict(RECORDS[0], error={"source": "upstream", "error_type": "ConnectRefused",
                                     "message": _LONG})
_ERR_ESC = dict(RECORDS[0], error={"source": "upstream", "error_type": "ConnectRefused",
                                    "message": 'say "hi" {x} \\ ' * 400})
RELAYED += [
    _derive(_ERR_LONG, "err-long-sorted-compact", SHAPES["sorted-compact"]),
    _derive(_ERR_LONG, "err-long-sorted-spaced", SHAPES["sorted-spaced"]),
    _derive(_ERR_ESC, "err-esc-sorted-compact", SHAPES["sorted-compact"]),
    _derive(_ERR_ESC, "err-esc-sorted-spaced", SHAPES["sorted-spaced"]),
]
# One more, behind an RFC 5424 header whose structured data holds a brace. It
# is sent on tcp:5515 only, with that header.
SD_RECORD, SD_LINE = _derive(RECORDS[0], "sd", SHAPES["sorted-compact"])
SD_HEADER = '<30>1 2026-10-20T09:00:05.000000+00:00 synapse-host synapse 1 - [x@1 k="{v}"] '
SD_SOURCES = {"tcp:5515"}

RAW_LINES += [line for _, line in RELAYED]
RECORDS += [rec for rec, _ in RELAYED] + [SD_RECORD]
# The text of each record as sent, which _raw must equal.
BODY = {rec["request_id"]: l for rec, l in zip(RECORDS, RAW_LINES)}
BODY[SD_RECORD["request_id"]] = SD_LINE
# A record inside another JSON object, as a log pipeline's envelope holds it.
# It is not an access record itself, so it must stay unrouted and whole.
ENVELOPE_MARK = "g0s-envelope"
ENVELOPE = json.dumps({"host": ENVELOPE_MARK, "record": dict(RECORDS[0], request_id="req_enveloped")},
                      separators=(",", ":"))
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
    # UTF-8 as Synapse 0.8.8 wrote it. It writes the path as sent, and an
    # empty user agent for a header that is not ASCII.
    "req_1792518275950695792": {
        "uri_path": "/café", "http_user_agent": None, "status": "200", "action": "allowed",
        "url": "https://app.example.com:8443/café",
    },
    # The same record with the user agent edited to hold UTF-8.
    "req_1792518275950695790": {
        "uri_path": "/café", "http_user_agent": "Ünïcode/1.0", "status": "200", "action": "allowed",
        "url": "https://app.example.com:8443/café",
    },
}
for _rec, _ in RELAYED + [(SD_RECORD, SD_LINE)]:
    EXPECTED[_rec["request_id"]] = EXPECTED[_rec["request_id"].split("-", 1)[0]]
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


# Lines with no host before a program tag: the host must stay the input's.
# BARE has no header at all, so its host is the input's default; the others
# must show that same host. Each ends in a marker that names it.
BARE = "g0s-hostless-bare"
ISO_NO_TAG = "2026-10-20T09:00:05Z WARN g0s-hostless-iso"
BSD_NO_HOST = "<30>Oct 20 09:00:05 synapse[1]: g0s-hostless-3164"
BSD_NO_HOST_NO_PRI = "Oct 20 09:00:05 synapse[1]: g0s-hostless-3164"
RFC5424_NIL_HOST = "<30>1 2026-10-20T09:00:05.000000+00:00 - synapse 1 - - g0s-hostless-5424"
HOSTLESS = {
    "/test-data/access/syslog-3164.log": [BARE, ISO_NO_TAG, BSD_NO_HOST_NO_PRI],
    "tcp:5514": [BARE, ISO_NO_TAG, BSD_NO_HOST],
    "tcp:5515": [BARE, RFC5424_NIL_HOST],
    "hec-raw": [BARE, ISO_NO_TAG, BSD_NO_HOST],
}

# Lines whose header host must be kept: (line, marker, host). The hosts differ
# from HEADER_HOST, so the check shows the header was read.
KEEP = {
    "tcp:5514": [
        ("<30>Oct 20 09:00:05 2001:db8::1 synapse[1]: g0s-keep-ipv6-bsd", "g0s-keep-ipv6-bsd", "2001:db8::1"),
        ("<30>Oct 20 09:00:05 web-01.example.com postfix/smtpd-x.y[123]: g0s-keep-fqdn",
         "g0s-keep-fqdn", "web-01.example.com"),
    ],
    "tcp:5515": [
        ("<30>1 2026-10-20T09:00:05.000000+00:00 2001:db8::2 synapse 1 - - g0s-keep-ipv6-5424",
         "g0s-keep-ipv6-5424", "2001:db8::2"),
        ('<30>1 2026-10-20T09:00:05.000000+00:00 sd-host.example.com synapse 1 - [a x="1"][b y="2"] g0s-keep-two-sd',
         "g0s-keep-two-sd", "sd-host.example.com"),
    ],
}
MARKERS = ("g0s-hostless-bare", "g0s-hostless-iso", "g0s-hostless-3164", "g0s-hostless-5424")


def lines(header=None, src=None):
    """Each record as one line, after `header` when given. A header variant
    also carries one app log line, as Synapse's syslog stream does, and the
    hostless lines of its source."""
    prefix = header(None) if header else ""
    out = [prefix + l for l in RAW_LINES]
    if header:
        out.insert(1, prefix + APP_LINE)
    out.append(prefix + ENVELOPE)
    if src in SD_SOURCES:
        out.append(SD_HEADER + SD_LINE)
    return out + HOSTLESS.get(src, []) + [l for l, _, _ in KEEP.get(src, [])]


# Paths that carry a syslog header: the host must come from it.
HEADER_HOST = "synapse-host"
HEADERED = {"/test-data/access/syslog-3164.log", "tcp:5514", "tcp:5515", "hec-raw"}

SOURCES = {
    "/test-data/access/syslog-3164.log": Source("file", "gen0sec:synapse", lines(header_3164_file, "/test-data/access/syslog-3164.log")),
    "/test-data/access/plain.jsonl": Source("file", "gen0sec:synapse", lines(None)),
    "tcp:5514": Source("tcp", "gen0sec:synapse", lines(header_3164, "tcp:5514")),
    "tcp:5515": Source("tcp", "gen0sec:synapse", lines(header_5424, "tcp:5515")),
    "hec-raw": Source("hec_raw", "gen0sec:synapse", lines(header_hec_raw, "hec-raw")),
    "hec-event": Source("hec_event", "gen0sec:synapse:access", lines(None)),
}


def key_of(line):
    """The record's own request_id, or None for a line that has none (the
    application log line). A JSON line is read as JSON, because a request
    header can carry a `request_id` of its own and sorted keys put it first."""
    try:
        doc = json.loads(line)
        return doc.get("request_id") if isinstance(doc, dict) else None
    except ValueError:
        pass
    m = re.search(r'"request_id"\s*:\s*"([^"]*)"', line)
    return m.group(1) if m else None


def epoch(ts):
    whole, frac = ts.rstrip("Z").split(".")
    t = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return round(t + float("0." + frac), 6)


def check_hostless(src, rows):
    fails = []
    by = {m: [r for r in rows if m in r.get("raw", "")] for m in MARKERS}
    bare = by["g0s-hostless-bare"]
    if len(bare) != 1:
        return [f"{src}: hostless bare line: found {len(bare)} events"]
    default = bare[0].get("host")
    for line in HOSTLESS[src]:
        m = next(m for m in MARKERS if m in line)
        r = by[m]
        if len(r) != 1:
            fails.append(f"{src}: {m}: found {len(r)} events")
        elif r[0].get("host") != default:
            fails.append(f"{src}: {m}: host {r[0].get('host')!r}, want the input's {default!r}")
        elif r[0]["sourcetype"] != "gen0sec:synapse":
            fails.append(f"{src}: {m}: sourcetype {r[0]['sourcetype']}")
    return fails


def check(got):
    """`got` maps each source to its rows. Returns the problems found."""
    fails = []
    for src, source in SOURCES.items():
        sent = source.lines
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
        env = [r for r in rows if "req_enveloped" in r.get("raw", "")]
        want_env = [l for l in sent if l.endswith(ENVELOPE)]
        if len(env) != 1 or len(want_env) != 1:
            fails.append(f"{src}: envelope line: found {len(env)} events")
        else:
            want_type = "gen0sec:synapse:access" if source.kind == "hec_event" else "gen0sec:synapse"
            if env[0]["sourcetype"] != want_type:
                fails.append(f"{src}: envelope line: sourcetype {env[0]['sourcetype']}, want {want_type}")
            if env[0]["raw"] != want_env[0]:
                fails.append(f"{src}: envelope line: _raw is not the line as sent: {env[0]['raw'][:80]!r}")
            if src in HEADERED and tuple(time.gmtime(float(env[0]["t"]))[1:6]) != HEADER_TIME:
                fails.append(f"{src}: envelope line: _time is not the header's")
        if src in HEADERED:
            app_host = [r.get("host") for r in app]
            if app_host != [HEADER_HOST]:
                fails.append(f"{src}: app log line host {app_host}, want {HEADER_HOST!r}")
        if src in HOSTLESS:
            fails += check_hostless(src, rows)
        for _, marker, host in KEEP.get(src, []):
            found = [r for r in rows if marker in r.get("raw", "")]
            if len(found) != 1:
                fails.append(f"{src}: {marker}: found {len(found)} events")
            elif found[0].get("host") != host:
                fails.append(f"{src}: {marker}: host {found[0].get('host')!r}, want {host!r}")
        for rec in RECORDS:
            rid = rec["request_id"]
            if rec is SD_RECORD and src not in SD_SOURCES:
                continue
            match = [r for r in rows if key_of(r.get("raw", "")) == rid]
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
            if r["raw"] != BODY[rid]:
                fails.append(f"{where}: _raw is not the record as sent: {r['raw'][:80]!r}")
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
