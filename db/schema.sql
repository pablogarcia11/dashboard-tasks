CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,        -- git | notion | gcal | slack | github
  kind TEXT NOT NULL,          -- commit | wip | note | task | task_plan | meeting | message | pr | review
  external_id TEXT NOT NULL,
  ts TEXT NOT NULL,            -- ISO 8601 con zona
  work_date TEXT NOT NULL,     -- YYYY-MM-DD en zona del usuario
  title TEXT, body TEXT, url TEXT, project TEXT, status TEXT,
  extra_json TEXT,             -- p.ej. {"pushed": false, "branch": "..."}
  UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS activity_work_date ON activity(work_date);

CREATE TABLE IF NOT EXISTS summaries (
  id INTEGER PRIMARY KEY,
  work_date TEXT, kind TEXT,   -- standup | day_summary | notion_summary | timesheet | weekly
  content_md TEXT, input_hash TEXT, created_at TEXT,
  UNIQUE(work_date, kind)
);

CREATE TABLE IF NOT EXISTS sync_state (source TEXT PRIMARY KEY, last_ok TEXT, last_error TEXT);
