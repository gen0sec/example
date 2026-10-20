"""The events.log stream: Synapse's block events in the text and JSON formats,
read by a monitor input with the sourcetype gen0sec:synapse:events.

Files (under samples/events/):
  events.text.log, events.json.log     what Synapse 0.8.8 wrote
  events.edited.text.log,
  events.edited.json.log               edge cases Synapse did not write in the
                                       sample run, each a real line with one
                                       edit (see samples/README.md)
  events.cef.log                       CEF lines, which a later change parses.
                                       Here they only have to stay as they are.

Each line's expected sourcetype, _time (to the second, UTC), fields, CIM fields,
eventtype and tag are written out below by hand, in the order of the file.
"""
import os

from splunk_harness import Source

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples", "events")
SOURCETYPE = "gen0sec:synapse:events"


def read(name):
    with open(os.path.join(SAMPLES, name)) as f:
        return f.read().splitlines()


FILES = {
    "events.text.log": read("events.text.log"),
    "events.json.log": read("events.json.log"),
    "events.edited.text.log": read("events.edited.text.log"),
    "events.edited.json.log": read("events.edited.json.log"),
    "events.cef.log": read("events.cef.log"),
}
SOURCES = {f"/test-data/events/{n}": Source("file", SOURCETYPE, lines) for n, lines in FILES.items()}

# _time of each line, as epoch seconds (UTC), in file order.
T_TEXT = 1792519885   # 2026-10-20T18:11:25Z
T_JSON_48 = 1792519908  # 2026-10-20T18:11:48Z
T_JSON_49 = 1792519909  # 2026-10-20T18:11:49Z

IDS_TAGS = {"ids", "attack"}
NET_TAGS = {"network", "communicate"}
ET_IDS = {"gen0sec_synapse_events", "gen0sec_synapse_events_ids"}
ET_NET = {"gen0sec_synapse_events", "gen0sec_synapse_events_network"}
HOST = "=host"  # dvc must equal the event's host
VENDOR = {"vendor": "Gen0Sec", "product": "Synapse", "vendor_product": "Gen0Sec Synapse", "dvc": HOST}

# Intrusion_Detection, by layer and action.
WAF_BLOCK = {"layer": "waf", "synapse_action": "block", "action": "blocked", "severity": "high",
             "ids_type": "application", "category": "waf", "eventtype": ET_IDS, "tag": IDS_TAGS, **VENDOR}
WAF_RATELIMIT = {**WAF_BLOCK, "synapse_action": "ratelimit", "severity": "medium"}
IDS_NOTICE = {"layer": "ids", "synapse_action": "notice", "action": "allowed", "severity": "low",
              "ids_type": "network", "category": "ids", "eventtype": ET_IDS, "tag": IDS_TAGS, **VENDOR}
# Severity follows the action: block and drop high, captcha and ratelimit medium, the rest low.
WAF_CAPTCHA = {**WAF_BLOCK, "synapse_action": "captcha", "severity": "medium"}
THREAT_INTEL = {**WAF_BLOCK, "synapse_source": "threat_intel"}
IDS_BLOCK = {**IDS_NOTICE, "synapse_action": "block", "action": "blocked", "severity": "high"}
IDS_DROP = {**IDS_BLOCK, "synapse_action": "drop"}
# Network_Traffic: none of the intrusion fields.
NO_IDS = {"signature": None, "signature_id": None, "category": None, "severity": None, "ids_type": None}
RATE_LIMIT = {"layer": "rate_limit", "synapse_action": "ratelimit", "action": "blocked",
              "eventtype": ET_NET, "tag": NET_TAGS, **NO_IDS, **VENDOR}
SMART_FIREWALL = {"layer": "smart_firewall", "synapse_action": "drop", "action": "blocked",
                  "eventtype": ET_NET, "tag": NET_TAGS, **NO_IDS, **VENDOR}
ACCESS_RULES = {"layer": "access_rules", "synapse_action": "block", "action": "blocked",
                "eventtype": ET_NET, "tag": NET_TAGS, **NO_IDS, **VENDOR}
FLEET_BAN = {**ACCESS_RULES, "synapse_action": "drop", "synapse_source": "fleet_ban", "ban_secs": "600",
             "src": "203.0.113.9", "src_ip": "203.0.113.9", "src_port": None, "dest": None, "dst_ip": None,
             "rule_id": None, "rule": None}
SMART_LOG = {**SMART_FIREWALL, "synapse_action": "log", "action": "allowed", "synapse_source": "traffic_classifier",
             "src_country": "NL", "src_asn": "64500", "src_asn_org": "Example Hosting, B.V.",
             "sni": "evil.example.com", "traffic_class": "c2", "traffic_confidence": "87"}
# A client-set string (a quoted msg, an `eve.http` User-Agent) that looks like
# fields. None of it may reach src, rule or the sids.
INJECTED = {"src": "198.51.100.20", "src_ip": "198.51.100.20", "rule_id": "waf-block-admin", "ids_sids": None}

ADDRS = {"src": "198.51.100.20", "src_ip": "198.51.100.20", "dest": "192.0.2.10", "dst_ip": "192.0.2.10"}
TO_8443 = {**ADDRS, "dest_port": "8443", "dst_port": "8443"}


def rule(rule_id, msg):
    return {"rule_id": rule_id, "rule_msg": msg, "signature": msg, "signature_id": rule_id}


def net_rule(rule_id, msg):
    return {"rule_id": rule_id, "rule_msg": msg, "rule": rule_id}


ADMIN = rule("waf-block-admin", "Block /admin (response=403)")
SQLI = rule("waf-block-sqli", "Block basic SQL injection (response=403)")
XSS = rule("waf-block-xss", "Block basic XSS (response=403)")
LOGIN = rule("waf-ratelimit-login", "Rate limit /login (response=429)")
HTTP_TEST = rule("sid:1000002", "GEN0SEC example: HTTP request to /ids-test")
ICMP_TEST = rule("sid:1000001", "GEN0SEC example: ICMP echo with test payload")
TS_TEXT = {"ts": "2026-10-20T18:11:25Z"}
TS_48 = {"ts": "2026-10-20T18:11:48Z"}
TS_49 = {"ts": "2026-10-20T18:11:49Z"}


def text(port, trace, span):
    return {"src_port": port, "trace_id": trace, "span_id": span, "synapse_source": "waf"}


def js(port, trace, span):
    return {"src_port": port, "trace.trace_id": trace, "trace.span_id": span, "trace.trace_flags": "01",
            "trace_id": trace, "span_id": span, "synapse_source": "waf", "source": "waf"}


# (_time, expected) per line of each file, in file order.
EXPECTED = {
    "events.text.log": [
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **ADMIN, **text("52256", "057df7833696284bfdffe9ca6284bfd2", "49e8ebf3dc2f4c06")}),
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **SQLI, **text("52262", "529e68adf7f40e52e03f7dba97031d4b", "3b0be6f4ef31e150")}),
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **XSS, **text("52270", "db46c50e7ba25e003f05de020da505b1", "837d743aa5c5c4e5")}),
        (T_TEXT, {**TS_TEXT, **WAF_RATELIMIT, **TO_8443, **LOGIN, **text("52310", "468192110bfc623aec714a047d95a1cf", "e7144e172c193ce0")}),
        (T_TEXT, {**TS_TEXT, **WAF_RATELIMIT, **TO_8443, **LOGIN, **text("52314", "19eb8d2e63e031bca014d3364f05fb60", "c3050503f6c4750b")}),
        (T_TEXT, {**TS_TEXT, **IDS_NOTICE, **ADDRS, "dest_port": "8080", "dst_port": "8080", **HTTP_TEST, "src_port": "55900"}),
        (T_TEXT, {**TS_TEXT, **IDS_NOTICE, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST, "src_port": "0"}),
    ],
    "events.json.log": [
        (T_JSON_48, {**TS_48, **WAF_BLOCK, **TO_8443, **ADMIN, **js("52300", "23ead64f40e7ac23a4b2255dec543905", "b9a305d5c3809706")}),
        (T_JSON_48, {**TS_48, **WAF_BLOCK, **TO_8443, **SQLI, **js("52304", "b9aae5063fb0d201d47666c324134b4c", "4bea9405503350e9")}),
        (T_JSON_48, {**TS_48, **WAF_BLOCK, **TO_8443, **XSS, **js("52308", "a8f7adb9d42e8cc023ea1dde804e9a00", "8966c80cb59f20f1")}),
        (T_JSON_49, {**TS_49, **WAF_RATELIMIT, **TO_8443, **LOGIN, **js("52334", "77e5c248c2ba4eb65a092b52c7de9856", "b895e1f8b93b0b1d")}),
        (T_JSON_49, {**TS_49, **WAF_RATELIMIT, **TO_8443, **LOGIN, **js("52350", "74e980eec1be82849bbe152d391842d7", "cffb4b5c4f6cc4e3")}),
        (T_JSON_49, {**TS_49, **IDS_NOTICE, **ADDRS, "dest_port": "8080", "dst_port": "8080", **HTTP_TEST,
                     "src_port": "33222", "eve.alert.signature_id": "1000002", "eve.event_type": "alert",
                     "eve.fingerprints.ja4l": "1_64"}),
        (T_JSON_49, {**TS_49, **IDS_NOTICE, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST,
                     "src_port": "0", "eve.alert.signature_id": "1000001", "eve.proto": "ICMP"}),
    ],
    "events.edited.text.log": [
        # msg with \", =, spaces and \u{2028}, kept as written
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **text("52256", "057df7833696284bfdffe9ca6284bfd2", "49e8ebf3dc2f4c06"),
                  **rule("waf-block-admin", r"Block \"a=b\" admin\u{2028}x (response=403)")}),
        # IPv6 src kept whole: no src_ip or src_port
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **ADMIN, **text(None, "057df7833696284bfdffe9ca6284bfd2", "49e8ebf3dc2f4c06"),
                  "src": "2001:db8::1:443", "src_ip": None}),
        (T_TEXT, {**TS_TEXT, **RATE_LIMIT, **TO_8443, **net_rule("waf-ratelimit-login", "Rate limit /login (response=429)"),
                  **text("52310", "468192110bfc623aec714a047d95a1cf", "e7144e172c193ce0")}),
        (T_TEXT, {**TS_TEXT, **SMART_FIREWALL, **TO_8443, **net_rule("waf-block-sqli", "Block basic SQL injection (response=403)"),
                  **text("52262", "529e68adf7f40e52e03f7dba97031d4b", "3b0be6f4ef31e150")}),
        (T_TEXT, {**TS_TEXT, **WAF_CAPTCHA, **TO_8443, **XSS, **text("52270", "db46c50e7ba25e003f05de020da505b1", "837d743aa5c5c4e5")}),
        (T_TEXT, {**TS_TEXT, **ACCESS_RULES, **TO_8443, **net_rule("waf-block-sqli", "Block basic SQL injection (response=403)"),
                  **text("52262", "529e68adf7f40e52e03f7dba97031d4b", "3b0be6f4ef31e150")}),
        (T_TEXT, {**TS_TEXT, **THREAT_INTEL, **TO_8443, **LOGIN, **text("52314", "19eb8d2e63e031bca014d3364f05fb60", "c3050503f6c4750b"),
                  "synapse_source": "threat_intel"}),
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **ADMIN, **text("52256", "057df7833696284bfdffe9ca6284bfd2", "49e8ebf3dc2f4c06"),
                  "ban_secs": "600"}),
        (T_TEXT, {**TS_TEXT, **IDS_NOTICE, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST, "src_port": "0",
                  "ids_sids": {"1", "2"}}),
        (T_TEXT, {**TS_TEXT, **IDS_BLOCK, **ADDRS, "dest_port": "8080", "dst_port": "8080", **HTTP_TEST, "src_port": "55900",
                  "ids_sids": {"1000002"}}),
        (T_TEXT, {**TS_TEXT, **IDS_DROP, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST, "src_port": "0"}),
        # no port on src, no dst: src_ip is still set
        (T_TEXT, {**TS_TEXT, **FLEET_BAN}),
        # no rule: rule and rule_id stay empty
        (T_TEXT, {**TS_TEXT, **ACCESS_RULES, **TO_8443, "rule_id": None, "rule": None, "rule_msg": None,
                  "src_port": "52262", "synapse_source": "access_rules"}),
        # a quoted rule id
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **text("52256", "057df7833696284bfdffe9ca6284bfd2", "49e8ebf3dc2f4c06"),
                  **rule("Block admin", "Block /admin (response=403)")}),
        (T_TEXT, {**TS_TEXT, **SMART_LOG, **TO_8443, **net_rule("c2-sni", "C2 SNI seen"), "src_port": "52304"}),
        (T_TEXT, {**TS_TEXT, **WAF_BLOCK, **TO_8443, **ADMIN, "src_port": "52256", "synapse_source": "waf",
                  "rule_msg": "Block /admin src=203.0.113.66:1 rule=evil ids_sids=999 (response=403)",
                  "signature": "Block /admin src=203.0.113.66:1 rule=evil ids_sids=999 (response=403)", **INJECTED}),
    ],
    "events.edited.json.log": [
        # only ts, layer and action
        (T_JSON_48, {**TS_48, **WAF_BLOCK, "src": None, "src_ip": None, "dest": None, "dst_ip": None,
                     "rule_id": None, "rule_msg": None, "signature": None, "signature_id": None}),
        (T_JSON_49, {**TS_49, **RATE_LIMIT, **TO_8443, **net_rule("waf-ratelimit-login", "Rate limit /login (response=429)"),
                     **js("52334", "77e5c248c2ba4eb65a092b52c7de9856", "b895e1f8b93b0b1d")}),
        (T_JSON_48, {**TS_48, **SMART_FIREWALL, **TO_8443, **net_rule("waf-block-sqli", "Block basic SQL injection (response=403)"),
                     **js("52304", "b9aae5063fb0d201d47666c324134b4c", "4bea9405503350e9")}),
        (T_JSON_48, {**TS_48, **WAF_CAPTCHA, **TO_8443, **XSS, **js("52308", "a8f7adb9d42e8cc023ea1dde804e9a00", "8966c80cb59f20f1")}),
        (T_JSON_49, {**TS_49, **WAF_RATELIMIT, **TO_8443, **LOGIN, **js("52350", "74e980eec1be82849bbe152d391842d7", "cffb4b5c4f6cc4e3"),
                     "ban_secs": "600"}),
        (T_JSON_49, {**TS_49, **IDS_NOTICE, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST, "src_port": "0",
                     "ids_sids": {"1", "2"}}),
        (T_JSON_48, {**TS_48, **THREAT_INTEL, **TO_8443, **XSS, "src_port": "52308"}),
        # the User-Agent holds ` src=... rule=... ids_sids=...`
        (T_JSON_49, {**TS_49, **IDS_BLOCK, **ADDRS, "dest_port": "8080", "dst_port": "8080", **HTTP_TEST, "src_port": "33222",
                     "ids_sids": {"1000002"}, "rule_id": "sid:1000002", "eve.http.http_user_agent":
                     "curl/8 src=203.0.113.66:1 rule=evil ids_sids=999"}),
        (T_JSON_49, {**TS_49, **IDS_DROP, **ADDRS, "dest_port": "0", "dst_port": "0", **ICMP_TEST, "src_port": "0",
                     "ids_sids": {"1"}}),
        (T_JSON_49, {**TS_49, **FLEET_BAN}),
        (T_JSON_49, {**TS_49, **ACCESS_RULES, **TO_8443, "rule_id": None, "rule": None, "rule_msg": None,
                     "src_port": "52262", "synapse_source": "access_rules", "source": "access_rules"}),
        (T_JSON_48, {**TS_48, **SMART_LOG, **TO_8443, **net_rule("c2-sni", "C2 SNI seen"), "src_port": "52304",
                     "source": "traffic_classifier"}),
    ],
}
# A CEF line stays in this sourcetype, byte for byte. The CIM fields are for
# events with a layer, so none appear. Its _time is not checked.
CEF_NONE = {"layer": None, "action": None, "signature": None, "severity": None, "tag": None, "vendor_product": None}

FIELDS = sorted({f for rows in EXPECTED.values() for _, w in rows for f in w if f != "source"}
                | set(CEF_NONE) | {"eventtype"})


def key_of(line):
    """A line is its own key: the event whose _raw is this line."""
    return line


def check(got):
    """`got` maps each source to its rows. Returns the problems found."""
    fails = []
    for name, lines in FILES.items():
        src = f"/test-data/events/{name}"
        rows = got.get(src, [])
        if len(rows) != len(lines):
            fails.append(f"{src}: {len(rows)} events, sent {len(lines)}")
        wants = EXPECTED.get(name)
        if wants is not None and len(wants) != len(lines):
            fails.append(f"{src}: {len(wants)} expectations for {len(lines)} lines")
            continue
        for i, line in enumerate(lines):
            where = f"{src} line {i + 1}"
            match = [r for r in rows if r.get("raw") == line]
            if len(match) != 1:
                fails.append(f"{where}: found {len(match)} events with this _raw")
                continue
            r = match[0]
            if r["sourcetype"] != SOURCETYPE:
                fails.append(f"{where}: sourcetype {r['sourcetype']}")
            if wants is None:
                for f, want in CEF_NONE.items():
                    if r.get(f) != want:
                        fails.append(f"{where}: {f}={r.get(f)!r}, want {want!r}")
                continue
            t, want = wants[i]
            if float(r["t"]) != t:
                fails.append(f"{where}: _time {r['t']}, want {t}")
            for field, w in want.items():
                have = r.get(field)
                if field == "source" and isinstance(have, list):
                    have = next((v for v in have if not v.startswith("/")), None)
                if w == HOST:
                    w = r.get("host")
                if isinstance(w, set):
                    have = set(have) if isinstance(have, list) else ({have} if have else set())
                if have != w:
                    fails.append(f"{where}: {field}={have!r}, want {w!r}")
    return fails
