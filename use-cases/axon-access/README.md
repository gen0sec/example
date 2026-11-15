# axon: a Lua snippet on every request

Run a short Lua script on every request the WAF allowed. It can tag a request
in the access log, and block it. This is axon, in the style of OpenResty's
`access_by_lua_file`. Needs Synapse 0.8.10 or later, **built with the `axon`
cargo feature**, which is off by default.

`access.lua` does three things:

| What | How | Result |
|---|---|---|
| Block a path | `axon.re.match(axon.ctx.path, "^/admin")` | 403 |
| Limit a client to 30 requests a minute | `axon.shared.hits:incr(ip, 1, 0, 60)` | 403 above 30 |
| Tag a scanner | the user agent starts with `sqlmap` | the request passes; `axon_tag` is `scanner-ua` in `access.log` |

Things to know:

- The snippet runs only for requests the WAF **allowed**. A request the WAF
  blocked or challenged never reaches it.
- A snippet returns `nil`, `{ tag = "x" }` or `{ action = "block", tag = "x" }`.
  A block is enforced only when the phase sets `allow_block: true`. Without it,
  the block is logged and counted and nothing more. A snippet cannot allow a
  request or change one.
- `axon.ctx.path` is the path the WAF judged: `/%61dmin`, `//admin` and
  `/x/../admin` are all `/admin`, so a respelled path does not get past it.
- A shared dictionary must be declared in `snippet.shared_dicts`. It is
  process-wide: every worker thread sees the same counters. It is sized in
  entries, and a full dictionary drops the oldest.
- Time is bounded: a snippet that runs longer than the deadline (10 ms for
  this phase) is stopped, and a phase that fails 10 times in a row switches
  itself off until the next successful reload. A request is never failed by an
  error in a snippet.
- A snippet is code that runs in the proxy. Anyone who can write the file can
  run code there, so the loader refuses a file that is world-writable, that
  another group can write, or that is owned by a user other than root and the
  user Synapse runs as. In docker, make the mounted `access.lua` readable by
  that user and owned by root or by it.
- `snippet.required: true` makes a start fail when the snippet cannot load, so
  the proxy does not run without its rules. A reload that fails keeps the
  last snippet that worked.
- This example counts the address Synapse sees. Behind a load balancer, set
  `proxy.trusted_proxies` so that it counts the client's address.

## Run and test

Use an image of Synapse 0.8.10 that was built with the `axon` feature:

```sh
export SYNAPSE_IMAGE=<your axon image>
docker compose up -d
./test.sh          # prints "ok" or "FAIL" per check and exits 1 if any fails
docker compose down
```

The rate limit counts a minute, so wait 60 seconds before you run `test.sh`
again. A binary without the feature starts, logs a warning that it was built
without `axon`, and runs no snippet (with `required: true` it refuses to
start); `test.sh` then fails on the first block.

To see the test fail, change `"^/admin"` to `"^/nothing"` in `access.lua`,
run `docker compose restart synapse` and `./test.sh` again.

`synapse --check-config` also validates the snippet: it reports a Lua syntax
error, a snippet that is not found or not safe to load, and a build without the
feature.
