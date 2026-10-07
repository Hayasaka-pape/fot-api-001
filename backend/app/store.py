"""SQLite scene storage; a transaction survives interruption without partial JSON."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import NotFoundError
from .models import SceneInput


class SceneStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "scenes.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS scenes (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def list(self):
        with self.connect() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT data FROM scenes ORDER BY updated DESC, id")]

    def get(self, scene_id):
        with self.connect() as connection:
            row = connection.execute("SELECT data FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if row is None:
            raise NotFoundError("保存されたシーンが見つかりませんでした")
        return json.loads(row[0])

    def create(self, scene: SceneInput):
        # Client IDs are never used for inserts to avoid accidental overwrites.
        scene_id = str(uuid.uuid4())
        value = scene.model_dump(mode="json")
        value["id"] = scene_id
        with self.connect() as connection:
            connection.execute("INSERT INTO scenes (id,data) VALUES (?,?)", (scene_id, json.dumps(value, ensure_ascii=False)))
        return value

    def update(self, scene_id, scene: SceneInput):
        value = scene.model_dump(mode="json")
        value["id"] = scene_id
        with self.connect() as connection:
            changed = connection.execute("UPDATE scenes SET data=?, updated=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(value, ensure_ascii=False), scene_id)).rowcount
        if not changed:
            raise NotFoundError("保存されたシーンが見つかりませんでした")
        return value

    def delete(self, scene_id):
        with self.connect() as connection:
            changed = connection.execute("DELETE FROM scenes WHERE id=?", (scene_id,)).rowcount
        if not changed:
            raise NotFoundError("保存されたシーンが見つかりませんでした")
