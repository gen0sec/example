"""Sends the traffic from a second container, so it reaches Synapse over eth0
and the capture sees it. Requests are written as bytes, so a path or header
that holds UTF-8 goes out as UTF-8."""
import os
import socket
import ssl
import struct
import sys
import time

TARGET = os.environ["TARGET"]
HOST = "app.example.com"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def send(path, ua="curl/8.5.0", method="GET", body=b"", tls=True):
    req = (
        f"{method} ".encode() + path.encode("utf-8") + b" HTTP/1.1\r\n"
        + f"Host: {HOST}\r\n".encode()
        + b"User-Agent: " + ua.encode("utf-8") + b"\r\n"
        + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
    )
    try:
        raw = socket.create_connection((TARGET, 8443 if tls else 8080), timeout=10)
        s = ctx.wrap_socket(raw, server_hostname=HOST) if tls else raw
        s.sendall(req)
        first = b""
        while b"\r\n" not in first:
            chunk = s.recv(4096)
            if not chunk:
                break
            first += chunk
        print(method, path, first.split(b"\r\n")[0].decode(errors="replace"))
        s.close()
    except OSError as e:
        print("ERR", path, e)
        sys.exit(1)


def icmp(payload):
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)

    def checksum(b):
        if len(b) % 2:
            b += b"\0"
        t = sum(struct.unpack("!%dH" % (len(b) // 2), b))
        t = (t >> 16) + (t & 0xFFFF)
        t += t >> 16
        return ~t & 0xFFFF

    head = struct.pack("!BBHHH", 8, 0, 0, 1, 1)
    s.sendto(struct.pack("!BBHHH", 8, 0, checksum(head + payload), 1, 1) + payload, (TARGET, 0))
    s.close()


send("/")
send("/search?q=synapse&page=2")
send("/café", ua="Ünïcode/1.0")
send("/admin")
send("/?q=1%3D1")
send("/?q=%3Cscript%3E")
for _ in range(5):
    send("/login")
send("/", tls=False)
send("/ids-test?x=1", tls=False)
icmp(b"gen0sec-test")
time.sleep(12)
