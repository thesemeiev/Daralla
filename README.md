# Daralla VPN Bot 🚀

Modern Telegram Mini App & Web Dashboard for VPN subscription management with unified webhook API and Remnawave integration.

## 📋 Features

- **Telegram Mini App** - Subscribe to VPN directly from Telegram
- **Web Dashboard** - Manage subscriptions via web interface (HTML5, PWA)
- **Payment Integration** - YooKassa webhook for payment processing
- **Remnawave API** - VPN server management and user provisioning
- **Unified Authentication** - Single auth for Telegram, Web tokens, and Admin access
- **Type-Safe API** - Full type hints (Pylance validated, 0 errors)
- **Comprehensive Tests** - 100+ unit and integration tests

## 🏗️ Project Structure

```
bot/
  ├─ handlers/webhooks/
  │  ├─ webhook_utils.py         # Core API library (auth, responses, async)
  │  ├─ webhook_auth.py          # Authentication logic
  │  ├─ payment_processors.py    # YooKassa webhook handlers
  │  └─ routes/
  │     ├─ api_user.py           # User endpoints (register, payment, etc)
  │     ├─ api_auth.py           # Web auth (login, register, verify)
  │     ├─ api_admin.py          # Admin endpoints
  │     └─ payment.py            # Payment webhook endpoint
  ├─ services/
  │  ├─ remnawave_service.py     # Remnawave API client
  │  ├─ subscription_service.py  # Subscription logic
  │  └─ notification_manager.py  # Push notifications
  ├─ db/
  │  ├─ accounts_db.py           # Account management
  │  ├─ payments_db.py           # Payment history
  │  └─ ...
  └─ events/                      # Event system for payments

webapp/                           # Web UI (HTML, CSS, JS, PWA)
tests/                            # Test suite
  ├─ conftest.py                 # Test fixtures
  ├─ test_webhook_utils.py       # Unit tests (40 tests)
  ├─ test_integration_auth.py    # Auth integration tests
  └─ test_integration_payment.py # Payment integration tests

docs/                             # Documentation
docker-compose.yml               # Docker setup
requirements.txt                 # Python dependencies
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose (optional)
- YooKassa merchant account
- Remnawave API credentials
- Telegram Bot Token

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run tests:**
   ```bash
   pytest tests/test_webhook_utils.py -v
   pytest tests/test_integration_auth.py -v
   pytest tests/test_integration_payment.py -v
   ```

4. **Start the bot:**
   ```bash
   python -m bot.bot
   ```

5. **Start webhook server:**
   ```bash
   # The webhook API starts automatically with the bot
   # API available at http://localhost:5000/api/*
   ```

### Docker

```bash
docker-compose up -d
```

## 📡 API Endpoints

### User API (`/api/user/*`)
- `POST /api/user/register` - Register new user
- `GET /api/subscriptions` - Get user subscriptions
- `POST /api/user/payment/create` - Create payment
- `GET /api/user/payment/status/<id>` - Check payment status
- `GET /api/user/server-usage` - Get server usage
- `POST /api/user/web-access/setup` - Setup web login
- `POST /api/user/link-telegram/start` - Link Telegram account

### Auth API (`/api/auth/*`)
- `POST /api/auth/register` - Web registration
- `POST /api/auth/login` - Web login
- `POST /api/auth/verify` - Verify token

### Webhooks
- `POST /webhook/yookassa` - YooKassa payment webhook
- `GET /sub/<token>` - Subscription link (universal)

## 🔐 Authentication

Three authentication methods supported:

### 1. Telegram Mini App
```javascript
// Frontend sends initData
const initData = window.Telegram.WebApp.initData;
fetch('/api/user/register', {
  method: 'POST',
  body: JSON.stringify({ initData })
})
```

### 2. Web Token
```javascript
// After login, use Bearer token
fetch('/api/user/register', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

### 3. Admin Token
- Admin accounts get admin access automatically
- Use same Bearer token with `Authorization` header

## 🧪 Testing

### Unit Tests (40 tests)
```bash
pytest tests/test_webhook_utils.py -v
```
Tests: APIResponse, AuthContext, Decorators, Async, Edge Cases, Performance

### Integration Tests
```bash
pytest tests/test_integration_auth.py -v
pytest tests/test_integration_payment.py -v
```

### Run all tests
```bash
pytest tests/ -v
```

## 📦 Core Components

### webhook_utils.py
Unified API library providing:
- `APIResponse` - Consistent response format (success, error, 400, 401, 403, 404, 409, 500)
- `@require_auth` - Authentication decorator
- `@require_admin` - Admin check decorator
- `run_async()` - Event loop management for async operations
- `AuthContext` - Type-safe auth data structure
- `handle_options()` - CORS preflight handling

### webhook_auth.py
Authentication & verification:
- `authenticate_request()` - Parse & validate auth
- `verify_telegram_init_data()` - Validate Telegram Mini App data
- `check_admin_access()` - Check admin permissions

### Remnawave Integration
Connects to Remnawave VPN API for:
- User creation and lifecycle
- Subscription expiry management
- Device limit control
- Sub info queries

## 🔄 Payment Flow

1. User clicks "Buy subscription"
2. App calls `POST /api/user/payment/create`
3. YooKassa OAuth flow redirected to user
4. User completes payment
5. YooKassa sends webhook to `/webhook/yookassa`
6. Server activates subscription in Remnawave
7. User receives Telegram notification
8. Subscription active in webapp

## 📊 Database

Single SQLite database (`data/app.db`) containing:
- **accounts** - User accounts
- **identities** - Multi-account support (Telegram ID, username, etc)
- **payments** - Payment history
- **notifications** - Notification log
- **server_config** - Node override mappings

## 🚨 Error Handling

All endpoints return consistent error format:
```json
{
  "success": false,
  "error": "User not found",
  "error_code": "NOT_FOUND"
}
```

HTTP Status Codes:
- `200` - Success
- `400` - Bad request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not found
- `409` - Conflict
- `500` - Internal error

## 🔧 Configuration

See `.env.example` for all configuration variables:
- `BOT_TOKEN` - Telegram bot token
- `WEBHOOK_URL` - Webhook server URL
- `REMNAWAVE_API_KEY` - Remnawave API credentials
- `YOOKASSA_SHOP_ID` - YooKassa merchant ID
- `YOOKASSA_API_KEY` - YooKassa API key

## 📚 Documentation

- `docs/DEPLOY.md` - Deployment guide
- `docker-compose.yml` - Docker setup
- `Dockerfile` - Container image

## 🛠️ Development

### Code Quality
- Type hints: 100% coverage (Pylance validated)
- Tests: 100+ test cases
- No linting errors

### Adding New Endpoints

1. Create route function with `@bp.route()` decorator
2. Use `@require_auth` or `@require_admin` if needed
3. Return `APIResponse.success()` or `APIResponse.error()`
4. Add unit tests to `tests/test_webhook_utils.py`

Example:
```python
@bp.route('/api/example', methods=['POST', 'OPTIONS'])
@require_auth
def api_example(auth: AuthContext):
    if request.method == 'OPTIONS':
        return handle_options()
    
    try:
        return APIResponse.success(result="data")
    except Exception as e:
        logger.error(f"Error: {e}")
        return APIResponse.internal_error()
```

## 📄 License

See LICENSE file

## 👨‍💻 Support

For issues or questions, please open an issue in the repository.
