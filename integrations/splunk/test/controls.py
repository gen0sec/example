"""Controls for the add-on test: each is a broken copy of the TA, made by one
regex substitution in one file. A control is killed when the stream checks
report a problem that `must_fail` matches. It names the source and the
field, so a problem another control causes does not count; if the checks stay quiet
or fail only elsewhere, the control survived and the test has a gap.

`pattern` must match exactly once (MULTILINE), or applying the control is an
error, so a control cannot pass because the add-on moved on from it.
"""
import os
import re
import shutil
import sys
from collections import namedtuple

Control = namedtuple("Control", "name path pattern replacement must_fail")

PROPS = "default/props.conf"
TRANSFORMS = "default/transforms.conf"

CONTROLS = [
    Control("header strip removed from TRANSFORMS-g0s", PROPS,
            r", gen0sec_synapse_strip_header$", "",
            re.compile(r"^tcp:5514 \S+: _raw is not pure JSON")),
    Control("access sourcetype regex broken", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = \\\{"event_type":"http_access_log)"',
            r'\1_x"',
            re.compile(r"^tcp:5514 \S+: sourcetype gen0sec:synapse$")),
    Control("record-time transform removed from TRANSFORMS-g0s", PROPS,
            r"(gen0sec_synapse_host), gen0sec_synapse_time,", r"\1,",
            re.compile(r"^tcp:5514 \S+: _time ")),
    Control("EVAL-action removed", PROPS,
            r"^EVAL-action = .*\n", "",
            re.compile(r"^tcp:5514 \S+: action=None, want ")),
    Control("host transform removed from TRANSFORMS-g0s", PROPS,
            r"^(TRANSFORMS-g0s = )gen0sec_synapse_host, ", r"\1",
            re.compile(r"^tcp:5514 \S+: host '\S*', want 'synapse-host'")),
    Control("challenge dropped from the action rule", PROPS,
            r"\(block\|challenge\|ratelimit\)", "(block|ratelimit)",
            re.compile(r"^tcp:5514 req_1792506501500000002: action='allowed', want 'blocked'")),
    Control("TIME_* removed from [gen0sec:synapse:access]", PROPS,
            r"^TIME_PREFIX = .*\nTIME_FORMAT = .*\n", "",
            re.compile(r"^hec-event \S+: _time ")),
    Control("TIME_PREFIX added to [gen0sec:synapse]", PROPS,
            r"(\[gen0sec:synapse\]\n)", r'\1TIME_PREFIX = "timestamp":"\n',
            re.compile(r"^tcp:5514: app log line _time ")),
    Control("access sourcetype regex widened to the app line", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = )\\\{"event_type":"http_access_log"',
            r'\1(?:event_type":"http_access_log"|Failed to load)',
            re.compile(r"^tcp:5514: app log line: .*want one gen0sec:synapse")),
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


def make_copy(control, ta_dir, dest):
    """A fresh broken copy of `ta_dir` at `dest`, world-readable so splunkd can read it."""
    shutil.copytree(ta_dir, dest)
    apply(control, dest)
    for root, dirs, files in os.walk(dest):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)
    os.chmod(dest, 0o755)
