import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .client import FotmobClient
from .demo import demo_response
from .errors import FotmobError, InvalidResponseError
from .export import make_export
from .models import Query, SceneInput
from .normalizers import normalize
from .store import SceneStore


def create_app(*, data_dir=None, client=None, frontend_dist=None):
    app = FastAPI(title="Fot API 001", version="1.0.0", description="サッカー同時視聴配信用データ・OBS シーン API")
    app.state.client = client or FotmobClient()
    app.state.store = SceneStore(data_dir or os.getenv("DATA_DIR", "data"))
    dist = Path(frontend_dist or os.getenv("FRONTEND_DIST", "../frontend/dist")).resolve()
    # Same-origin by default. Dev origins must be explicitly configured.
    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip() and origin.strip() != "*"]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])

    @app.exception_handler(FotmobError)
    async def handle_fotmob_error(request, error):
        body = {"code": error.code, "message": str(error)}
        headers = {}
        if error.retry_after:
            body["retryAfter"] = error.retry_after
            headers["Retry-After"] = error.retry_after
        return JSONResponse({"error": body}, status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request, error):
        messages = []
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"] if part != "body")
            messages.append(f"{location}: {item['msg']}" if location else item["msg"])
        return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": " / ".join(messages)}}, status_code=422)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request, error):
        return JSONResponse({"error": {"code": "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR", "message": str(error.detail)}}, status_code=error.status_code)

    @app.exception_handler(sqlite3.Error)
    async def handle_storage_error(request, error):
        return JSONResponse({"error": {"code": "STORAGE_ERROR", "message": "シーンの保存に失敗しました。データディレクトリの空き容量・権限を確認してください"}}, status_code=500)

    async def query_data(query):
        if query.mode == "demo":
            return demo_response(query)
        raw, fetched_at = await app.state.client.fetch(query)
        try:
            modules, warnings, unavailable = normalize(raw, query)
        except (TypeError, AttributeError, KeyError, ValueError):
            raise InvalidResponseError("FotMob のデータ構造が変更されています。時間をおいて再取得してください")
        # Only selected information is exposed in an explicitly filtered response.
        selected_raw = {"selected": modules} if query.sections is not None else raw
        return {"source": "fotmob", "fetchedAt": fetched_at, "kind": query.kind, "modules": modules,
                "raw": selected_raw, "warnings": warnings, "unavailable": unavailable}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "1.0.0", "upstream": "FotMob (非公式)", "demoAvailable": True}

    @app.post("/api/query")
    async def query(query: Query):
        return await query_data(query)

    @app.get("/api/scenes")
    async def list_scenes():
        return app.state.store.list()

    @app.post("/api/scenes", status_code=201)
    async def create_scene(scene: SceneInput):
        return app.state.store.create(scene)

    @app.get("/api/scenes/{scene_id}")
    async def get_scene(scene_id: str):
        return app.state.store.get(scene_id)

    @app.put("/api/scenes/{scene_id}")
    async def update_scene(scene_id: str, scene: SceneInput):
        return app.state.store.update(scene_id, scene)

    @app.delete("/api/scenes/{scene_id}", status_code=204)
    async def delete_scene(scene_id: str):
        app.state.store.delete(scene_id)
        return Response(status_code=204)

    async def scene_data(scene_id):
        scene = app.state.store.get(scene_id)
        query = Query.model_validate({**scene["query"], "sections": scene["sections"]})
        return scene, await query_data(query)

    @app.get("/api/scenes/{scene_id}/data")
    async def get_scene_data(scene_id: str):
        _, data = await scene_data(scene_id)
        return data

    @app.get("/api/scenes/{scene_id}/export")
    async def export_scene(scene_id: str, request: Request, connected: bool = False):
        scene, data = await scene_data(scene_id)
        connected_url = str(request.url_for("get_scene_data", scene_id=scene_id)) if connected else None
        return Response(make_export(scene, data, connected_url, dist), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="fot-api-{scene_id}.zip"'})

    @app.get("/{file_path:path}", include_in_schema=False)
    async def frontend(file_path: str):
        if file_path.startswith("api/"):
            raise HTTPException(404, "API が見つかりませんでした")
        target = (dist / file_path).resolve()
        if target.is_relative_to(dist) and target.is_file():
            return FileResponse(target)
        index = dist / "index.html"
        if index.is_file() and (not file_path or file_path.startswith("overlay/")):
            return FileResponse(index)
        raise HTTPException(404, "フロントエンドが未ビルド、またはページが見つかりませんでした")

    return app


app = create_app()
