# Splunk

A Splunk add-on, `TA-gen0sec-synapse`, that parses Synapse access logs. It
works when the logs arrive through syslog (for example via AxoSyslog) or
straight from a file. It maps each record to the CIM Web data model.

Tested with Splunk Enterprise 9.0.1 and AxoSyslog 4.29, on records written
by Synapse 0.8.8.

## What it does

Synapse sends app logs and access logs to syslog under the same identifier
(`synapse`). Send that whole stream to Splunk with the sourcetype
`gen0sec:synapse`. The add-on then does the following:

- It moves each access record to the sourcetype `gen0sec:synapse:access`. App
  log lines keep `gen0sec:synapse`.
- It removes any syslog header in front of an access record, so `_raw` is the
  record's JSON. This covers an RFC 3164 or RFC 5424 header, AxoSyslog's file
  format, and its HEC raw format.
- It recognises an access record that a relay re-serialised: spaces around
  the JSON separators, keys in sorted order (so `event_type` is not first),
  and an RFC 5424 header whose structured data contains `{`. `_raw` stays the
  record as the relay sent it. The header must be under 256 bytes. Keys that
  sort in front of `event_type` may hold strings, numbers, `true`, `false`,
  `null` or one level of object (the `error` of a failed request); an array
  or a deeper object there stops the match, and so does a key that sorts
  in front of `event_type` and pushes it past the first 16384 bytes (an `error`
  message of about 16 KB). A record inside another JSON
  object, such as `{"host":"r1","record":{...}}`, is not recognised and stays
  as it came. A line that holds an access record within its first 256
  characters is routed, so an app log line that quotes one is too.
- It takes `_time` from the record's own top-level `timestamp` (UTC), not from
  the syslog header and not from a request header named `timestamp`.
- It takes `host` from the syslog header when a program tag follows the host
  (`host prog[pid]:`), or from an RFC 5424 header, and it may be an IPv4 or
  IPv6 address. A line with no host in its
  header, such as Synapse's own `<30>Oct 20 14:28:21 synapse[1]: msg`, keeps
  the input's host.
- It extracts every JSON field (`http.method`, `network.src_ip`,
  `upstream.method`, …) and adds the CIM fields below.

Passthrough connections are logged as access records too.

## Install

Copy `TA-gen0sec-synapse/` to `$SPLUNK_HOME/etc/apps/` on every indexer and
heavy forwarder, and on the search heads. Then restart Splunk. The index-time
part (header removal, timestamp, sourcetype) runs where the data is parsed:
the indexers, or a heavy forwarder in front of them. A Universal Forwarder
does not parse, so it does not need the add-on.

```bash
cp -r TA-gen0sec-synapse "$SPLUNK_HOME/etc/apps/"
"$SPLUNK_HOME/bin/splunk" restart
```

In a cluster, install it the way Splunk distributes apps there:

- **Indexer cluster.** Copy it to `$SPLUNK_HOME/etc/manager-apps/` on the
  cluster manager (`master-apps/` before 9.0), then run
  `splunk apply cluster-bundle`.
- **Search head cluster.** Copy it to `$SPLUNK_HOME/etc/shcluster/apps/` on the
  deployer, then run `splunk apply shcluster-bundle -target <a member's URI>`.

## Enable syslog in Synapse

```yaml
logging:
  syslog:
    enabled: true
    facility: daemon
    identifier: synapse
    levels:
      error: err
      app: info
      access: info
```

## Get the logs into Splunk

Pick one of the three paths. Each AxoSyslog snippet assumes a source named
`s_local` that reads `/dev/log`, and selects Synapse's messages with:

```
filter f_synapse { program("synapse"); };
```

### 1. AxoSyslog writes a file, a Universal Forwarder reads it

AxoSyslog. It creates files readable by root only (mode 0600), so give the
group of the user the forwarder runs as read access. Replace `FORWARDER-GROUP`
with that group: a Universal Forwarder runs as `splunkfwd` since 9.1, and as
`splunk` before that.

```
destination d_synapse_file {
  file("/var/log/synapse/syslog.log"
       create-dirs(yes) dir-group("FORWARDER-GROUP") dir-perm(0750)
       group("FORWARDER-GROUP") perm(0640));
};
log { source(s_local); filter(f_synapse); destination(d_synapse_file); };
```

`group()`, `perm()` and their `dir-` forms apply when AxoSyslog creates the file
or directory. Change the permissions of existing ones by hand.

Forwarder `inputs.conf`:

```ini
[monitor:///var/log/synapse/syslog.log]
sourcetype = gen0sec:synapse
index = main
```

### 2. AxoSyslog sends syslog to a Splunk TCP input

AxoSyslog. Both forms send one message per line. The first is RFC 3164; the
second, with `flags(syslog-protocol)`, is RFC 5424:

```
destination d_splunk_tcp { network("splunk.example.com" port(5514) transport("tcp")); };
# or: network("splunk.example.com" port(5514) transport("tcp") flags(syslog-protocol));
log { source(s_local); filter(f_synapse); destination(d_splunk_tcp); };
```

Splunk `inputs.conf`:

```ini
[tcp://5514]
sourcetype = gen0sec:synapse
connection_host = dns
index = main
```

Do not use AxoSyslog's `syslog()` driver for this. Over TCP, it puts a byte
count in front of each message instead of ending it with a newline, and a
Splunk TCP input cannot split that.

### 3. AxoSyslog sends to the HTTP Event Collector

Create a HEC token in Splunk (Settings → Data inputs → HTTP Event Collector).
Then use either destination.

**Raw** sends the whole stream, like paths 1 and 2:

```
destination d_splunk_hec {
  splunk-hec-raw(
    url("https://splunk.example.com:8088")
    token("YOUR-HEC-TOKEN")
    channel("8a5a8a8e-0000-4000-8000-000000000001")   # any GUID
    default_sourcetype("gen0sec:synapse")
    default_index("main")
  );
};
log { source(s_local); filter(f_synapse); destination(d_splunk_hec); };
```

**Event** sends access records only, as the access sourcetype. Keep both
`time("")` and `auto_extract_timestamp=true`. Without them, `_time` is the
syslog header's whole second: Splunk uses a `time` sent with the event and
ignores the record's own time.

```
filter f_synapse_access { program("synapse") and message('"event_type":"http_access_log"'); };
destination d_splunk_hec {
  splunk-hec-event(
    url("https://splunk.example.com:8088")
    token("YOUR-HEC-TOKEN")
    sourcetype("gen0sec:synapse:access")
    index("main")
    time("")
    extra_queries("&auto_extract_timestamp=true")
  );
};
log { source(s_local); filter(f_synapse_access); destination(d_splunk_hec); };
```

## Fields

`KV_MODE = json` extracts every field of the record. On top of them:

| Field | From | Note |
|---|---|---|
| `src`, `src_port` | `network.src_ip`, `network.src_port` | |
| `dest`, `dest_port` | `network.dst_ip`, `network.dst_port` | |
| `site` | `http.host` | The SNI name for a passthrough connection |
| `http_method` | `http.method` | Absent for passthrough |
| `uri_path`, `uri_query` | `http.path`, `http.query` | Absent when empty |
| `url` | scheme, host, port, path and query | Absent for passthrough |
| `status` | `response.status` | `0` for passthrough |
| `http_user_agent`, `http_content_type` | `http.user_agent`, `http.content_type` | Absent when not sent |
| `bytes_in`, `bytes_out` | `http.content_length`, `response.content_length` | For passthrough: bytes to the upstream and bytes to the client |
| `duration` | `performance.request_time_ms` | Milliseconds |
| `action` | `remediation.waf_action` | `blocked` for `block`, `challenge` or `ratelimit`, otherwise `allowed` |
| `synapse_mode` | `upstream.method` | `passthrough` or `proxy` |
| `vendor`, `product`, `vendor_product` | | `Gen0Sec`, `Synapse`, `Gen0Sec Synapse` |

Access records have the eventtype `gen0sec_synapse_access`, tagged `web`.

## events.log

Synapse's `events.log` holds one line per block: the layer that acted (`waf`,
`ids`, `captcha`, `threat_intel`, `smart_firewall`, `access_rules` or
`rate_limit`), the action, the addresses and the rule. Read the file with a
monitor input and the sourcetype `gen0sec:synapse:events`. Both the text and
the JSON format are parsed:

```
[monitor:///var/log/synapse/events.log]
sourcetype = gen0sec:synapse:events
index = main
```

The add-on takes `_time` from `ts` (UTC, to the second) and extracts
`layer`, `action` and the other keys, including the nested `eve` object of an
IDS line (`eve.alert.signature_id`). A text value keeps its escapes as
written. An IPv6 address stays whole: `src` holds `2001:db8::1:443` and
there is no `src_ip` or `src_port`. On top of them:

| Field | Note |
|---|---|
| `src`, `src_port`, `dest`, `dest_port` | The address and port, split apart |
| `synapse_action` | The action as Synapse wrote it |
| `action` | `blocked` for `block`, `ratelimit`, `captcha` or `drop`, otherwise `allowed` |
| `signature`, `signature_id`, `category`, `severity`, `ids_type` | Intrusion_Detection, for `ids`, `waf`, `captcha` and `threat_intel` |
| `rule` | Network_Traffic, for `smart_firewall`, `access_rules` and `rate_limit` |
| `dvc`, `vendor`, `product`, `vendor_product` | The host, `Gen0Sec`, `Synapse`, `Gen0Sec Synapse` |

`ids`, `waf`, `captcha` and `threat_intel` events have the eventtype
`gen0sec_synapse_events_ids`, tagged `ids` and `attack`. The others have
`gen0sec_synapse_events_network`, tagged `network` and `communicate`. Every
event with a layer also has `gen0sec_synapse_events`.

A JSON line has a `source` key (`waf`), and Splunk adds it as a second value of
the `source` field. A search for `source="/var/log/synapse/events.log"` still
finds the line, but `| table source` shows both values. In a text line Splunk
does not extract it. A CEF line (`format = cef`) keeps the sourcetype and is
not parsed.

## Sample searches

```
sourcetype="gen0sec:synapse:access" action=blocked
| stats count by src, remediation.waf_rule_name

sourcetype="gen0sec:synapse:access" synapse_mode=proxy
| timechart span=5m perc95(duration) by site

sourcetype="gen0sec:synapse:access" status>=500
| stats count by site, upstream.selected
```

## Limits

- **Message size.** An access record carries the request body when
  `platform.include_request_body` is on, up to `max_body_size`. AxoSyslog
  cuts messages at `log-msg-size` (64 KiB by default), and UDP cannot carry
  more than about 64 KiB. Either one leaves a cut record that is not valid
  JSON. If you log bodies, use TCP or HEC and raise `log-msg-size` in
  AxoSyslog's `options {}`. The add-on accepts events up to 8 MiB
  (`TRUNCATE`).
- **App log lines** keep the sourcetype `gen0sec:synapse`. The add-on does not
  parse them. Their time is the syslog header's.

## Test

`test/test_splunk.py` runs Splunk 9.0.1 in docker with this add-on and sends
the sample records in `test/samples/` along every path above. It then checks
each event's sourcetype, `_time`, `_raw` and CIM fields. It needs docker and
downloads the Splunk image (about 1 GB) on first use.

```bash
make test-splunk
```
