# syslog-ng

A syslog-ng (AxoSyslog) config, `synapse-forward.conf`, that forwards
Synapse's syslog to a remote host over UDP. It also records where Synapse
sends its syslog and what limits a UDP hop has.

Tested with AxoSyslog 4.29.0, against the syslog format of Synapse 0.8.8.

## Where Synapse sends syslog

Synapse 0.8.8 has no setting for a remote syslog host or port. `logging.syslog`
holds `enabled`, `facility`, `identifier` and `levels`, and nothing else. This
is a gap. Synapse always sends to the syslog daemon on its own host, and that
daemon forwards the messages.

At start-up Synapse tries these targets once, in this order, and uses the first
that connects:

| Order | Target | Notes |
|-------|--------|-------|
| 1 | Unix datagram socket `/dev/log`, then `/var/run/syslog`, then `/var/run/log` | One message per datagram. A stream socket is used only when the path is one. |
| 2 | TCP `127.0.0.1:601` | Each message is written with no delimiter, so a receiver cannot split the stream. |
| 3 | UDP `127.0.0.1:514` | One message per datagram. |

Every message has this format. There is no hostname, and the day is
zero-padded:

```
<PRI>Mmm DD HH:MM:SS synapse[PID]: message
```

The program name is the `identifier` setting. App and access logs use the same
logger and the same target, so a forwarding config treats them alike.

Synapse picks the target once. If the syslog daemon starts after Synapse, or
`/dev/log` is missing at that moment, Synapse stays on the fallback it chose.

Containers MUST bind-mount the host's `/dev/log`, for example
`-v /dev/log:/dev/log`. Without it Synapse finds no socket and falls back to
the container's own localhost, where nothing listens. The messages go nowhere.

The CEF output is separate. It has its own host setting and does not go
through the local syslog daemon, so this config does not apply to it.

## Install

Set the receiver in the two `@define` lines at the top of
`synapse-forward.conf`:

```
@define synapse_remote_host "192.0.2.1"
@define synapse_remote_port 514
```

Then use it in one of two ways.

- **As the whole config.** Copy it to `/etc/syslog-ng/syslog-ng.conf` and
  reload syslog-ng. Use this on a host that runs syslog-ng only for Synapse.
- **Merged into an existing config.** Copy the `@define` lines, the `filter`,
  the `destination` and the `log` block. Replace the `source(s_synapse_local)`
  in the `log` block with the source your distribution already reads
  `/dev/log` with (often `s_src` or `s_sys`). Keep the UDP source if Synapse
  may fall back to it. Keep `flags(final)` only if you do not want Synapse's
  lines in the local log files.

The config does not open TCP 601. Synapse's TCP fallback writes messages with
no delimiter, so syslog-ng would merge them. If a host has no `/dev/log`,
fix that instead of accepting the TCP fallback.

## What the test measured

`make test-syslog-ng` runs the config in an AxoSyslog 4.29.0 container, sends
Synapse's wire format to it, and checks what a second container receives. These
are observations from that run:

- Without systemd, `system()` resolves to
  `unix-dgram("/dev/log" so_rcvbuf(8192) flags(syslog-protocol))`.
- The forwarded message has a hostname. For a message from `/dev/log` it is the
  sender's own. For one from the UDP source it is `localhost`. The day is
  space-padded (`Oct  5`), unlike on Synapse's wire.
- On the `/dev/log` path, the pid in `synapse[PID]` is the sending process's
  real pid, not the one in the text.
- Priority, program and message text arrive unchanged for records of 2.3 KB
  (the real samples), 16 KiB and 60 KiB, over both paths.
- A 70 KiB record sent to `/dev/log` arrives cut to a datagram of 65,507 bytes.
  syslog-ng counts it as truncated and logs no error.
- `log-msg-size` set to 131072 changes nothing in what arrives. Set to 8192, it
  cuts every record above 8 KiB, on both source paths.

## UDP limits

A syslog message over UDP is one datagram. Know these limits.

- A UDP payload cannot exceed 65,507 bytes. syslog-ng cuts longer messages to
  that size, and the receiver gets the start of the JSON without its end.
- On a 1500-byte MTU, a datagram with more than about 1,472 bytes of payload
  travels as IP fragments. Firewalls, NAT and cloud networks often drop
  fragments. The datagram is then lost whole.
- Access records are large. Measured from Synapse 0.8.8, without JA4 data:
  a passthrough record is 1,897 bytes of JSON, a routed request with curl's
  default headers 2,281 bytes, and one with 12 browser headers 2,969 bytes.
  The samples in `test/samples/` are 2,276 to 2,376 bytes. Every one of these
  is fragmented, so on a path that drops fragments every access record is
  lost, while short app lines still arrive. Measure the sizes on your own logs.
- Many receivers cut UDP syslog at 1 KiB, 2 KiB or 8 KiB. This cuts the JSON.
  Check the receiver's maximum message size.
- When the receiver's port was closed, the sender
  log showed `Syslog connection broken ... time_reopen='60'`. syslog-ng then
  waits 60 seconds before it sends again.
- On a systemd host, `system()` reads the journal. Its rate limit
  (`RateLimitIntervalSec` and `RateLimitBurst` in `journald.conf`) can drop
  messages under load. This path is untested here: the test containers have no
  journald.

TCP has no datagram ceiling and no fragmentation. If the receiver accepts it,
use TCP or TLS. The commented variants in `synapse-forward.conf` show both.
Raise `log-msg-size` when you do: its default of 64 KiB cuts long messages.
This is not tested.

## Verify

Send a test message through the local syslog daemon:

```bash
logger -t synapse -p daemon.info "forwarding test"
```

Check the destination counters. `dropped` MUST stay 0 and `queued` SHOULD be 0:

```bash
syslog-ng-ctl stats | grep d_synapse_remote
```

Look for IP fragments leaving the host. Each line is part of a datagram that was
too large for one packet:

```bash
tcpdump -n -i any 'udp and (ip[6:2] & 0x3fff != 0)'
```

On the receiver, run the same capture. Fragments that leave the sender but do
not arrive were dropped on the path.

## Test

```bash
make test-syslog-ng            # needs docker
make test-syslog-ng-controls   # breaks the config five ways; each MUST be caught
```

The test starts two containers on a private docker network and removes only
those it created. `AXOSYSLOG_IMAGE` overrides the image
(`ghcr.io/axoflow/axosyslog:4.29.0`).
