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

CREATE TABLE IF NOT EXISTS report_images (
  report_id TEXT NOT NULL,
  image_index INTEGER NOT NULL,
  image_key TEXT NOT NULL,
  image_type TEXT NOT NULL,
  image_name TEXT NOT NULL,
  PRIMARY KEY (report_id, image_index),
  FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS report_images_report_id
  ON report_images (report_id, image_index);

CREATE TABLE IF NOT EXISTS daily_limits (
  quota_key TEXT NOT NULL,
  day TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (quota_key, day)
);

CREATE INDEX IF NOT EXISTS daily_limits_day
  ON daily_limits (day);

CREATE TABLE IF NOT EXISTS monthly_limits (
  quota_key TEXT NOT NULL,
  month TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (quota_key, month)
);

CREATE INDEX IF NOT EXISTS monthly_limits_month
  ON monthly_limits (month);
