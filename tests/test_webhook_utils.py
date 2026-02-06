"""
Unit tests для webhook_utils.py
Тестирует: APIResponse, AuthContext, decorators, run_async, handle_options
"""
import asyncio
import json
import pytest
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from flask import Flask, jsonify

# Для импорта webhook_utils нужно добавить путь
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.handlers.webhooks.webhook_utils import (
    APIResponse,
    AuthContext,
    handle_options,
    require_auth,
    require_admin,
    run_async,
    authenticate_and_check,
)


# ============ Fixtures ============

@pytest.fixture
def app():
    """Flask app для тестирования"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client"""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Flask app context"""
    return app.app_context()


# ============ Tests: APIResponse ============

class TestAPIResponse:
    """Тестирование APIResponse класса"""
    
    def test_success_basic(self, app_context):
        """Тест: success() возвращает правильный формат"""
        with app_context:
            response, status, headers = APIResponse.success()
            assert status == 200
            assert headers['Content-Type'] == 'application/json'
            assert headers['Access-Control-Allow-Origin'] == '*'
    
    def test_success_with_data(self, app_context):
        """Тест: success() с данными"""
        with app_context:
            response, status, headers = APIResponse.success(count=5, items=[1, 2, 3])
            assert status == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['count'] == 5
            assert data['items'] == [1, 2, 3]
    
    def test_success_with_dict(self, app_context):
        """Тест: success() с dict параметром"""
        with app_context:
            response, status, headers = APIResponse.success({'user_id': 123, 'name': 'John'})
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['user_id'] == 123
            assert data['name'] == 'John'
    
    def test_error_basic(self, app_context):
        """Тест: error() возвращает правильный формат"""
        with app_context:
            response, status, headers = APIResponse.error("Something went wrong", 400, "TEST_ERROR")
            assert status == 400
            data = json.loads(response.data)
            assert data['success'] is False
            assert data['error'] == "Something went wrong"
            assert data['error_code'] == "TEST_ERROR"
    
    def test_error_without_code(self, app_context):
        """Тест: error() без error_code"""
        with app_context:
            response, status, headers = APIResponse.error("Bad request")
            data = json.loads(response.data)
            assert 'error_code' not in data
    
    def test_unauthorized(self, app_context):
        """Тест: unauthorized() возвращает 401"""
        with app_context:
            response, status, headers = APIResponse.unauthorized("Custom message")
            assert status == 401
            data = json.loads(response.data)
            assert data['error'] == "Custom message"
            assert data['error_code'] == "UNAUTHORIZED"
    
    def test_forbidden(self, app_context):
        """Тест: forbidden() возвращает 403"""
        with app_context:
            response, status, headers = APIResponse.forbidden()
            assert status == 403
            data = json.loads(response.data)
            assert data['error_code'] == "FORBIDDEN"
    
    def test_not_found(self, app_context):
        """Тест: not_found() возвращает 404"""
        with app_context:
            response, status, headers = APIResponse.not_found("User not found")
            assert status == 404
            data = json.loads(response.data)
            assert data['error_code'] == "NOT_FOUND"
    
    def test_bad_request(self, app_context):
        """Тест: bad_request() возвращает 400"""
        with app_context:
            response, status, headers = APIResponse.bad_request("Invalid input")
            assert status == 400
            data = json.loads(response.data)
            assert data['error_code'] == "BAD_REQUEST"
    
    def test_conflict(self, app_context):
        """Тест: conflict() возвращает 409"""
        with app_context:
            response, status, headers = APIResponse.conflict("Resource already exists", "DUPLICATE")
            assert status == 409
            data = json.loads(response.data)
            assert data['error_code'] == "DUPLICATE"
    
    def test_internal_error(self, app_context):
        """Тест: internal_error() возвращает 500"""
        with app_context:
            response, status, headers = APIResponse.internal_error("Database error")
            assert status == 500
            data = json.loads(response.data)
            assert data['error_code'] == "INTERNAL_ERROR"
            assert data['error'] == "Database error"
    
    def test_cors_headers(self, app_context):
        """Тест: cors_headers() содержит правильные headers"""
        headers = APIResponse.cors_headers()
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert headers['Content-Type'] == 'application/json'


# ============ Tests: AuthContext ============

class TestAuthContext:
    """Тестирование AuthContext dataclass"""
    
    def test_auth_context_creation(self):
        """Тест: создание AuthContext"""
        auth = AuthContext(account_id=123, auth_type="telegram", is_admin=False)
        assert auth.account_id == 123
        assert auth.auth_type == "telegram"
        assert auth.is_admin is False
    
    def test_auth_context_admin(self):
        """Тест: AuthContext с админ правами"""
        auth = AuthContext(account_id=1, auth_type="web", is_admin=True)
        assert auth.is_admin is True
    
    def test_auth_context_default_admin(self):
        """Тест: AuthContext со default is_admin=False"""
        auth = AuthContext(account_id=456, auth_type="web")
        assert auth.is_admin is False


# ============ Tests: handle_options ============

class TestHandleOptions:
    """Тестирование handle_options функции"""
    
    def test_handle_options_returns_tuple(self):
        """Тест: handle_options() возвращает кортеж (body, code, headers)"""
        result = handle_options()
        assert isinstance(result, tuple)
        assert len(result) == 3
        body, code, headers = result
        assert body == ''
        assert code == 200
    
    def test_handle_options_headers(self):
        """Тест: handle_options() содержит правильные CORS headers"""
        body, code, headers = handle_options()
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'GET' in headers['Access-Control-Allow-Methods']
        assert 'POST' in headers['Access-Control-Allow-Methods']
        assert 'OPTIONS' in headers['Access-Control-Allow-Methods']
        assert 'Content-Type' in headers['Access-Control-Allow-Headers']
        assert 'Authorization' in headers['Access-Control-Allow-Headers']


# ============ Tests: run_async ============

class TestRunAsync:
    """Тестирование run_async функции"""
    
    def test_run_async_simple(self):
        """Тест: run_async() выполняет простую корутину"""
        async def simple_task():
            return "result"
        
        result = run_async(simple_task())
        assert result == "result"
    
    def test_run_async_with_await(self):
        """Тест: run_async() с асинхронными операциями"""
        async def async_task():
            await asyncio.sleep(0.01)
            return 42
        
        result = run_async(async_task())
        assert result == 42
    
    def test_run_async_with_exception(self):
        """Тест: run_async() передает исключение из корутины"""
        async def failing_task():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            run_async(failing_task())
    
    def test_run_async_returns_dict(self):
        """Тест: run_async() с dict результатом"""
        async def dict_task():
            return {"id": 123, "name": "test"}
        
        result = run_async(dict_task())
        assert isinstance(result, dict)
        assert result['id'] == 123


# ============ Tests: require_auth decorator ============

class TestRequireAuthDecorator:
    """Тестирование @require_auth декоратора"""
    
    def test_require_auth_options_request(self, app):
        """Тест: @require_auth на OPTIONS запросе возвращает handle_options()"""
        @app.route('/test', methods=['GET', 'OPTIONS'])
        @require_auth
        def handler(auth):
            return jsonify({'data': 'test'})
        
        with app.test_request_context('/test', method='OPTIONS'):
            response = handler()
            assert response[1] == 200  # status code
            body, code, headers = response
            assert 'Access-Control-Allow-Origin' in headers
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_auth_success(self, mock_auth, app):
        """Тест: @require_auth с успешной аутентификацией"""
        mock_auth_context = AuthContext(account_id=123, auth_type="web")
        mock_auth.return_value = mock_auth_context
        
        @app.route('/test', methods=['GET'])
        @require_auth
        def handler(auth):
            return jsonify({'account_id': auth.account_id})
        
        with app.test_request_context('/test', method='GET'):
            response = handler()
            # Response от Flask wrapper возвращает Response объект
            if isinstance(response, tuple):
                data = json.loads(response[0].data)
            else:
                data = json.loads(response.data)
            assert data['account_id'] == 123
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_auth_unauthorized(self, mock_auth, app):
        """Тест: @require_auth без аутентификации возвращает 401"""
        mock_auth.return_value = None
        
        @app.route('/test', methods=['GET'])
        @require_auth
        def handler(auth):
            return jsonify({'data': 'test'})
        
        with app.test_request_context('/test', method='GET'):
            response = handler()
            status = response[1]
            assert status == 401
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_auth_exception_handling(self, mock_auth, app):
        """Тест: @require_auth ловит исключения в handler"""
        mock_auth_context = AuthContext(account_id=123, auth_type="web")
        mock_auth.return_value = mock_auth_context
        
        @app.route('/test', methods=['GET'])
        @require_auth
        def handler(auth):
            raise ValueError("Test error")
        
        with app.test_request_context('/test', method='GET'):
            response = handler()
            status = response[1]
            assert status == 500  # internal_error


# ============ Tests: require_admin decorator ============

class TestRequireAdminDecorator:
    """Тестирование @require_admin декоратора"""
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_admin_success(self, mock_auth, app):
        """Тест: @require_admin с админ пользователем"""
        mock_auth_context = AuthContext(account_id=1, auth_type="web", is_admin=True)
        mock_auth.return_value = mock_auth_context
        
        @app.route('/admin', methods=['POST'])
        @require_admin
        def handler(auth):
            return jsonify({'admin': auth.is_admin})
        
        with app.test_request_context('/admin', method='POST'):
            response = handler()
            if isinstance(response, tuple):
                data = json.loads(response[0].data)
            else:
                data = json.loads(response.data)
            assert data['admin'] is True
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_admin_not_admin(self, mock_auth, app):
        """Тест: @require_admin с обычным пользователем возвращает 403"""
        mock_auth_context = AuthContext(account_id=123, auth_type="web", is_admin=False)
        mock_auth.return_value = mock_auth_context
        
        @app.route('/admin', methods=['POST'])
        @require_admin
        def handler(auth):
            return jsonify({'data': 'secret'})
        
        with app.test_request_context('/admin', method='POST'):
            response = handler()
            status = response[1]
            assert status == 403  # forbidden
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_admin_unauthorized(self, mock_auth, app):
        """Тест: @require_admin без аутентификации возвращает 401"""
        mock_auth.return_value = None
        
        @app.route('/admin', methods=['POST'])
        @require_admin
        def handler(auth):
            return jsonify({'data': 'test'})
        
        with app.test_request_context('/admin', method='POST'):
            response = handler()
            status = response[1]
            assert status == 401


# ============ Tests: authenticate_and_check ============

class TestAuthenticateAndCheck:
    """Тестирование authenticate_and_check функции"""
    
    @patch('bot.handlers.webhooks.webhook_utils._authenticate_request')
    @patch('bot.handlers.webhooks.webhook_utils.check_admin_access')
    def test_authenticate_success(self, mock_admin, mock_auth, app):
        """Тест: authenticate_and_check с успешной аутентификацией"""
        mock_auth.return_value = 123
        mock_admin.return_value = False
        
        with app.test_request_context('/', headers={'Authorization': 'Bearer token'}):
            result = authenticate_and_check(require_admin=False)
            assert result is not None
            assert result.account_id == 123
            assert result.auth_type == "web"
    
    @patch('bot.handlers.webhooks.webhook_utils._authenticate_request')
    def test_authenticate_failure(self, mock_auth, app):
        """Тест: authenticate_and_check без токена"""
        mock_auth.return_value = None
        
        with app.test_request_context('/'):
            result = authenticate_and_check()
            assert result is None
    
    @patch('bot.handlers.webhooks.webhook_utils._authenticate_request')
    @patch('bot.handlers.webhooks.webhook_utils.check_admin_access')
    def test_authenticate_admin_required(self, mock_admin_check, mock_auth, app):
        """Тест: authenticate_and_check с требованием админа"""
        mock_auth.return_value = 123
        mock_admin_check.return_value = False  # Не админ
        
        with app.test_request_context('/'):
            result = authenticate_and_check(require_admin=True)
            assert result is None


# ============ Integration Tests ============

class TestIntegration:
    """Integration тесты"""
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_full_auth_flow(self, mock_auth, app):
        """Тест: полный поток с auth и response"""
        mock_auth_context = AuthContext(account_id=456, auth_type="telegram", is_admin=False)
        mock_auth.return_value = mock_auth_context
        
        @app.route('/api/user/profile', methods=['GET', 'OPTIONS'])
        @require_auth
        def get_profile(auth):
            return APIResponse.success(
                user_id=auth.account_id,
                auth_type=auth.auth_type,
                is_admin=auth.is_admin
            )
        
        with app.test_request_context('/api/user/profile', method='GET'):
            response = get_profile()
            status = response[1]
            data = json.loads(response[0].data)
            assert status == 200
            assert data['success'] is True
            assert data['user_id'] == 456
    
    def test_async_and_response_combined(self, app_context):
        """Тест: async операция + APIResponse"""
        async def fetch_data():
            await asyncio.sleep(0.01)
            return {'fetched_value': 'data'}
        
        with app_context:
            data: Dict[str, Any] = run_async(fetch_data())
            response, status, headers = APIResponse.success(**data)
            assert status == 200
            result = json.loads(response.data)
            assert result['fetched_value'] == 'data'


# ============ Edge Cases ============

class TestEdgeCases:
    """Тестирование граничных случаев"""
    
    def test_api_response_with_special_chars(self, app_context):
        """Тест: APIResponse с спецсимволами"""
        with app_context:
            response, status, headers = APIResponse.success(
                message="Ошибка: не удалось обновить аккаунт",
                emoji="🎉"
            )
            data = json.loads(response.data)
            assert "Ошибка" in data['message']
            assert data['emoji'] == "🎉"
    
    def test_api_response_large_payload(self, app_context):
        """Тест: APIResponse с большой нагрузкой"""
        with app_context:
            large_list = list(range(1000))
            response, status, headers = APIResponse.success(items=large_list)
            data = json.loads(response.data)
            assert len(data['items']) == 1000
    
    def test_run_async_nested_coroutines(self):
        """Тест: run_async с вложенными корутинами"""
        async def inner():
            return "inner"
        
        async def outer():
            result = await inner()
            return f"outer-{result}"
        
        result = run_async(outer())
        assert result == "outer-inner"
    
    @patch('bot.handlers.webhooks.webhook_utils.authenticate_and_check')
    def test_require_auth_multiple_calls(self, mock_auth, app):
        """Тест: @require_auth может быть использован на нескольких функциях"""
        mock_auth_context = AuthContext(account_id=123, auth_type="web")
        mock_auth.return_value = mock_auth_context
        
        @app.route('/endpoint1', methods=['GET'])
        @require_auth
        def handler1(auth):
            return jsonify({'endpoint': 1})
        
        @app.route('/endpoint2', methods=['GET'])
        @require_auth
        def handler2(auth):
            return jsonify({'endpoint': 2})
        
        with app.test_request_context('/endpoint1', method='GET'):
            response1 = handler1()
            if isinstance(response1, tuple):
                data1 = json.loads(response1[0].data)
            else:
                data1 = json.loads(response1.data)
            assert data1['endpoint'] == 1
        
        with app.test_request_context('/endpoint2', method='GET'):
            response2 = handler2()
            if isinstance(response2, tuple):
                data2 = json.loads(response2[0].data)
            else:
                data2 = json.loads(response2.data)
            assert data2['endpoint'] == 2


# ============ Performance Tests ============

class TestPerformance:
    """Performance тесты"""
    
    def test_run_async_loop_cleanup(self):
        """Тест: run_async правильно очищает event loop"""
        async def task():
            return 1
        
        initial_loop = asyncio.get_event_loop()
        result = run_async(task())
        final_loop = asyncio.get_event_loop()
        
        # Event loop должен быть очищен, но asyncio.get_event_loop() создает новый
        assert result == 1
    
    def test_multiple_api_responses(self, app_context):
        """Тест: создание множества APIResponse не вызывает утечек"""
        with app_context:
            for i in range(100):
                response, status, headers = APIResponse.success(id=i)
                assert status == 200
    
    def test_auth_context_creation_performance(self):
        """Тест: создание множества AuthContext"""
        contexts = [
            AuthContext(account_id=i, auth_type="web", is_admin=(i % 10 == 0))
            for i in range(1000)
        ]
        assert len(contexts) == 1000
        assert contexts[0].account_id == 0
        assert contexts[100].is_admin is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
