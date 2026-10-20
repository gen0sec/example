"""End-to-end test of TA-gen0sec-synapse in a real Splunk 9.0.1.

Starts splunk/splunk:9.0.1 in docker with the add-on installed, sends every
stream's sample data in every way the README describes, then checks what
Splunk made of each event. One container serves all streams: it boots once,
everything is sent, the results are collected once and each stream checks its
own.

Each stream is a module in test/streams/ (see streams/access.py) exporting:
  SOURCES  dict of Splunk `source` to harness.Source(kind, sourcetype, lines).
           Files are named /test-data/<stream>/<file>; the network sources are
           tcp:5514, tcp:5515, udp:5516 and any name for HEC.
  FIELDS   the search-time fields the check reads
  key_of(line)  the id that ties an event to its sample
  check(rows)   rows maps each source to its Splunk rows; returns problems

The container, the inputs and the sending live in test/splunk_harness.py.
The inputs.conf has a monitor per stream data directory, with the sourcetype
that stream's file sources declare, and tcp 5514, tcp 5515 and udp 5516, with
sourcetype gen0sec:synapse.

Needs docker. Usage, from integrations/splunk/:  python3 test/test_splunk.py
Environment:
  TA_DIR        the add-on to install (default: ./TA-gen0sec-synapse)
  SPLUNK_IMAGE  default: splunk/splunk:9.0.1
  STREAMS       comma-separated stream names to run (default: all)
  KEEP=1        leave the container running after the test
  SPLUNK_TEST_NAME       container name (default: g0s-splunk-ta-test)
  SPLUNK_TEST_PORT_BASE  host port base (default: 15000); the ports are
                         base+514, +515, +516 (tcp 5514, 5515, udp 5516),
                         base+3088 (HEC) and base+3089 (management). A
                         second run beside this one needs a base that shares
                         none of them: step by 1000.

  --controls    instead of one run, boot once and run every control in
                test/controls.py. A control of kind "index" is installed over
                the real add-on, splunkd restarts, the samples are sent again
                and only events indexed after the restart are checked. A
                control of kind "search" is installed, the config is
                reloaded, and the baseline's events are searched again; the
                add-on is then restored and those events must pass again.
                Prints killed or survived per control; exit 1 if any
                survived. `make test-splunk-controls` runs it.
Exit status: 0 when every check passes (every control killed), 1 otherwise.
"""
import importlib
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import controls  # noqa: E402
import splunk_harness as h  # noqa: E402

TA_DIR = os.path.abspath(os.environ.get("TA_DIR", os.path.join(HERE, "..", "TA-gen0sec-synapse")))
NETWORK = {"tcp:5514": "tcp3164", "tcp:5515": "tcp5424", "udp:5516": "udp"}


def load_streams():
    names = sorted(f[:-3] for f in os.listdir(os.path.join(HERE, "streams"))
                   if f.endswith(".py") and not f.startswith("_"))
    want = [s.strip() for s in os.environ.get("STREAMS", "").split(",") if s.strip()]
    unknown = [s for s in want if s not in names]
    if unknown:
        sys.exit(f"error: unknown stream(s) {unknown}; have {names}")
    streams = {n: importlib.import_module(f"streams.{n}") for n in names if not want or n in want}
    # A source name two streams share would count (and look up) each other's events.
    owner = {}
    for name, mod in streams.items():
        for src in mod.SOURCES:
            if src in owner:
                sys.exit(f"error: source {src!r} is declared by both {owner[src]} and {name}")
            owner[src] = name
    return streams


def actual_source(src, kind, tag):
    """The Splunk source of `src`. A tag puts a file in its own subdirectory,
    so a monitor reads it even though its content was seen before."""
    if tag and kind == "file":
        d, f = os.path.split(src)
        return os.path.join(d, tag, f)
    return src


def send(streams, data_dir, tag=None):
    for mod in streams.values():
        for src, s in mod.SOURCES.items():
            if s.kind == "file":
                h.write_monitor_file(data_dir, actual_source(src, s.kind, tag), s.lines)
            elif s.kind == "tcp":
                h.send_tcp(h.PORTS[NETWORK[src]], s.lines)
            elif s.kind == "udp":
                h.send_udp(h.PORTS[NETWORK[src]], s.lines)
            elif s.kind == "hec_raw":
                h.send_hec_raw(src, s.sourcetype, s.lines)
            elif s.kind == "hec_event":
                h.send_hec_event(src, s.sourcetype, s.lines)
            else:
                sys.exit(f"error: {src}: unknown kind {s.kind!r}")


def collect(streams, deadline_s=180, since=None, tag=None, until=None):
    """Rows per source. With `since`, only events indexed at or after that
    epoch second; with `until`, at or before it. `tag` is the one given to
    send()."""
    want = {src: len(s.lines) for mod in streams.values() for src, s in mod.SOURCES.items()}
    where = {actual_source(src, s.kind, tag): src
             for mod in streams.values() for src, s in mod.SOURCES.items()}
    fields = sorted({f for mod in streams.values() for f in mod.FIELDS})
    base = ("search index=main" + (f" _indextime>={int(since)}" if since else "")
            + (f" _indextime<={int(until) + 1}" if until else ""))
    query = ("%s source IN (%s) | eval raw=_raw, t=_time | table source sourcetype host t raw request_id %s"
             % (base, ",".join(f'"{s}"' for s in where), " ".join(fields)))
    end = time.time() + deadline_s
    while True:
        rows = h.search(query)
        got = {}
        for r in rows:
            # An events.log record has a "source" key of its own, which Splunk
            # adds to the source metadata as a second value.
            src = r["source"]
            if isinstance(src, list):
                src = next(v for v in src if v in where)
            got.setdefault(where[src], []).append(r)
        if all(len(got.get(s, [])) >= n for s, n in want.items()) or time.time() > end:
            return got
        time.sleep(5)


def write_inputs(streams, work):
    inputs = os.path.join(work, "g0s_test_inputs", "default")
    os.makedirs(inputs)
    conf = ""
    for name, mod in streams.items():
        # The stanza's sourcetype is the one the stream's file sources declare.
        types = {s.sourcetype for s in mod.SOURCES.values() if s.kind == "file"}
        if len(types) > 1:
            sys.exit(f"error: stream {name}: its files declare several sourcetypes {sorted(types)}; "
                     "one monitor reads the whole directory")
        if not types:
            continue
        conf += (f"[monitor:///test-data/{name}]\nindex = main\nsourcetype = {types.pop()}\n"
                 "crcSalt = <SOURCE>\n\n")
    for port, extra in (("tcp://5514", "connection_host = none\n"),
                        ("tcp://5515", "connection_host = none\n"),
                        ("udp://5516", "connection_host = none\n")):
        conf += f"[{port}]\nindex = main\nsourcetype = gen0sec:synapse\n{extra}\n"
    with open(os.path.join(inputs, "inputs.conf"), "w") as f:
        f.write(conf.rstrip("\n") + "\n")
    return os.path.dirname(inputs)


def check_all(streams, got):
    fails = []
    for mod in streams.values():
        fails += mod.check(got)
    return fails


def run_controls(streams, data):
    """Baseline first: the unbroken add-on must pass through the same path,
    or a failing check would not mean the control was caught.

    An "index" control restarts splunkd and sends the samples again. A
    "search" control only reloads the config and searches the baseline's
    events again, within the window in which they were indexed, so events a
    later send adds do not count. Search controls still run first: an index
    control leaves its broken add-on installed, and a search control
    would start from it. After each, the add-on is put back and the baseline
    events must pass again, which shows the reload took the repair and that
    the next control starts clean."""
    work = tempfile.mkdtemp(prefix="g0s-controls-")
    results = []
    t_all = time.time()
    try:
        good = os.path.join(work, "ta-good")
        controls.make_copy(None, TA_DIR, good)
        ordered = sorted(controls.CONTROLS, key=lambda c: c.kind != "search")
        for c in ordered:
            controls.check_kind(c, TA_DIR)
        runs = [("baseline", None)] + [(c.name, c) for c in ordered]
        for i, (name, c) in enumerate(runs):
            t_ctl = time.time()
            if c is not None and c.kind == "search":
                broken = os.path.join(work, f"ta{i}")
                controls.make_copy(c, TA_DIR, broken)
                h.install_ta(broken)
                h.reload_conf()
                fails = check_all(streams, collect(streams, since=base[0], tag=base[1], until=base[2]))
                h.install_ta(good)
                h.reload_conf()
                left = check_all(streams, collect(streams, since=base[0], tag=base[1], until=base[2]))
                if left:
                    print(f"FAIL: restoring the add-on did not clear {name!r}'s problems from the baseline events:")
                    for f in left[:5]:
                        print("  " + f)
                    return 1
            else:
                if c is not None:
                    broken = os.path.join(work, f"ta{i}")
                    controls.make_copy(c, TA_DIR, broken)
                    h.install_ta(broken)
                h.restart()
                t0 = time.time() - 2
                tag = f"c{i}"
                send(streams, data, tag)
                fails = check_all(streams, collect(streams, since=t0, tag=tag))
                if c is None:
                    base = (t0, tag, time.time())
            dt = time.time() - t_ctl
            if c is None:
                if fails:
                    print("FAIL: the unbroken add-on fails its own checks:")
                    for f in fails:
                        print("  " + f)
                    return 1
                print(f"baseline ok ({dt:.0f}s)", flush=True)
                continue
            hit = [f for f in fails if c.must_fail.search(f)]
            how = "reload" if c.kind == "search" else "restart"
            if hit:
                print(f"killed {name} ({len(fails)} problems, {how}, {dt:.0f}s)", flush=True)
            else:
                extra = f"; {len(fails)} problems, none matching {c.must_fail.pattern!r}" if fails else ""
                print(f"survived {name}{extra} ({how}, {dt:.0f}s)", flush=True)
                for f in fails[:5]:
                    print("  " + f)
            results.append((name, bool(hit)))
        # Put the real add-on back, so KEEP=1 leaves a container that is not broken.
        h.install_ta(good)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    survived = [n for n, k in results if not k]
    print(f"{len(results) - len(survived)} of {len(results)} controls killed, total {time.time() - t_all:.0f}s")
    return 1 if survived else 0


def main():
    controls_mode = "--controls" in sys.argv[1:]
    if not os.path.isdir(TA_DIR):
        sys.exit(f"error: add-on not found at {TA_DIR}")
    streams = load_streams()
    work = tempfile.mkdtemp(prefix="g0s-splunk-")
    data = os.path.join(work, "test-data")
    for name in streams:
        os.makedirs(os.path.join(data, name))
    inputs_app = write_inputs(streams, work)
    os.chmod(work, 0o755)
    for root, dirs, files in os.walk(work):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)

    try:
        h.create(data)
        installed_ta = os.path.join(work, "ta")
        controls.make_copy(None, TA_DIR, installed_ta)
        h.install(installed_ta, inputs_app)
        h.start()
        print(f"waiting for {h.IMAGE} ...", flush=True)
        h.wait_ready()
        if controls_mode:
            return run_controls(streams, data)
        send(streams, data)
        got = collect(streams)
        fails = []
        for mod in streams.values():
            fails += mod.check(got)
    finally:
        if os.environ.get("KEEP") != "1":
            h.remove()
            shutil.rmtree(work, ignore_errors=True)
    total = sum(len(s.lines) for mod in streams.values() for s in mod.SOURCES.values())
    paths = sum(len(mod.SOURCES) for mod in streams.values())
    if fails:
        print(f"FAIL: {len(fails)} problem(s) across {total} events")
        for f in fails:
            print("  " + f)
        return 1
    print(f"PASS: {total} events over {paths} ingest paths, all fields as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
