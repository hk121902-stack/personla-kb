CREATE TABLE IF NOT EXISTS saved_items (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  extracted_text TEXT NOT NULL,
  user_note TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  topic TEXT NOT NULL,
  summary TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  archived INTEGER NOT NULL,
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_surfaced_at TEXT,
  surface_count INTEGER NOT NULL,
  source_metadata_json TEXT NOT NULL,
  learning_brief_json TEXT NOT NULL DEFAULT '{}',
  ai_status TEXT NOT NULL DEFAULT 'pending',
  ai_attempt_count INTEGER NOT NULL DEFAULT 0,
  ai_last_attempt_at TEXT,
  ai_last_error TEXT NOT NULL DEFAULT '',
  embedding_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_items_user_archived
ON saved_items(user_id, archived, created_at);
