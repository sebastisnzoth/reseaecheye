-- Versioned migration: visual comparisons are part of the final report.
ALTER TABLE investigations ADD COLUMN comparison_json TEXT;
ALTER TABLE investigations ADD COLUMN scene_json TEXT;
ALTER TABLE investigations ADD COLUMN manual_links_json TEXT;
