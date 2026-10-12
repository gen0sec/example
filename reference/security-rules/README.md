# Security rules reference

The security rules file holds the rules Synapse applies without a Gen0Sec API
key. Each directory is a config set that `synapse --check-config` accepts: a
`config.yaml` and a `security_rules.yaml` with every key explained.

| Directory | What it shows |
|---|---|
| [`access-rules/`](./access-rules/security_rules.yaml) | Allow and block lists by address, CIDR, country and ASN |
| [`waf-rules/`](./waf-rules/security_rules.yaml) | WAF rules with the `allow`, `block`, `challenge`, `ratelimit` and `content_scanning` actions |
| [`firewall-rules/`](./firewall-rules/security_rules.yaml) | 5-tuple rulesets with priority, direction and expiry |
| [`amygdala-rules/`](./amygdala-rules/security_rules.yaml) | Fingerprint (JA4 family) and address rules under `smart_firewall_rules` |

## Things to know

- `access_rules` and `waf_rules` are required keys. A file that only uses
  firewall or amygdala rules still carries them, empty.
- The amygdala rules live under `smart_firewall_rules`, not `amygdala_rules`.
  Whether amygdala runs is set in `config.yaml` under `firewall.amygdala`.
- WAF string tests use the function form: `starts_with(http.request.path, "/x")`.
  The infix form `http.request.path starts_with "/x"` is rejected.
- WAF rules run in file order and the first match wins, except
  `content_scanning`, which is not terminal: it marks the request and
  evaluation continues.
- The per-set `config.yaml` files are identical on purpose, so each set differs
  only in its `security_rules.yaml`.
- `challenge` needs `proxy.captcha` and `content_scanning` needs
  `proxy.content_scanning` in `config.yaml`. These sets do not set them, so the
  check says nothing about those keys.

## What `--check-config` does not check

It reports a rule that does not parse: an unknown WAF action, a WAF expression
that does not compile, a misspelled key in a typed section. It cannot see:

- keys inside `waf_rules.rules[].config`, so a typo such as `requets` under
  `rateLimit` passes; a missing `rateLimit` key logs an error at run time, but a
  non-numeric value silently falls back to 60 (period), 60 (duration) and 100
  (requests);
- a misspelled optional key on a `smart_firewall_rules` entry (for example
  `acton`), for the same reason; a misspelled `kind` is caught, because the
  entry then matches neither shape;
- whether a fingerprint value has the right shape for its `kind`, or whether
  an amygdala expression compiles; both are checked when the rules are applied;
- anything inside `firewall_rules`, because the rulesets are an untagged union.
  A misspelled key is ignored silently and its default applies: a misspelled
  `src_ip` matches every source and `protcol` becomes TCP, which can lock you
  out. Only an unparsable value (a bad port such as `"abc"`) makes the rule be
  skipped, with a warning at run time;
- whether the captcha or ClamAV settings a `challenge` or `content_scanning`
  rule relies on are present.
