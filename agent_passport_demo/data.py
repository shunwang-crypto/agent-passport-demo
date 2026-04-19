from __future__ import annotations

from .file_store import FileStore
from .models import now_utc
from .storage import DemoDatabase


class DemoDataStore:
    def __init__(self, database: DemoDatabase, *, file_store: FileStore | None = None) -> None:
        self.database = database
        self.file_store = file_store

    def read_document(self, resource: str) -> str:
        record = self.read_document_record(resource)
        return str(record["content"])

    def read_document_record(self, resource: str) -> dict[str, str]:
        row = self.database.fetch_one(
            """
            SELECT resource_type, content
            FROM resources
            WHERE resource_id = ?
              AND resource_type IN ('document', 'sheet', 'dataset')
            """,
            (resource,),
        )
        if row is None:
            raise KeyError(resource)

        resource_type = str(row["resource_type"])
        default_content = str(row["content"])
        mapped_file_path = ""
        if self.file_store is not None:
            mapped_file_path = self.file_store.file_path_for(resource) or ""

        if resource_type in {"document", "dataset"} and self.file_store is not None:
            file_payload = self.file_store.read_document(resource)
            if file_payload is not None:
                return {
                    "resource": resource,
                    "resource_type": resource_type,
                    "content": str(file_payload["content"]),
                    "source": "real_file",
                    "file_path": str(file_payload.get("file_path", "")),
                }
            raise FileNotFoundError(resource)

        return {
            "resource": resource,
            "resource_type": resource_type,
            "content": default_content,
            "source": "seed_data",
            "file_path": mapped_file_path,
        }

    def send_message(self, task_id: str, target: str, content: str) -> dict[str, str]:
        created_at = now_utc().isoformat(timespec="seconds")
        self.database.execute(
            """
            INSERT INTO outbound_messages (created_at, task_id, target, content)
            VALUES (?, ?, ?, ?)
            """,
            (created_at, task_id, target, content),
        )
        return {
            "created_at": created_at,
            "task_id": task_id,
            "target": target,
            "content": content,
        }

    def export_resources(self) -> list[dict[str, str]]:
        rows = self.database.fetch_all(
            """
            SELECT
                resource_id,
                resource_type,
                project,
                sensitivity,
                owner,
                description,
                allowed_actions
            FROM resources
            ORDER BY
                CASE sensitivity
                    WHEN 'secret' THEN 1
                    WHEN 'restricted' THEN 2
                    WHEN 'internal' THEN 3
                    ELSE 4
                END,
                resource_type,
                resource_id
            """
        )
        return [
            {
                "resource_id": str(row["resource_id"]),
                "resource_type": str(row["resource_type"]),
                "project": str(row["project"]),
                "sensitivity": str(row["sensitivity"]),
                "owner": str(row["owner"]),
                "description": str(row["description"]),
                "allowed_actions": str(row["allowed_actions"]),
                "file_path": (
                    ""
                    if self.file_store is None
                    else str(self.file_store.file_path_for(str(row["resource_id"])) or "")
                ),
            }
            for row in rows
        ]

    @property
    def sent_messages(self) -> list[dict[str, str]]:
        rows = self.database.fetch_all(
            """
            SELECT created_at, task_id, target, content
            FROM outbound_messages
            ORDER BY message_id DESC
            """
        )
        return [
            {
                "created_at": str(row["created_at"]),
                "task_id": str(row["task_id"] or ""),
                "target": str(row["target"]),
                "content": str(row["content"]),
            }
            for row in rows
        ]
