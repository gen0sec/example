#!/bin/sh
# Check flow.lua on live captured traffic. Exit 1 if any check fails.
#   sudo SYNAPSE_BIN=/path/to/synapse ./test.sh
#
# Needs root, ip (iproute2) and python3. Everything runs in two network
# namespaces made for the run and joined by a veth pair: the agent captures
# on its end with AF_PACKET and `firewall.mode: none`, so the host's
# interfaces and firewall are not touched. The namespaces are removed on exit.
# The agent runs this set's `snippet:` block as it is, with test/threat.mmdb
# as its threat database (203.0.113.0/24 scored 90).
set -u
cd "$(dirname "$0")" || exit 2
here=$(pwd)
bin=${SYNAPSE_BIN:-synapse}
bin=$(command -v "$bin") || { echo "error: synapse binary not found; set SYNAPSE_BIN" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "error: run as root (AF_PACKET capture and network namespaces)" >&2; exit 2; }
for t in ip python3; do command -v $t >/dev/null || { echo "error: $t is required" >&2; exit 2; }; done

id=$$
cli=axf-cli-$id srv=axf-srv-$id vc=axfc$id vs=axfs$id
work=$(mktemp -d) || exit 2
apid='' lpid=''
cleanup() {
  for p in "$apid" "$lpid"; do
    if [ -n "$p" ] && [ "$p" -gt 1 ] && kill -0 "$p" 2>/dev/null; then kill -TERM "$p"; fi
  done
  sleep 1
  for p in "$apid" "$lpid"; do
    if [ -n "$p" ] && [ "$p" -gt 1 ] && kill -0 "$p" 2>/dev/null; then kill -KILL "$p"; fi
  done
  ip netns del "$cli" 2>/dev/null
  ip netns del "$srv" 2>/dev/null
  rm -rf -- "${work:?}"
}
trap cleanup EXIT INT TERM

# --- two namespaces: the client has a public and a private address
ip netns add "$cli" && ip netns add "$srv" && ip link add "$vc" type veth peer name "$vs" || exit 2
ip link set "$vc" netns "$cli" && ip link set "$vs" netns "$srv" || exit 2
ip -n "$cli" addr add 203.0.113.5/24 dev "$vc"
ip -n "$cli" addr add 10.0.0.5/24 dev "$vc"
ip -n "$srv" addr add 198.51.100.1/24 dev "$vs"
for n in "$cli" "$srv"; do ip -n "$n" link set lo up; done
ip -n "$cli" link set "$vc" up
ip -n "$srv" link set "$vs" up
ip -n "$cli" route add 198.51.100.0/24 dev "$vc"
ip -n "$srv" route add 203.0.113.0/24 dev "$vs"
ip -n "$srv" route add 10.0.0.0/24 dev "$vs"

# --- listeners on 22, 443 and 8080 that accept and close
ip netns exec "$srv" python3 -I -c '
import socket, threading
def serve(port):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("198.51.100.1", port)); s.listen(64)
    while True:
        c, _ = s.accept(); c.close()
for p in (22, 443, 8080):
    threading.Thread(target=serve, args=(p,), daemon=True).start()
threading.Event().wait()' &
lpid=$!

# --- the agent: this set's snippet block, captured on the veth
cp flow.lua test/threat.mmdb "$work"/
chmod 644 "$work/flow.lua"
{
  cat <<EOF
mode: agent
multi_thread: false
network: { iface: "$vs", ip_version: ipv4 }
firewall: { mode: none }
capture: { enabled: true, mode: af_packet, interface: "$vs" }
daemon: { enabled: false, event_socket: "$work/event.sock", control_socket: "$work/control.sock" }
logging: { level: info, file_logging_enabled: true, log_directory: "$work/logs", events_log_format: json }
platform:
  api_key: test-key
  base_url: "http://127.0.0.1:9"
  threat: { enabled: true, path: "$work/threat.mmdb" }
EOF
  sed -n '/^snippet:/,$p' "$here/config.yaml"
} > "$work/config.yaml"
(cd "$work" && exec ip netns exec "$srv" "$bin" -c config.yaml --firewall-mode none >"$work/agent.out" 2>&1) &
apid=$!

logs() { cat "$work/agent.out" "$work"/logs/*.log 2>/dev/null; }
i=0
until logs | grep -q "AF_PACKET capture thread running on '$vs'"; do
  i=$((i + 1))
  [ $i -le 60 ] || { echo "FAIL the capture did not start"; logs | tail -20; exit 1; }
  sleep 1
done

connect() {
  ip netns exec "$cli" python3 -I -c "
import socket
for _ in range(5):
    s = socket.socket(); s.bind(('$1', 0)); s.settimeout(2)
    try: s.connect(('198.51.100.1', $2))
    except OSError: pass
    s.close()"
}
n=0
while [ $n -lt 10 ]; do
  connect 203.0.113.5 22; connect 10.0.0.5 22; connect 203.0.113.5 443; connect 203.0.113.5 8080
  sleep 1; n=$((n + 1))
done
sleep 2

fail=0
ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
has() { logs | grep -q "rule 'axon:$1' matched src $2 .*LOG only"; }

logs | grep -q "generation 1 loaded" && ok "the snippet loaded" || bad "the snippet did not load"
has ssh-from-public 203.0.113.5 && ok "SSH from a public address is tagged ssh-from-public" || bad "no ssh-from-public tag for 203.0.113.5"
has ssh-from-public 10.0.0.5 && bad "SSH from a private address was tagged" || ok "SSH from a private address is not tagged"
has tls-to-risky 203.0.113.5 && ok "443 from an address scored 90 is tagged tls-to-risky (filters:)" || bad "no tls-to-risky tag for 203.0.113.5"
logs | grep "rule 'axon:" | grep -qv "LOG only" && bad "a tag was not log only" || ok "every tag is log only"
logs | grep -q "axon\[flow\]" && bad "the snippet logged an error" || ok "no snippet error"

exit $fail
