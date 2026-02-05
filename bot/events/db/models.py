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
  referrer_account_id TEXT NOT NULL
  referred_account_id TEXT NOT NULL
  created_at TEXT NOT NULL (ISO datetime)
  UNIQUE(referred_account_id, event_id)

event_counted_payments:
  id INTEGER PRIMARY KEY AUTOINCREMENT
  event_id INTEGER NOT NULL
  referred_account_id TEXT NOT NULL
  paid_at TEXT NOT NULL (ISO datetime)
  UNIQUE(event_id, referred_account_id)

user_referral_codes:
  account_id TEXT PRIMARY KEY
  code TEXT NOT NULL UNIQUE
  created_at TEXT NOT NULL
"""
