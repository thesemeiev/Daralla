"""
Quart Blueprint: /, /index.html, /<path:filename> (webapp and static files).
"""
import logging
import os
from pathlib import Path

from quart import Blueprint, Response, redirect

logger = logging.getLogger(__name__)

bp = Blueprint("static", __name__)


def _set_no_cache_headers(resp: Response) -> Response:
    """Disable browser/proxy cache for HTML entrypoints."""
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _webapp_base_dir():
    """Project root (where apps/backend and apps/frontend live)."""
    # __file__ = .../apps/backend/src/daralla_backend/web/routes/static.py
    return Path(__file__).resolve().parents[6]


@bp.route("/", methods=["GET"])
@bp.route("/index.html", methods=["GET"])
async def root_index():
    """Отдает HTML страницу веб-приложения с корня."""
    try:
        base_dir = _webapp_base_dir()
        webapp_path = base_dir / "apps" / "frontend" / "webapp" / "index.html"
        if webapp_path.exists():
            with webapp_path.open("rb") as f:
                body = f.read()
            resp = Response(
                body,
                status=200,
                content_type="text/html; charset=utf-8",
            )
            return _set_no_cache_headers(resp)
        logger.warning("Web app not found at: %s", webapp_path)
        return Response("Web app not found", status=404, mimetype="text/plain")
    except Exception as e:
        logger.error("Ошибка при загрузке webapp: %s", e, exc_info=True)
        return Response("Error loading web app", status=500, mimetype="text/plain")


def _read_webapp_file(relative_path: str):
    base_dir = _webapp_base_dir()
    webapp_dir = base_dir / "apps" / "frontend" / "webapp"
    file_path = (webapp_dir / relative_path).resolve()
    webapp_dir_abs = webapp_dir.resolve()
    if webapp_dir_abs not in file_path.parents and file_path != webapp_dir_abs:
        return None, 403
    if not file_path.exists() or not file_path.is_file():
        return None, 404
    with file_path.open("rb") as f:
        return f.read(), 200


@bp.route("/privacy", methods=["GET"])
async def privacy_page():
    body, status = _read_webapp_file("legal/privacy.html")
    if status != 200:
        return ("File not found", 404) if status == 404 else ("Forbidden", status)
    return _set_no_cache_headers(
        Response(body, status=200, content_type="text/html; charset=utf-8")
    )


@bp.route("/terms", methods=["GET"])
async def terms_page():
    body, status = _read_webapp_file("legal/terms.html")
    if status != 200:
        return ("File not found", 404) if status == 404 else ("Forbidden", status)
    return _set_no_cache_headers(
        Response(body, status=200, content_type="text/html; charset=utf-8")
    )


@bp.route("/support", methods=["GET"])
async def support_redirect():
    """Единая точка входа в поддержку из веба/Mini App."""
    support_url = (os.getenv("SUPPORT_URL") or "https://t.me/DarallaSupport").strip()
    if not support_url:
        support_url = "https://t.me/DarallaSupport"
    return redirect(support_url, code=302)


@bp.route("/<path:filename>", methods=["GET"])
async def root_static(filename):
    """Отдает статические файлы веб-приложения (style.css, app.js, ...)."""
    try:
        body, status = _read_webapp_file(filename)
        if status == 403:
            logger.warning("Forbidden file access attempt: %s", filename)
            return "Forbidden", 403
        if status == 200:
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
            return Response(body, status=200, content_type=content_type)
        return "File not found", 404
    except Exception as e:
        logger.error("Ошибка при загрузке статического файла: %s", e)
        return "Error loading file", 500
