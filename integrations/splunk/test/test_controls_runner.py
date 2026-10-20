"""Unit tests for run_controls() in test_splunk.py, against a fake Splunk.

The fake models three places a setting lives: the installed add-on files, the
config splunkd has loaded (set by a restart or a reload), and the config the
events were indexed with (set when samples are sent). Index-time settings
(the TRANSFORMS line) show in the events only through the indexed copy;
search-time ones (the EVAL line) through the loaded copy.

Run from integrations/splunk/:  python3 -m unittest discover -s test -p 'test_controls_runner.py'
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import controls  # noqa: E402
import test_splunk as runner  # noqa: E402

PROPS = ("[gen0sec:synapse:access]\n"
         "TRANSFORMS-g0s = a, b\n"
         "EVAL-action = case(x)\n"
         "KV_MODE = json\n")


class FakeSplunk:
    def __init__(self):
        self.installed = {}
        self.loaded = {}
        self.indexed = {}
        self.restarts = 0
        self.reloads = 0
        self.sends = 0
        self.ignore_reload_from = None

    def read(self, d):
        with open(os.path.join(d, "default", "props.conf")) as f:
            return f.read()

    def install_ta(self, d):
        self.installed = self.read(d)

    def restart(self):
        self.restarts += 1
        self.loaded = self.installed

    def reload_conf(self):
        self.reloads += 1
        if self.ignore_reload_from is None or self.reloads < self.ignore_reload_from:
            self.loaded = self.installed

    def send(self, streams, data, tag=None):
        self.sends += 1
        self.indexed = self.loaded

    def check(self, rows):
        out = []
        if "TRANSFORMS-g0s = a, b" not in self.indexed:
            out.append("tcp:5514 k: index-time thing missing")
        if "EVAL-action = case(x)" not in self.loaded:
            out.append("tcp:5514 k: search-time thing missing")
        return out


def control(name, pattern, replacement, must_fail, kind):
    return controls.Control(name, controls.PROPS, pattern, replacement, re.compile(must_fail), kind)


SEARCH_BREAK = control("eval removed", r"^EVAL-action = .*\n", "", "search-time thing", "search")
INDEX_BREAK = control("transform removed", r"^TRANSFORMS-g0s = a, b\n", "", "index-time thing", "index")
SEARCH_NOOP = control("no-op edit", r"^(KV_MODE = json)$", r"\1", "never matches", "search")


class RunControls(unittest.TestCase):
    def setUp(self):
        self.ta = tempfile.mkdtemp(prefix="g0s-ta-")
        os.makedirs(os.path.join(self.ta, "default"))
        with open(os.path.join(self.ta, "default", "props.conf"), "w") as f:
            f.write(PROPS)
        self.fake = FakeSplunk()
        mod = types.SimpleNamespace(check=self.fake.check)
        self.streams = {"fake": mod}
        self.saved = (runner.h, runner.TA_DIR, runner.send, runner.collect, controls.CONTROLS)
        runner.h = types.SimpleNamespace(install_ta=self.fake.install_ta, restart=self.fake.restart,
                                         reload_conf=self.fake.reload_conf)
        runner.TA_DIR = self.ta
        runner.send = self.fake.send
        runner.collect = lambda streams, since=None, tag=None, **kw: {}
        self.fake.install_ta(self.ta)

    def tearDown(self):
        runner.h, runner.TA_DIR, runner.send, runner.collect, controls.CONTROLS = self.saved
        shutil.rmtree(self.ta, ignore_errors=True)

    def run_with(self, ctls):
        controls.CONTROLS = ctls
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = runner.run_controls(self.streams, "unused")
        return rc, out.getvalue()

    def test_search_control_neither_restarts_nor_resends(self):
        rc, out = self.run_with([SEARCH_BREAK])
        self.assertEqual(rc, 0, out)
        self.assertIn("killed eval removed", out)
        self.assertEqual((self.fake.restarts, self.fake.sends), (1, 1), "only the baseline restarts and sends")

    def test_index_control_still_restarts_and_resends(self):
        rc, out = self.run_with([INDEX_BREAK])
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.fake.restarts, self.fake.sends), (2, 2))

    def test_both_kinds_are_killed(self):
        rc, out = self.run_with([INDEX_BREAK, SEARCH_BREAK])
        self.assertEqual(rc, 0, out)
        self.assertEqual((self.fake.restarts, self.fake.sends), (2, 2))

    def test_surviving_search_control_exits_1(self):
        rc, out = self.run_with([SEARCH_NOOP])
        self.assertEqual(rc, 1, out)
        self.assertIn("survived no-op edit", out)
        self.assertEqual(self.fake.restarts, 1)

    def test_next_control_does_not_see_the_previous_broken_config(self):
        # SEARCH_NOOP follows SEARCH_BREAK and must not inherit its fault: if it
        # did, its must_fail would match and it would be wrongly killed.
        noop = control("no-op edit", r"^(KV_MODE = json)$", r"\1", "search-time thing", "search")
        rc, out = self.run_with([SEARCH_BREAK, noop])
        self.assertEqual(rc, 1, out)
        self.assertIn("killed eval removed", out)
        self.assertIn("survived no-op edit", out)

    def test_search_controls_run_before_index_controls(self):
        # An index control leaves its broken add-on installed; a search control
        # after it would start from that.
        rc, out = self.run_with([INDEX_BREAK, SEARCH_BREAK])
        self.assertLess(out.index("killed eval removed"), out.index("killed transform removed"))

    def test_failed_restore_is_an_error(self):
        self.fake.ignore_reload_from = 2  # the reload that restores is ignored
        rc, out = self.run_with([SEARCH_BREAK])
        self.assertEqual(rc, 1, out)
        self.assertIn("restoring the add-on did not clear", out)

    def test_search_kind_on_an_index_time_edit_is_refused(self):
        bad = control("transform marked search", r"^TRANSFORMS-g0s = a, b\n", "", "index-time thing", "search")
        with self.assertRaises(SystemExit) as cm:
            self.run_with([bad])
        self.assertIn("not a search-time edit", str(cm.exception))

    def test_search_kind_with_an_index_time_replacement_is_refused(self):
        bad = control("adds a transform", r"^(KV_MODE = json)$", r"\1\nTRANSFORMS-x = y", "x", "search")
        with self.assertRaises(SystemExit):
            self.run_with([bad])

    def test_unknown_kind_is_refused(self):
        bad = control("typo", r"^KV_MODE = json$", "", "x", "serach")
        with self.assertRaises(SystemExit):
            self.run_with([bad])


if __name__ == "__main__":
    unittest.main()
