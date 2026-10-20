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
The inputs.conf has a monitor per stream data directory, and tcp 5514, tcp
5515 and udp 5516, all with sourcetype gen0sec:synapse.

Needs docker. Usage, from integrations/splunk/:  python3 test/test_splunk.py
Environment:
  TA_DIR        the add-on to install (default: ./TA-gen0sec-synapse)
  SPLUNK_IMAGE  default: splunk/splunk:9.0.1
  STREAMS       comma-separated stream names to run (default: all)
  KEEP=1        leave the container running after the test
  SPLUNK_TEST_NAME       container name (default: g0s-splunk-ta-test)
  SPLUNK_TEST_PORT_BASE  host port base (default: 15000); the ports are
                         base+514, +515, +516 (tcp 5514, 5515, udp 5516),
                         base+3088 (HEC) and base+3089 (management), so a
                         second run beside this one needs another base.
Exit status: 0 when every check passes, 1 otherwise.
"""
import importlib
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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
    return {n: importlib.import_module(f"streams.{n}") for n in names if not want or n in want}


def send(streams, data_dir):
    for mod in streams.values():
        for src, s in mod.SOURCES.items():
            if s.kind == "file":
                h.write_monitor_file(data_dir, src, s.lines)
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


def collect(streams, deadline_s=180):
    want = {src: len(s.lines) for mod in streams.values() for src, s in mod.SOURCES.items()}
    fields = sorted({f for mod in streams.values() for f in mod.FIELDS})
    query = ("search index=main source IN (%s) | eval raw=_raw, t=_time | table source sourcetype host t raw request_id %s"
             % (",".join(f'"{s}"' for s in want), " ".join(fields)))
    end = time.time() + deadline_s
    while True:
        rows = h.search(query)
        got = {}
        for r in rows:
            got.setdefault(r["source"], []).append(r)
        if all(len(got.get(s, [])) >= n for s, n in want.items()) or time.time() > end:
            return got
        time.sleep(5)


def write_inputs(streams, work):
    inputs = os.path.join(work, "g0s_test_inputs", "default")
    os.makedirs(inputs)
    conf = ""
    for name in streams:
        conf += f"[monitor:///test-data/{name}]\nindex = main\nsourcetype = gen0sec:synapse\n\n"
    for port, extra in (("tcp://5514", "connection_host = none\n"),
                        ("tcp://5515", "connection_host = none\n"),
                        ("udp://5516", "connection_host = none\n")):
        conf += f"[{port}]\nindex = main\nsourcetype = gen0sec:synapse\n{extra}\n"
    with open(os.path.join(inputs, "inputs.conf"), "w") as f:
        f.write(conf.rstrip("\n") + "\n")
    return os.path.dirname(inputs)


def main():
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
        h.install(TA_DIR, inputs_app)
        h.start()
        print(f"waiting for {h.IMAGE} ...", flush=True)
        h.wait_ready()
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
