# Sample records

`records.jsonl` holds ten access records, one per line. The first three were
written by Synapse 0.8.8 in a local test (hosts `app.local` and `db.local`, all
on 127.0.0.1):

1. a request proxied on a `paths` route;
2. a TLS passthrough connection;
3. a proxied request with browser-like headers (its cookie is redacted by
   Synapse).

The other five are the first one, edited into shapes that need WAF rules or
particular traffic to produce:

4. a request blocked by the WAF: status 403 and a `remediation` block with
   every field Synapse writes;
5. a request the WAF challenged;
6. a request with a query string;
7. a record without `http`, which Synapse's schema allows;
8. a blocked POST with an 8 KiB body, so the record is over 10 KB;
9. a request for `/café`, written by `generate.sh` (Synapse 0.8.8). The path
   is UTF-8. Synapse wrote an empty user agent, because the request's
   `User-Agent: Ünïcode/1.0` header is not ASCII;
10. record 9 with one edit: its request id ends in `0`, and its two user agent
    values are `Ünïcode/1.0`. Synapse does not write a non-ASCII user agent,
    so a real one cannot be produced. The edit shows Splunk a UTF-8 value in
    the field.

`streams/access.py` derives nineteen more records from these when it runs, as a
relay that re-writes the JSON would send them. They are not in
`records.jsonl`. Each takes the `request_id` of its base record plus a
suffix. Records 1, 4 and 8 each give three, which are the same JSON in another
text form:

- `-sorted-spaced`: `json.dumps(rec, sort_keys=True)`;
- `-sorted-compact`: sorted keys, no spaces;
- `-spaced`: a space around every separator and after the opening brace.

Nine more, from record 1:

- `-hdr-native`, `-hdr-sorted-compact`, `-hdr-sorted-spaced`: the record
  with request headers named `timestamp` (a day before the record's own) and `request_id`. In
  sorted order they come before the record's own fields;
- `-err-sorted-compact`, `-err-sorted-spaced`: the record with an `error`
  object, sorted, whose message holds a quote, a backslash and braces;
- `-err-long-sorted-compact`, `-err-long-sorted-spaced`: the same with a plain
  message of over 4000 characters;
- `-err-esc-sorted-compact`, `-err-esc-sorted-spaced`: a message of over 4000
  characters with quotes, backslashes and braces throughout.

The nineteenth (`-sd`, from record 1, sorted and compact) is sent on tcp:5515
only, behind an RFC 5424 header with structured data `[x@1 k="{v}"]`.

Every source also gets one line that is not an access record: a record wrapped
in another JSON object (`{"host":"g0s-envelope","record":{...}}`). It must keep
the input's sourcetype and stay whole.

`test_splunk.py` sends these lines as they are, and with the syslog headers
that each ingest path adds.

## Generated samples

`generate.sh` runs the Synapse 0.8.8 container (`SYNAPSE_IMAGE`) three times
and writes the files below. Every line in them is what Synapse wrote, with
two changes. The container addresses are replaced by `192.0.2.10` (Synapse)
and `198.51.100.20` (the client). The hostname is `synapse-host`, set on the
container. Repeated shapes are dropped, so the files stay small. No line was
written by hand. `gen/collect.py` MUST find each shape the table below lists.
It exits non-zero and removes the old file when Synapse did not write one, so
one tree never mixes two runs. It also fails if an IPv4 address outside
192.0.2.0/24, 198.51.100.0/24, 127.0.0.0/8 or 0.0.0.0, or any IPv6 address,
is left in a file.

It pulls the image if it is missing, so it MAY need registry access
(`registry.gen0sec.com/gen0sec/synapse:0.8.8` by default). Synapse runs with
`--cap-add NET_RAW --ulimit memlock=-1:-1` and nothing else. Packet capture
works through AF_PACKET. The eBPF TLS probe fails ("Operation not permitted"), which is in
`app/error.log`.

| Run | events.log | app.log | CEF syslog |
|-----|------------|---------|------------|
| a | text | text | UDP, RFC 5424 |
| b | json | json | TCP, RFC 5424, octet counting |
| c | CEF | text | UDP, RFC 3164 |

| File | Run | What it is |
|------|-----|------------|
| `access/access.log` | a | 8 access records: proxied, query string, `/café`, two WAF blocks with `remediation`, a 429 rate limit, plain HTTP |
| `app/app.text.log`, `app/app.json.log` | a, b | the first 20 application lines, with an ERROR and a WARN line |
| `app/error.log` | a | `error.log` |
| `syslog/syslog.raw` | a | one datagram per message shape, as received (RFC 3164, no host): PRI 30, 28 and 27, and the ERROR pair that Synapse sends twice |
| `events/events.{text,json,cef}.log` | a, b, c | `events.log` in each format |
| `eve/eve.json` | a | one IDS stats event (`worker` `thalamus_ids_afpacket`), an alert for the ICMP rule (sid 1000001), an alert for the HTTP rule (sid 1000002) |
| `eventbridge/eventbridge.log` | a | ja4t, ja4ts, ja4, ja4s, plain and enriched with country and ASN |
| `telemetry/telemetry.log` | a | 6 records: 4 WAF (three blocks and the login rate limit, with trace and span ids), 2 IDS (`sid:1000001`, `sid:1000002`, without them) |
| `cef/cef.file.log` | a | `cef.log` |
| `cef/cef.udp-rfc5424.raw` | a | datagrams received on UDP |
| `cef/cef.udp-rfc3164.raw` | c | datagrams received on UDP, RFC 3164 header |
| `cef/cef.tcp-octet-counted.raw` | b | the TCP stream: `<octets> <message>`, no newline |

`cef/cef.tcp-octet-counted.raw` has one edit beyond the address change. The
octet count of each frame is written again, because the shorter addresses
change its length.

### Not produced

Synapse 0.8.8 did not write these in this setup. They are NOT in the
samples, and no line stands in for them.

- EVE `http` events and an EVE alert with an `http` object. They come from
  decrypted L7 transactions, which need an agent and a proxy in `offload`
  mode. The HTTP alert here (sid 1000002) has no `http` object.
- EVE IPv6-ICMP, an alert with the destination blanked, EVE `references`,
  and a stats event of any `worker` but the IDS one. The IDS stats event has
  `in_iface`. The capture worker (`afpacket_capture`) writes its stats every
  30 s, and only when the next frame arrives, so a run this short does not
  reach it. The EVE timestamps of alerts start in 1970, because Synapse
  writes them relative to its start.
- Fingerprint events of the `ja4l`, `ja4ls`, `ja4d` and `ja4ssh` kinds, the
  packet placeholder, and fractions of other widths. A run in which the
  fingerprint capture saw `ja4l` and `ja4ls` did not repeat in the final run.
- JSON events for smart_firewall/drop and captcha. The rate limit appears as
  a `waf` event with action `ratelimit`. Edited stand-ins are in
  `events/events.edited.*.log`, below.
- Text events whose value holds `\"` or `\u{2028}`, and a JSON event with
  only `ts`, `layer` and `action`. Edited stand-ins are below.
- `ban=` and `ids_sids=`. They come from smart_firewall bans, which this
  setup does not produce. Edited stand-ins are below.
- The telemetry `doubleValue` attribute type.
- IPv6 in any stream but the one edited line below, `cnt=3`, a CEF
  line without `rt`, a truncated record, and the relay shapes.

## Edited events.log lines

`events/events.edited.text.log` and `events/events.edited.json.log` are NOT
generated. They are hand-edited lines of `events.text.log` and
`events.json.log`, kept apart so that the generated files stay as Synapse
wrote them. Each line below differs from the line it came from in the one
thing named. The edited text lines start from the line with the same
address and port in `events.text.log`, the JSON ones from `events.json.log`.
The test checks them as it checks the real ones.

Text (`events.edited.text.log`):

| Line | From | Edit |
|---|---|---|
| 1 | `waf/block`, port 52256 | `msg` is `Block \"a=b\" admin\u{2028}x (response=403)`: an escaped quote, an `=` and `\u{2028}`, kept as written |
| 2 | `waf/block`, port 52256 | `src=2001:db8::1:443`: an IPv6 `ip:port` |
| 3 | `waf/ratelimit`, port 52310 | layer and action `rate_limit/ratelimit` |
| 4 | `waf/block`, port 52262 | layer and action `smart_firewall/drop` |
| 5 | `waf/block`, port 52270 | layer and action `captcha/captcha` |
| 6 | `waf/block`, port 52262 | layer and action `access_rules/block` |
| 7 | `waf/ratelimit`, port 52314 | layer and action `threat_intel/block` |
| 8 | `waf/block`, port 52256 | `ban=600s` added after `source=waf` |
| 9 | `ids/notice`, port 0 | `ids_sids=1,2` added |

JSON (`events.edited.json.log`):

| Line | From | Edit |
|---|---|---|
| 1 | `waf/block`, port 52300 | everything but `ts`, `layer` and `action` removed |
| 2 | `waf/ratelimit`, port 52334 | layer `rate_limit` |
| 3 | `waf/block`, port 52304 | layer and action `smart_firewall/drop` |
| 4 | `waf/block`, port 52308 | layer and action `captcha/captcha` |
| 5 | `waf/ratelimit`, port 52350 | `ban_secs` 600 added |
| 6 | `ids/notice`, port 0 | `ids_sids` `[1,2]` added |
