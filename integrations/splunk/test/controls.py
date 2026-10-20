"""Controls for the add-on test: each is a broken copy of the TA, made by one
regex substitution in one file. A control is killed when the stream checks
report a problem that contains `must_fail_substring`; if the checks stay quiet
or fail only elsewhere, the control survived and the test has a gap.

`pattern` must match exactly once (MULTILINE), or applying the control is an
error, so a control cannot pass because the add-on moved on from it.
"""
import os
import re
import shutil
import sys
from collections import namedtuple

Control = namedtuple("Control", "name path pattern replacement must_fail_substring")

PROPS = "default/props.conf"
TRANSFORMS = "default/transforms.conf"

CONTROLS = [
    Control("header strip removed from TRANSFORMS-g0s", PROPS,
            r", gen0sec_synapse_strip_header$", "",
            "_raw is not pure JSON"),
    Control("access sourcetype regex broken", TRANSFORMS,
            r'(\[gen0sec_synapse_access_sourcetype\]\nREGEX = \\\{"event_type":"http_access_log)"',
            r'\1_x"',
            "sourcetype gen0sec:synapse"),
    Control("record-time transform removed from TRANSFORMS-g0s", PROPS,
            r"(gen0sec_synapse_host), gen0sec_synapse_time,", r"\1,",
            ": _time "),
    Control("EVAL-action removed", PROPS,
            r"^EVAL-action = .*\n", "",
            "action=None, want"),
    Control("host transform removed from TRANSFORMS-g0s", PROPS,
            r"^(TRANSFORMS-g0s = )gen0sec_synapse_host, ", r"\1",
            ": host "),
    Control("challenge dropped from the action rule", PROPS,
            r"\(block\|challenge\|ratelimit\)", "(block|ratelimit)",
            "action='allowed', want 'blocked'"),
    Control("TIME_* removed from [gen0sec:synapse:access]", PROPS,
            r"^TIME_PREFIX = .*\nTIME_FORMAT = .*\n", "",
            "hec-event"),
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
