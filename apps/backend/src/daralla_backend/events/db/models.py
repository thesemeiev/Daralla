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

event_counted_payments:
  id INTEGER PRIMARY KEY AUTOINCREMENT
  event_id INTEGER NOT NULL
  referrer_user_id TEXT NOT NULL
  payment_id TEXT NOT NULL
  paid_at TEXT NOT NULL (ISO datetime)
  UNIQUE(event_id, payment_id) — один балл на платёж в рамках события

event_rewards_granted:
  event_id INTEGER PRIMARY KEY
  granted_at TEXT NOT NULL

user_referral_codes:
  user_id TEXT PRIMARY KEY
  code TEXT NOT NULL UNIQUE
  created_at TEXT NOT NULL (ISO datetime)
"""
