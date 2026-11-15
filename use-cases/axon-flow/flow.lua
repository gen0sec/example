-- flow_by_axon: runs once for every flow the smart firewall evaluated.
--
-- It returns nil, or { tag = "x" }. The agent records the tag as an
-- `axon:<tag>` log-only entry next to the smart firewall's own matches.
-- This snippet never blocks: allow_block is off.

-- Leave a flow alone that is already being dropped.
for _, m in ipairs(axon.ctx.matches) do
  if m.action == "drop" then
    return nil
  end
end

-- A named expression from config.yaml, judged on this flow.
if axon.filter("tls_to_risky") then
  return { tag = "tls-to-risky" }
end

-- SSH from an address outside the private ranges. Helpers are pure and
-- bounded; a value that is not an address yields false, never an error.
if axon.ctx.dst_port == 22 and not axon.ip.is_private(axon.ctx.src_ip) then
  return { tag = "ssh-from-public" }
end

return nil
