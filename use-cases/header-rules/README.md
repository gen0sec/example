# Add and remove headers on requests and responses

Rewrite the headers on the way to the back-end (request) and on the way back to
the client (response). `test.sh` checks every rule against the running example.

Two tools, layered global, then host, then route. At each level `headers:` runs
first, then that level's `transforms:`, so the more specific level wins.

| Tool | Does |
|---|---|
| `headers: request` / `response` | `"Name: value"` entries. Each one **sets** (replaces) the header |
| `transforms: request_headers` / `response_headers` | ordered rules with `remove`, `set`, `set_expr`, `add`, `add_expr`, and an optional `when` |

| What | Request | Response |
|---|---|---|
| Remove by exact name | `remove: ["X-Debug"]` | `remove: ["Server"]` |
| Remove by prefix | `remove: ["X-Internal-*"]` | `remove: ["X-Internal-*"]` |
| Set a literal | `headers:` entry, or `set:` | `headers:` entry, or `set:` |
| Set from an expression | `set_expr: { X-Client-Ip: to_string(ip.src) }` | `set_expr` with `http.response.*` fields |
| Add a value, keep the others | `add: { X-Trace: ... }` | `add: { Set-Cookie: [..., ...] }` |
| Only when a condition holds | `when: 'starts_with(http.request.path, "/api")'` | `when: 'http.response.status == 200'` |

Things to know:

- `remove` drops every value of the matching headers. `set` and `set_expr` replace
  the header. `add` and `add_expr` append a value, or a list of values.
- `*_expr` values must produce a string: wrap numbers and addresses in `to_string(...)`.
  An expression with no value (it reads a header that is not there) leaves the header alone.
- Request rules see the request as the client sent it and cannot use `http.response.*`.
  Response rules can.
- A rule that does not compile rejects the whole file, and the configuration already
  running stays in place. An unusable `headers:` entry is skipped with a warning.
- `Content-Length`, `Transfer-Encoding`, `Connection`, `Keep-Alive`, `TE`, `Trailer`,
  `Upgrade` and `Proxy-Connection` cannot be named in a rule, and a prefix `remove`
  skips them. `Sec-WebSocket-Key` and `Sec-WebSocket-Accept` are protected too.
- Rules do not apply to responses Synapse makes itself: block pages, redirects, 404s.
- Not available on a passthrough host itself, which has no request of its own. Set
  them on a path of a host with `paths:`.

## Run and test

```sh
docker compose up -d
./test.sh          # prints "ok" or "FAIL" per rule and exits 1 if any fails
docker compose down
```

The `/req` route goes to a back-end that echoes the request headers it received.
The `/resp` route goes to an nginx origin that sends headers a rule should remove or
replace. Set `BASE` if you publish another port, and `SYNAPSE_IMAGE` to use your own image.

To see the test fail, break one rule, for example change `remove: ["Server", "X-Powered-By"]` to
`remove: ["Nothing"]`, run `docker compose restart synapse` and `./test.sh` again.
