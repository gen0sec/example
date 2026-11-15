-- access_by_axon: runs once for every request the WAF allowed.
--
-- A snippet can observe and annotate, and block when the phase sets
-- `allow_block: true`. It cannot allow a request the WAF blocked.
-- What it returns:
--   nil                              nothing happens
--   { tag = "x" }                    the tag goes to the access log
--   { action = "block", tag = "x" }  the proxy answers 403

-- 1. A path nobody should reach from outside.
if axon.re.match(axon.ctx.path, "^/admin") then
  return { action = "block", tag = "admin-path" }
end

-- 2. A client that makes more than LIMIT requests a minute. `incr` adds 1
-- to the counter of this address, starts it at 0 and lets it expire after
-- 60 seconds. The dict is nil when it is not declared in config.yaml.
local LIMIT = 30
local hits = axon.shared.hits
if hits then
  local n = hits:incr(axon.ctx.client_ip, 1, 0, 60)
  if n and n > LIMIT then
    return { action = "block", tag = "rate-limit" }
  end
end

-- 3. A scanner is only tagged. The tag shows in the access log.
local ua = axon.ctx.user_agent
if ua and axon.re.match(ua, "^sqlmap") then
  return { tag = "scanner-ua" }
end

return nil
