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
HEADERED = {"/test-data/access/syslog-3164.log", "tcp:5514", "tcp:5515", "hec-raw"}

SOURCES = {
    "/test-data/access/syslog-3164.log": Source("file", "gen0sec:synapse", lines(header_3164_file)),
    "/test-data/access/plain.jsonl": Source("file", "gen0sec:synapse", lines(None)),
    "tcp:5514": Source("tcp", "gen0sec:synapse", lines(header_3164)),
    "tcp:5515": Source("tcp", "gen0sec:synapse", lines(header_5424)),
    "hec-raw": Source("hec_raw", "gen0sec:synapse", lines(header_hec_raw)),
    "hec-event": Source("hec_event", "gen0sec:synapse:access", lines(None)),
}


def key_of(line):
    """The request_id in an event's text, or None for a line that has none
    (the application log line)."""
    m = re.search(r'"request_id":"([^"]*)"', line)
    return m.group(1) if m else None


def epoch(ts):
    whole, frac = ts.rstrip("Z").split(".")
    t = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return round(t + float("0." + frac), 6)


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
        for rec in RECORDS:
            rid = rec["request_id"]
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
