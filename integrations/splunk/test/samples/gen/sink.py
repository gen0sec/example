"""Runs next to Synapse in one network namespace. It stands in for what
Synapse talks to and writes down exactly what arrives:
  /sock/log      the syslog datagram socket (Synapse opens /dev/log)
  udp 127.0.0.1:5514, tcp 127.0.0.1:5515   the CEF syslog output
  tcp 127.0.0.1:9000                       the upstream the proxy forwards to
"""
import http.server
import os
import socket
import socketserver
import threading

os.makedirs("/out", exist_ok=True)


def dgram(sock, path):
    while True:
        data = sock.recv(65535)
        with open(path, "ab") as f:
            f.write(data if data.endswith(b"\n") else data + b"\n")


s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind("/sock/log")
os.chmod("/sock/log", 0o666)
threading.Thread(target=dgram, args=(s, "/out/syslog.raw"), daemon=True).start()

u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
u.bind(("127.0.0.1", 5514))
threading.Thread(target=dgram, args=(u, "/out/cef-udp.raw"), daemon=True).start()

t = socket.socket()
t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
t.bind(("127.0.0.1", 5515))
t.listen(5)


def tcp_conn(c):
    while True:
        data = c.recv(65535)
        if not data:
            break
        with open("/out/cef-tcp.raw", "ab") as f:
            f.write(data)


def tcp_accept():
    while True:
        c, _ = t.accept()
        threading.Thread(target=tcp_conn, args=(c,), daemon=True).start()


threading.Thread(target=tcp_accept, daemon=True).start()


class Upstream(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok\n")

    do_POST = do_HEAD = do_GET  # the proxy health-checks with HEAD

    def log_message(self, *args):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer(("127.0.0.1", 9000), Upstream).serve_forever()
