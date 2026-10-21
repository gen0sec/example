"""Runs inside the sender container. Reads a JSON list of
{"mode": "unix"|"udp", "data": "<text>"} from stdin and sends each item the
way Synapse does: one datagram per message, no newline, no NUL, to /dev/log
or to UDP 127.0.0.1:514. Prints a JSON list: "ok" or the error of each send."""
import json
import socket
import sys
import time

out = []
for item in json.load(sys.stdin):
    data = item["data"].encode()
    try:
        if item["mode"] == "unix":
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.connect("/dev/log")
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("127.0.0.1", 514))
        s.send(data)
        s.close()
        out.append("ok")
    except OSError as e:
        out.append("%s: %s" % (type(e).__name__, e))
    time.sleep(0.05)
print(json.dumps(out))
