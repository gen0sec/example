# Sample records

`records.jsonl` holds eight access records, one per line. The first three were
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
8. a blocked POST with an 8 KiB body, so the record is over 10 KB.

`test_splunk.py` sends these lines as they are, and with the syslog headers
that each ingest path adds.
