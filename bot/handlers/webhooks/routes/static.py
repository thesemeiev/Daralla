"""
Blueprint: /, /index.html, /<path:filename> (webapp and static files).
"""
import os
import logging
from flask import Blueprint

logger = logging.getLogger(__name__)

bp = Blueprint('static', __name__)


def get_webapp_base_dir():
    """Project root (parent of bot/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


@bp.route('/', methods=['GET'])
@bp.route('/index.html', methods=['GET'])
def root_index():
    """Отдает HTML страницу веб-приложения с корня"""
    try:
        base_dir = get_webapp_base_dir()
        webapp_path = os.path.join(base_dir, 'webapp', 'index.html')
        if os.path.exists(webapp_path):
            with open(webapp_path, 'r', encoding='utf-8') as f:
                return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
        logger.warning(f"Web app not found at: {webapp_path}")
        return "Web app not found", 404
    except Exception as e:
        logger.error(f"Ошибка при загрузке webapp: {e}", exc_info=True)
        return "Error loading web app", 500


@bp.route('/<path:filename>', methods=['GET'])
def root_static(filename):
    """Отдает статические файлы веб-приложения с корня (style.css, app.js, ...)"""
    try:
        base_dir = get_webapp_base_dir()
        webapp_dir = os.path.join(base_dir, 'webapp')
        file_path = os.path.join(webapp_dir, filename)
        webapp_dir_abs = os.path.abspath(webapp_dir)
        file_path_abs = os.path.abspath(file_path)
        if not file_path_abs.startswith(webapp_dir_abs):
            logger.warning(f"Forbidden file access attempt: {file_path}")
            return "Forbidden", 403
        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = 'text/plain'
            if filename.endswith('.css'):
                content_type = 'text/css'
            elif filename.endswith('.js'):
                content_type = 'application/javascript'
            elif filename.endswith('.json'):
                content_type = 'application/json'
            elif filename.endswith('.png'):
                content_type = 'image/png'
            elif filename.endswith('.ico'):
                content_type = 'image/x-icon'
            elif filename.endswith('.html'):
                content_type = 'text/html; charset=utf-8'
            with open(file_path, 'rb') as f:
                return f.read(), 200, {'Content-Type': content_type}
        return "File not found", 404
    except Exception as e:
        logger.error(f"Ошибка при загрузке статического файла: {e}")
        return "Error loading file", 500
