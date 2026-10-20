"""ASGI-точка входа демо-режима: API и собранный SPA на одном порту.

Демо-стенд для заказчика работает одним процессом uvicorn на порту 3000
(его пробрасывает роутер), без nginx и без webpack dev server:

    uvicorn serve_demo:app --host 0.0.0.0 --port 3000

Тот же самый FastAPI-app из app.main — роуты /api/* и /media/* остаются
как есть; поверх них монтируется собранный mindcare_web/build. Mount на "/"
добавляется последним, поэтому API-роуты, объявленные раньше, имеют приоритет.

Для отладки этот модуль не нужен: там по-прежнему CRA (:3000) + uvicorn
app.main:app --reload (:8000). Режимы взаимоисключающие, переключение —
scripts/mindcare-mode.sh.
"""
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from app.main import app

_BUILD_DIR = Path(__file__).resolve().parent.parent / "mindcare_web" / "build"


class SPAStaticFiles(StaticFiles):
    """StaticFiles с SPA-fallback: неизвестный путь отдаёт index.html.

    React Router обслуживает /student/diary, /admin/users и т.п. на клиенте —
    без fallback прямой заход по такой ссылке или F5 давали бы 404.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


if not (_BUILD_DIR / "index.html").is_file():
    raise RuntimeError(
        f"Нет сборки фронтенда: {_BUILD_DIR}/index.html. "
        "Сначала выполните: cd mindcare_web && npm run build"
    )

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/", SPAStaticFiles(directory=str(_BUILD_DIR), html=True), name="spa")
