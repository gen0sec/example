# Cap the TCP MSS of a listener

`tcp_mss` on a listener caps the MSS of the connections it accepts, for a path
whose MTU is smaller than the client assumes. **Needs Synapse 0.8.9 or later.**

Things to know:

- A TC stage of the BPF firewall rewrites the MSS option of the client's SYN on
  ingress and of Synapse's SYN-ACK on egress. It needs Linux, BPF privileges and
  `firewall.mode` `auto` or `xdp`. With `none`, `nftables`, `iptables`, a build without BPF
  or the confined Kubernetes proxy, the key loads and does nothing; Synapse logs an
  `error` line per listener, `tcp_mss: ... is NOT enforced`.
- It only lowers: a client that offers a smaller MSS keeps it. The range is 88 to 32767.
- A wildcard listener also clamps connections the host forwards to that port.
- A reload applies a changed `tcp_mss` on a listener that is already bound. A
  new or moved listener needs a restart.
- Counters: `synapse_bpf_tcp_mss_clamped_total{direction}` and
  `synapse_bpf_tcp_mss_skipped_total`.

## Run

The container is privileged and pins BPF maps in a bpffs. It uses the host's
`/sys/fs/bpf` by default, which an agent on the same host shares. Set `BPFFS` to
a directory with a bpffs of its own to keep them apart.

```sh
docker compose up -d
docker compose logs synapse | grep tcp_mss      # tcp_mss: listener "http" ... clamps MSS to 1360
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' tcp-mss-synapse-1)
sudo tcpdump -nn -i any "host $IP and port 8080 and tcp[tcpflags] & tcp-syn != 0" &
curl -s -o /dev/null -H 'Host: app.example.com' http://$IP:8080/    # the SYN-ACK shows mss 1360
docker compose down
```

Set `SYNAPSE_IMAGE` to use your own image.
