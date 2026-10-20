# Sample records

`records.jsonl` holds four access records, one per line, written by Synapse
0.8.8 in a local test (hosts `app.local` and `db.local`, all on 127.0.0.1):

1. a request proxied on a `paths` route;
2. a TLS passthrough connection;
3. a proxied request with browser-like headers (its cookie is redacted by
   Synapse);
4. a request blocked by the WAF. This one is the first record, edited into
   the shape Synapse writes for a block (status 403 and a `remediation`
   block), because producing it needs WAF rules.

`test_splunk.py` sends these lines as they are, and with the syslog headers
that each ingest path adds.
