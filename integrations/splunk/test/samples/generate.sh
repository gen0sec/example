#!/usr/bin/env bash
# Regenerates the real Synapse output under samples/<stream>/.
#
# It runs the Synapse container three times, with different log formats, and
# sends it traffic from a second container. It pulls the image if it is not
# there, so it MAY need access to registry.gen0sec.com. It needs docker, openssl and
# python3. Synapse gets NET_RAW (and memlock) for packet capture. No other
# capability and no host network are used.
#
#   SYNAPSE_IMAGE   image to run (default registry.gen0sec.com/gen0sec/synapse:0.8.8)
#
# Run a: events text, app text, CEF over UDP (RFC 5424), full traffic
# Run b: events json, app json, CEF over TCP (octet counting)
# Run c: events cef, CEF over UDP (RFC 3164)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
IMAGE=${SYNAPSE_IMAGE:-registry.gen0sec.com/gen0sec/synapse:0.8.8}
USE=$HERE/../../../../use-cases
# RAW_DIR keeps the raw output of the three runs (for example to re-run
# gen/collect.py on it). It MUST be empty or absent.
if [ -n "${RAW_DIR:-}" ]; then mkdir -p "$RAW_DIR"; W=$(cd "$RAW_DIR" && pwd); else W=$(mktemp -d); fi
P=g0s-samples-$$
CLEAN=("$P-a-d" "$P-a-s" "$P-b-d" "$P-b-s" "$P-c-d" "$P-c-s" "$P-client")
trap 'docker rm -fv "${CLEAN[@]}" >/dev/null 2>&1 || true; [ -n "${RAW_DIR:-}" ] || rm -rf "$W"' EXIT

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"

mkdir -p "$W/etc/certs" "$W/etc/rules"
cp "$USE/reverse-proxy-waf/security_rules.yaml" "$W/etc/"
cp "$HERE/gen/host-ids.rules" "$W/etc/rules/"
sed 's|upstream: whoami:80|upstream: 127.0.0.1:9000|' "$USE/reverse-proxy-waf/upstreams.yaml" >"$W/etc/upstreams.yaml"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=app.example.com" \
  -addext "subjectAltName=DNS:app.example.com" \
  -keyout "$W/etc/certs/app.example.com.key" -out "$W/etc/certs/app.example.com.crt" 2>/dev/null
chmod a+r "$W/etc/certs/"*

run() { # run <id> <events_format> <cef_transport> <cef_port> <cef_rfc> <app_log_format>
  local id=$1 d=$P-$1-d s=$P-$1-s
  mkdir -p "$W/$id/sock" "$W/$id/s" "$W/$id/d"
  sed -e "s/@EVENTS_FORMAT@/$2/" -e "s/@CEF_TRANSPORT@/$3/" -e "s/@CEF_PORT@/$4/" -e "s/@CEF_RFC@/$5/" \
    "$HERE/gen/config.yaml.in" >"$W/etc/config.yaml"
  chmod -R a+rwX "$W/$id/sock"
  # d owns the network namespace and the hostname; s joins it.
  docker run -d --name "$d" --hostname synapse-host \
    -v "$HERE/gen/sink.py:/sink.py:ro" -v "$W/$id/sock:/sock" \
    python:3-slim python -u /sink.py >/dev/null
  for _ in $(seq 100); do [ -S "$W/$id/sock/log" ] && break; sleep 0.2; done
  [ -S "$W/$id/sock/log" ] || { echo "sink did not start" >&2; docker logs "$d" >&2; exit 1; }
  local env=()
  [ "$6" = json ] && env=(-e SYNAPSE_LOG_FORMAT=json)
  docker create --name "$s" --network "container:$d" \
    --cap-add NET_RAW --ulimit memlock=-1:-1 "${env[@]}" \
    -v "$W/etc:/etc/synapse:ro" \
    -v "$W/$id/sock/log:/dev/log" \
    "$IMAGE" -c /etc/synapse/config.yaml --security-rules-config /etc/synapse/security_rules.yaml >/dev/null
  docker start "$s" >/dev/null
  local ip
  ip=$(docker inspect -f '{{.NetworkSettings.Networks.bridge.IPAddress}}' "$d")
  for _ in $(seq 100); do
    docker exec "$d" python -c "import socket;socket.create_connection(('127.0.0.1',8080),2)" 2>/dev/null && break
    sleep 0.5
  done
  docker exec "$d" python -c "import socket;socket.create_connection(('127.0.0.1',8080),2)" ||
    { echo "proxy did not accept on 8080" >&2; docker logs "$s" >&2; exit 1; }
  docker run -d --name "$P-client" -e TARGET="$ip" -v "$HERE/gen/drive.py:/drive.py:ro" \
    python:3-slim python -u /drive.py >/dev/null
  local cip
  cip=$(docker inspect -f '{{.NetworkSettings.Networks.bridge.IPAddress}}' "$P-client")
  local rc
  rc=$(docker wait "$P-client")
  docker logs "$P-client" 2>&1 | sed 's/^/  client: /' | tee "$W/$id/client.log"
  [ "$rc" = 0 ] || { echo "client exited $rc" >&2; exit 1; }
  ! grep -q '^  client: ERR' "$W/$id/client.log" || { echo "client had errors" >&2; exit 1; }
  printf '{"synapse":"%s","client":"%s"}\n' "$ip" "$cip" >"$W/$id/ips.json"
  sleep 2
  docker cp "$s:/var/log/synapse/." "$W/$id/s/"
  docker cp "$d:/out/." "$W/$id/d/"
  docker rm -fv "$s" "$d" "$P-client" >/dev/null
}

run a text udp 5514 rfc5424 text
run b json tcp 5515 rfc5424 json
run c cef udp 5514 rfc3164 text

python3 "$HERE/gen/collect.py" "$W" "$HERE"
