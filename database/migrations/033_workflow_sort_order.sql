-- Manual drag-and-drop ordering for the Automation panel's workflow cards.
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
