# axon: a Lua snippet on every flow

Run a short Lua script on every flow the smart firewall evaluated, and tag the
flows you care about. Needs Synapse 0.8.10 or later, **built with the `axon`
cargo feature** (off by default) and with `amygdala-reactor` (in the standard
packages), on Linux. For the proxy-side phase, see [axon-access](../axon-access/).

`flow.lua` does two things:

| What | How | Result |
|---|---|---|
| Tag a flow to port 443 with a high threat score | the named expression `tls_to_risky`, asked for with `axon.filter("tls_to_risky")` | `axon:tls-to-risky` log-only entry |
| Tag SSH from a public address | `axon.ctx.dst_port == 22 and not axon.ip.is_private(axon.ctx.src_ip)` | `axon:ssh-from-public` log-only entry |

Things to know:

- The snippet sees the whole field set the smart firewall evaluates: packet
  facts, the JA4 family, TLS, DNS and HTTP fields, geography, threat, IDS and
  the smart firewall's own verdicts in `axon.ctx.matches`. A value the capture
  did not see reads as `nil`, never as zero.
- A tag is recorded as an `axon:<tag>` log entry next to the smart firewall's
  matches. A tag is printable ASCII, at most 64 bytes, without `,`, `"` or `\`.
- `allow_block` is off here. Set it to `true` and a snippet that returns
  `{ action = "block", tag = "x" }` makes a smart-firewall drop of the source
  address, through the same never-ban guards as a smart-firewall rule. It never
  overrides an explicit allow.
- `filters:` are compiled when the file loads. A bad expression rejects the
  file, and the snippet that was serving keeps serving; asking for a name that
  is not declared is a snippet error.
- Shared dictionaries (`snippet.shared_dicts`) are process-wide. The proxy and
  agent phases see the same dictionary only inside one process.
- The same safety rules as in [axon-access](../axon-access/) apply: a time
  limit per call, a circuit breaker, and a loader that refuses a file that is
  world-writable or owned by another user.

The privileges, kernel and interface settings are those of the
[smart-firewall](../smart-firewall/) set, which this config is based on.

## Test

`test.sh` runs this set's `snippet:` block on live captured traffic:

```sh
sudo SYNAPSE_BIN=/path/to/synapse ./test.sh   # "ok" or "FAIL" per check, exit 1 if any fails
```

It needs root, `ip` and `python3`, and a Synapse built with `axon`. It makes
two network namespaces joined by a veth pair, runs the agent in one with
AF_PACKET capture and `firewall.mode: none`, and connects from a public and a
private address in the other. The host's interfaces and firewall are not
touched, and the namespaces are removed when it ends. The threat database is
[`test/threat.mmdb`](./test/threat.mmdb), which scores the documentation range
203.0.113.0/24 at 90 and knows no other address.

To see the test fail, change `not axon.ip.is_private` to `axon.ip.is_private`
in `flow.lua` and run it again.
