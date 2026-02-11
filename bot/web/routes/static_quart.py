"""
Quart Blueprint: /, /index.html, /<path:filename> (webapp and static files).
"""
import os
import logging

from quart import Blueprint, Response

logger = logging.getLogger(__name__)

bp = Blueprint("static", __name__)


def _webapp_base_dir():
    """Project root: parent of bot/ (в Docker /app, локально — корень репозитория)."""
    # __file__ = .../bot/web/routes/static_quart.py → 4 уровня вверх = корень (где лежат bot/ и webapp/)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@bp.route("/", methods=["GET"])
@bp.route("/index.html", methods=["GET"])
async def root_index():
    """Отдает HTML страницу веб-приложения с корня."""
    try:
        base_dir = _webapp_base_dir()
        webapp_path = os.path.join(base_dir, "webapp", "index.html")
        if os.path.exists(webapp_path):
            with open(webapp_path, "rb") as f:
                body = f.read()
            return Response(
                body,
                status=200,
                mimetype="text/html",
                charset="utf-8",
            )
        logger.warning("Web app not found at: %s", webapp_path)
        return Response("Web app not found", status=404, mimetype="text/plain")
    except Exception as e:
        logger.error("Ошибка при загрузке webapp: %s", e, exc_info=True)
        return Response("Error loading web app", status=500, mimetype="text/plain")


@bp.route("/<path:filename>", methods=["GET"])
async def root_static(filename):
    """Отдает статические файлы веб-приложения (style.css, app.js, ...)."""
    try:
        base_dir = _webapp_base_dir()
        webapp_dir = os.path.join(base_dir, "webapp")
        file_path = os.path.join(webapp_dir, filename)
        webapp_dir_abs = os.path.abspath(webapp_dir)
        file_path_abs = os.path.abspath(file_path)
        if not file_path_abs.startswith(webapp_dir_abs):
            logger.warning("Forbidden file access attempt: %s", file_path)
            return "Forbidden", 403
        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = "text/plain"
            if filename.endswith(".css"):
                content_type = "text/css"
            elif filename.endswith(".js"):
                content_type = "application/javascript"
            elif filename.endswith(".json"):
                content_type = "application/json"
            elif filename.endswith(".png"):
                content_type = "image/png"
            elif filename.endswith(".ico"):
                content_type = "image/x-icon"
            elif filename.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            with open(file_path, "rb") as f:
                body = f.read()
            return Response(body, status=200, content_type=content_type)
        return "File not found", 404
    except Exception as e:
        logger.error("Ошибка при загрузке статического файла: %s", e)
        return "Error loading file", 500
