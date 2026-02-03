"""
Описание таблиц модуля событий.

events:
  id INTEGER PRIMARY KEY AUTOINCREMENT
  name TEXT NOT NULL
  description TEXT
  start_at TEXT NOT NULL (ISO datetime)
  end_at TEXT NOT NULL (ISO datetime)
  rewards_json TEXT (JSON: [{place, days}, ...])
  status TEXT (active, ended, draft)
  created_at TEXT NOT NULL (ISO datetime)

event_referrals:
  id INTEGER PRIMARY KEY AUTOINCREMENT
  event_id INTEGER NOT NULL
  referrer_user_id TEXT NOT NULL
  referred_user_id TEXT NOT NULL
  created_at TEXT NOT NULL (ISO datetime)
  UNIQUE(referred_user_id, event_id) — один приглашённый на один event_id

event_counted_payments:
  id INTEGER PRIMARY KEY AUTOINCREMENT
  event_id INTEGER NOT NULL
  referred_user_id TEXT NOT NULL
  paid_at TEXT NOT NULL (ISO datetime)
  UNIQUE(event_id, referred_user_id) — один засчёт на пару событие+приглашённый
"""
