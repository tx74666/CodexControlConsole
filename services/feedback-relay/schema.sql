CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  image_key TEXT,
  image_type TEXT,
  image_name TEXT,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'resolved')),
  app_version TEXT NOT NULL DEFAULT '',
  os_version TEXT NOT NULL DEFAULT '',
  locale TEXT NOT NULL DEFAULT '',
  module TEXT NOT NULL DEFAULT '',
  device_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS reports_status_created_at
  ON reports (status, created_at DESC);

CREATE TABLE IF NOT EXISTS daily_limits (
  quota_key TEXT NOT NULL,
  day TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (quota_key, day)
);

CREATE INDEX IF NOT EXISTS daily_limits_day
  ON daily_limits (day);
