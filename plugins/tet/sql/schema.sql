CREATE TABLE IF NOT EXISTS fx_proposal(
  id INTEGER PRIMARY KEY,
  run TEXT,
  grp TEXT,
  verb TEXT NOT NULL,
  argv TEXT NOT NULL CHECK (json_valid(argv)),
  writes TEXT NOT NULL CHECK (json_valid(writes)),
  body TEXT,
  target TEXT,
  base TEXT,
  why TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  decided_by TEXT,
  decided_at TEXT,
  applied_at TEXT,
  result TEXT
);
CREATE INDEX IF NOT EXISTS fx_proposal_status ON fx_proposal(status, run);
CREATE INDEX IF NOT EXISTS fx_proposal_target ON fx_proposal(target);
