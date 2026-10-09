-- leads.phone is looked up on every single inbound SMS/WhatsApp message
-- (_handle_inbound_message's very first query), plus every phone-scoped
-- continuity cross-check (duplicate-lead history lookup, opt-out check,
-- mid-conversation defer guard) added this session. All of these were doing
-- a sequential scan over the entire leads table with no index at all.
-- Harmless at a handful of leads; the single most expensive, most
-- frequently-hit query in the system once lead volume grows.
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads (phone);
