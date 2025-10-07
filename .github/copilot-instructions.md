# Daralla AI Coding Agent Instructions

This document guides AI coding agents working in the Daralla Telegram VPN Bot codebase.

## Project Overview
Daralla is a Telegram bot that manages VPN keys and referral system. Key components:

- Core bot functionality (`bot/bot.py`) - Main bot logic and handlers
- Database management (`bot/keys_db.py`) - SQLite DB for payments, referrals and user data
- Notifications system (`bot/notifications.py`) - Handles user notifications and metrics

## Key Architecture Patterns

### Server Management
- Multi-server architecture with locations (Finland, Latvia, Estonia)
- `MultiServerManager` class handles server load balancing and health checks
- Server config loaded from environment variables
- Each server uses X3 class for XUI panel API interactions

### Database Structure
- SQLite databases in `data/` directory:
  - `vpn_keys.db` - Payments and transactions
  - `referral_system.db` - Referral connections and points
  - `notifications.db` - User notifications and metrics

### Notification System
- Automated expiry notifications (1 hour, 1 day, 3 days before)
- Notification metrics and effectiveness tracking
- Atomic operations for critical transactions

## Common Workflows

### Adding New Features
1. Update appropriate module (`bot.py`, `keys_db.py`, or `notifications.py`)
2. Use atomic operations for critical DB changes
3. Add proper logging with `logger`
4. Handle errors and edge cases
5. Update user messages through UIMessages class

### Error Handling Pattern
```python
try:
    # Critical operation
    logger.info("Operation starting...")
    # ... code ...
except Exception as e:
    logger.error(f"Operation failed: {e}")
    await notify_admin(bot, f"Critical error: {e}")
```

### Development Setup
1. Clone repo
2. Copy `env.example` to `.env` and configure:
   - Bot token
   - Admin ID
   - Server credentials
3. Use docker-compose for local development

## UI/UX Conventions
- Use UIMessages class for consistent messaging
- Follow button patterns in UIButtons
- Maintain navigation stack for proper back functionality
- Use proper emojis from UIEmojis class

## Database Interactions
- Always use async/await with aiosqlite
- Follow atomic operation patterns for critical changes
- Clean up old records periodically
- Validate inputs before DB operations

## Common Pitfalls
- Don't make synchronous network calls - use async
- Properly handle Telegram API errors
- Check user permissions before admin operations
- Validate all user inputs
- Handle message editing errors gracefully