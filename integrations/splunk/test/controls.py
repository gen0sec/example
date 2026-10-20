"""Controls for the add-on test: each is a broken copy of the TA, made by one
regex substitution in one file. A control is killed when the stream checks
report a problem that `must_fail` matches. It names the source and the
field, so a problem another control causes does not count; if the checks stay quiet
or fail only elsewhere, the control survived and the test has a gap.

`pattern` must match exactly once (MULTILINE), or applying the control is an
error, so a control cannot pass because the add-on moved on from it.

`kind` says how Splunk takes the change up:
  "index"   (the default) a restart, then the samples are sent again: the
            setting acts when an event is indexed (TRANSFORMS, SEDCMD,
            INGEST_EVAL, TIME_*, LINE_BREAKER, and the transforms.conf stanzas
            they use).
  "search"  a config reload, then the baseline's events are searched again:
            the setting acts when a search reads them (EVAL-, FIELDALIAS-,
            EXTRACT-, REPORT-, LOOKUP-, KV_MODE in props.conf; eventtypes.conf,
            tags.conf). Declaring it is not enough: check_kind() refuses a
            "search" control that changes any other line, so a control cannot
            be run the cheap way and survive for the wrong reason.
"""
import difflib
import os
import re
import shutil
import sys
from collections import namedtuple

Control = namedtuple("Control", "name path pattern replacement must_fail kind", defaults=("index",))
KINDS = ("index", "search")

SEARCH_TIME_FILES = ("default/eventtypes.conf", "default/tags.conf")
SEARCH_TIME_SETTING = re.compile(r"(EVAL-|FIELDALIAS-|EXTRACT-|REPORT-|LOOKUP-|KV_MODE\b)")
PROPS = "default/props.conf"
TRANSFORMS = "default/transforms.conf"
EVENTTYPES = "default/eventtypes.conf"
TAGS = "default/tags.conf"

# The access pattern as it was before values could be objects, with the guard.
OLD_ROUTE = (r'^.{0,256}?(?<!":)(?<!": )\{\s*(?:"(?!event_type")[^"]*"\s*:\s*(?:"[^"]*"|null|true|false|-?\d+(?:\.\d+)?)\s*,\s*)*'
             r'"event_type"\s*:\s*"http_access_log"')
# The same, as the body of an eval string.
OLD_EVAL_BODY = (r'(?<!\":)(?<!\": )[{]\s*(?:\"(?!event_type\")[^\"]*\"\s*:\s*(?:\"[^\"]*\"|null|true|false|-?[0-9]+(?:[.][0-9]+)?)\s*,\s*)*'
                 r'\"event_type\"\s*:\s*\"http_access_log\"')

CONTROLS = [
    Control("header strip removed from TRANSFORMS-g0s", PROPS,
            r", gen0sec_synapse_strip_header, (gen0sec_synapse_time)$", r", \1",
            re.compile(r"^tcp:5514 \S+: _raw is not pure JSON")),
    Control("access sourcetype regex broken", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = .*http_access_log)"',
            r'\1_x"',
            re.compile(r"^tcp:5514 \S+: sourcetype gen0sec:synapse$")),
    Control("record-time transform removed from TRANSFORMS-g0s", PROPS,
            r", gen0sec_synapse_time$", "",
            re.compile(r"^tcp:5514 \S+: _time ")),
    Control("EVAL-action removed", PROPS,
            r"^EVAL-action = case\(isnull\('response.*\n", "",
            re.compile(r"^tcp:5514 \S+: action=None, want "), "search"),
    Control("host transforms removed from TRANSFORMS-g0s", PROPS,
            r"^(TRANSFORMS-g0s = )gen0sec_synapse_host_5424, gen0sec_synapse_host_bsd, ", r"\1",
            re.compile(r"^tcp:5514 \S+: host '\S*', want 'synapse-host'")),
    Control("5424 host transform removed from TRANSFORMS-g0s", PROPS,
            r"^(TRANSFORMS-g0s = )gen0sec_synapse_host_5424, ", r"\1",
            re.compile(r"^tcp:5515 \S+: host '\S*', want 'synapse-host'")),
    Control("BSD/ISO host regex takes any token (the old regex)", TRANSFORMS,
            r"(\[gen0sec_synapse_host_bsd\]\nREGEX = ).*\n",
            r"\1^(?:(?:<\\d{1,3}>)?[A-Z][a-z]{2} [ \\d]\\d \\d\\d:\\d\\d:\\d\\d |\\d{4}-\\d\\d-\\d\\dT\\S+ )([^\\s\\-{][^\\s{]*)\\s\n",
            re.compile(r"^tcp:5514: g0s-hostless-iso: host 'WARN', want the input's")),
    Control("BSD/ISO host regex without the IPv6 branch", TRANSFORMS,
            r"\(\(\?:\[0-9A-Fa-f\]\{0,4\}:\)\{2,\}\[0-9A-Fa-f\.:\]\*\|", "(",
            re.compile(r"^tcp:5514: g0s-keep-ipv6-bsd: host ")),
    Control("5424 host regex excludes : from the host", TRANSFORMS,
            r"\(\?!-\\s\)\(\\S\+\)", r"([^\\s\\-\\[:][^\\s\\[:]*)",
            re.compile(r"^tcp:5515: g0s-keep-ipv6-5424: host ")),
    Control("challenge dropped from the action rule", PROPS,
            r"\(block\|challenge\|ratelimit\)", "(block|ratelimit)",
            re.compile(r"^tcp:5514 req_1792506501500000002: action='allowed', want 'blocked'"), "search"),
    Control("time transform removed from [gen0sec:synapse:access]", PROPS,
            r"^TRANSFORMS-g0s-time = .*\n", "",
            re.compile(r"^hec-event \S+: _time ")),
    Control("TIME_PREFIX added to [gen0sec:synapse]", PROPS,
            r"(\[gen0sec:synapse\]\n)", r'\1TIME_PREFIX = "timestamp":"\n',
            re.compile(r"^tcp:5514: app log line _time ")),
    Control("access sourcetype regex widened to the app line", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = ).*\n',
            r'\1(?:event_type":"http_access_log"|Failed to load)\n',
            re.compile(r"^tcp:5514: app log line: .*want one gen0sec:synapse")),
    Control("access route reverted to the literal prefix", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = ).*\n",
            r'\1\\{"event_type":"http_access_log"\n',
            re.compile(r"^tcp:5514 \S+-sorted-compact: sourcetype gen0sec:synapse$")),
    Control("access route allows no whitespace", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = ).*\n",
            r'\1^.{0,256}?\\{(?:"[^"]*":(?:"[^"]*"|null|true|false|-?\\d+(?:\\.\\d+)?),)*"event_type":"http_access_log"\n',
            re.compile(r"^tcp:5514 \S+-spaced: sourcetype gen0sec:synapse$")),
    Control("access route header may not contain a brace", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = \^)\.\{0,256\}\?",
            r"\1[^{]*",
            re.compile(r"^tcp:5515 \S+-sd: sourcetype gen0sec:synapse$")),
    Control("header strip reverted to the literal prefix", TRANSFORMS,
            r"^(INGEST_EVAL = _raw=replace\(_raw, ).*\n",
            r'\1"^[^{]*([{]\\"event_type\\":\\"http_access_log\\")", "\\1")\n',
            re.compile(r"^tcp:5514 \S+-sorted-compact: _raw is not pure JSON")),
    Control("header strip stops at a brace in the header", TRANSFORMS,
            r'(INGEST_EVAL = _raw=replace\(_raw, "\^)\.\{0,256\}\?',
            r"\1[^{]*",
            re.compile(r"^tcp:5515 \S+-sd: _raw is not pure JSON")),
    Control("record-time route reverted to the literal prefix", TRANSFORMS,
            r'^(INGEST_EVAL = _time=if\()match\(_raw, "[^\n]*?"\), (coalesce)',
            r'\1match(_raw, "[{]\\"event_type\\":\\"http_access_log\\""), \2',
            re.compile(r"^tcp:5514 \S+-sorted-compact: _time ")),
    Control("access sourcetype takes its time from a TIME_PREFIX again", PROPS,
            r"^TRANSFORMS-g0s-time = .*$",
            'TIME_PREFIX = "timestamp"\\\\s*:\\\\s*"\nTIME_FORMAT = %Y-%m-%dT%H:%M:%S.%9N\nMAX_TIMESTAMP_LOOKAHEAD = 32\nTZ = UTC',
            re.compile(r"^hec-event \S+-hdr-sorted-compact: _time ")),
    Control("access route values are not possessive", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = )(.*)\n",
            lambda m: m.group(1) + m.group(2).replace("++", "+").replace("*+", "*") + "\n",
            re.compile(r"^tcp:5514 \S+-err-esc-sorted-compact: sourcetype gen0sec:synapse$")),
    Control("access route sees only the default LOOKAHEAD", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = [^\n]*\n)LOOKAHEAD = 16384\n",
            r"\1",
            re.compile(r"^tcp:5514 \S+-err-esc-sorted-compact: sourcetype gen0sec:synapse$")),
    Control("record time is the first timestamp in the record", TRANSFORMS,
            r'json_extract\(_raw, "timestamp"\)',
            r'replace(_raw, "^.*?\\"timestamp\\"\\s*:\\s*\\"([^\\"]+)\\".*$", "\\1")',
            re.compile(r"^tcp:5514 \S+-hdr-sorted-compact: _time ")),
    Control("access route values are scalars only", TRANSFORMS,
            r"(\[gen0sec_synapse_access_sourcetype\]\nREGEX = ).*\n",
            lambda m: m.group(1) + OLD_ROUTE + "\n",
            re.compile(r"^tcp:5514 \S+-err-sorted-compact: sourcetype gen0sec:synapse$")),
    Control("header strip values are scalars only", TRANSFORMS,
            r"(\[gen0sec_synapse_strip_header\]\nINGEST_EVAL = ).*\n",
            lambda m: m.group(1) + '_raw=replace(_raw, "^.{0,256}?(?=' + OLD_EVAL_BODY + ')", "")\n',
            re.compile(r"^tcp:5514 \S+-err-sorted-compact: _raw is not pure JSON")),
    Control("access route has no guard against an enclosing object", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = \^\.\{0,256\}\?)\(\?<!":\)\(\?<!": \)',
            r"\1",
            re.compile(r"^tcp:5514: envelope line: sourcetype gen0sec:synapse:access")),
    Control("header strip has no guard against an enclosing object", TRANSFORMS,
            r'(INGEST_EVAL = _raw=replace\(_raw, "\^\.\{0,256\}\?\(\?=)\(\?<!\\":\)\(\?<!\\": \)',
            r"\1",
            re.compile(r"^tcp:5514: envelope line: _raw is not the line as sent")),
    Control("events: line breaking broken", PROPS,
            r"(\[gen0sec:synapse:events\]\nSHOULD_LINEMERGE = false\nLINE_BREAKER = \(\[\\r\\n\]\+\))\n", r"\1ZZZ\n",
            re.compile(r"^/test-data/events/events\.text\.log: 1 events, sent 7$")),
    Control("events: TIME_PREFIX no longer skips {\"ts\":\"", PROPS,
            r'^TIME_PREFIX = \^\(\?:\\\{"ts":"\)\?$', "TIME_PREFIX = ^",
            re.compile(r"^/test-data/events/events\.json\.log line 1: _time ")),
    Control("events: MAX_TIMESTAMP_LOOKAHEAD too short for ts", PROPS,
            r"^MAX_TIMESTAMP_LOOKAHEAD = 20$", "MAX_TIMESTAMP_LOOKAHEAD = 5",
            re.compile(r"^/test-data/events/events\.text\.log line 1: _time ")),
    Control("events: KV_MODE auto removed", PROPS,
            r"^KV_MODE = auto\n", "KV_MODE = none\n",
            re.compile(r"^/test-data/events/events\.json\.log line 6: eve\.alert\.signature_id=None")),
    Control("events: layer capture renamed", PROPS,
            r"\(\?<layer>\[\^/", r"(?<layerx>[^/",
            re.compile(r"^/test-data/events/events\.text\.log line 1: layer=None, want 'waf'")),
    Control("events: src_port capture renamed", PROPS,
            r"\(\?<src_port>", "(?<src_portx>",
            re.compile(r"^/test-data/events/events\.text\.log line 1: src_port=None, want '52256'")),
    Control("events: IPv6 address split at the last colon", PROPS,
            r"\\d\{1,3\}\(\?:\\\.\\d\{1,3\}\)\{3\}\):\(\?<src_port>", r"\\S+):(?<src_port>",
            re.compile(r"^/test-data/events/events\.edited\.text\.log line 2: src_ip='2001:db8::1', want None")),
    Control("events: msg escape not skipped", PROPS,
            r"\(\?:\[\^\"\\\\\]\|\\\\\.\)\*", r"[^\"]*",
            re.compile(r"^/test-data/events/events\.edited\.text\.log line 1: rule_msg=")),
    Control("events: ids_sids extraction removed", PROPS,
            r"^EXTRACT-g0s_events_sids = .*\n", "",
            re.compile(r"^/test-data/events/events\.edited\.text\.log line 9: ids_sids='1', want '1,2'")),
    Control("events: EVAL-src takes the port along", PROPS,
            r"EVAL-src = coalesce\(src_ip, src\)", "EVAL-src = src",
            re.compile(r"^/test-data/events/events\.text\.log line 1: src='198\.51\.100\.20:52256', want '198\.51\.100\.20'")),
    Control("events: captcha not a blocked action", PROPS,
            r'\^\(block\|ratelimit\|captcha\|drop\)\$', "^(block|ratelimit|drop)$",
            re.compile(r"^/test-data/events/events\.edited\.text\.log line 5: action='allowed', want 'blocked'")),
    Control("events: EVAL-category removed", PROPS,
            r"^EVAL-category = .*\n", "",
            re.compile(r"^/test-data/events/events\.text\.log line 1: category=None, want 'waf'")),
    Control("events: EVAL-rule removed", PROPS,
            r"^EVAL-rule = .*\n", "",
            re.compile(r"^/test-data/events/events\.edited\.json\.log line 2: rule=None, want 'waf-ratelimit-login'")),
    Control("events: ids eventtype loses waf", EVENTTYPES,
            r"layer=waf OR ", "layer=wafx OR ",
            re.compile(r"^/test-data/events/events\.text\.log line 1: eventtype=\{'gen0sec_synapse_events'\}, want ")),
    Control("events: network eventtype loses rate_limit", EVENTTYPES,
            r"layer=rate_limit\)", "layer=rate_limitx)",
            re.compile(r"^/test-data/events/events\.edited\.text\.log line 3: eventtype=\{'gen0sec_synapse_events'\}, want ")),
    Control("events: ids tag removed", TAGS,
            r"^ids = enabled\n", "",
            re.compile(r"^/test-data/events/events\.text\.log line 1: tag=\{'attack'\}, want ")),
]


def apply(control, ta_dir):
    """Edit `ta_dir` in place. Exits with an error unless the pattern matches
    exactly once."""
    path = os.path.join(ta_dir, control.path)
    with open(path) as f:
        text = f.read()
    new, n = re.subn(control.pattern, control.replacement, text, flags=re.MULTILINE)
    if n != 1:
        sys.exit(f"error: control {control.name!r}: pattern matched {n} times in {control.path}, want 1")
    with open(path, "w") as f:
        f.write(new)


def _edited(control, ta_dir):
    """The file's lines before and after the control, as (old, new)."""
    path = os.path.join(ta_dir, control.path)
    with open(path) as f:
        text = f.read()
    return text.splitlines(), re.sub(control.pattern, control.replacement, text, flags=re.MULTILINE).splitlines()


def check_kind(control, ta_dir):
    """Exit with an error unless `control.kind` is known and, for "search", the
    control changes only search-time lines. Anything else is "index"."""
    if control.kind not in KINDS:
        sys.exit(f"error: control {control.name!r}: kind {control.kind!r}, want one of {KINDS}")
    if control.kind == "index":
        return
    if control.path in SEARCH_TIME_FILES:
        return
    if control.path == PROPS:
        old, new = _edited(control, ta_dir)
        changed = [l[2:] for l in difflib.ndiff(old, new) if l[:2] in ("- ", "+ ")]
        if all(not l.strip() or SEARCH_TIME_SETTING.match(l) for l in changed):
            return
    sys.exit(f"error: control {control.name!r} is kind 'search' but is not a search-time edit of {control.path}")


def make_copy(control, ta_dir, dest):
    """A fresh copy of `ta_dir` at `dest` with `control` applied (none: the
    add-on as it is), world-readable so splunkd can read it. Install this, not
    `ta_dir`: docker cp keeps the checkout's modes and owner, and a checkout
    made under umask 077 is unreadable to the splunk user."""
    shutil.copytree(ta_dir, dest)
    if control is not None:
        apply(control, dest)
    for root, dirs, files in os.walk(dest):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)
    os.chmod(dest, 0o755)
