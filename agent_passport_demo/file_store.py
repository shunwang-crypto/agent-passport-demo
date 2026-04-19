from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


DEFAULT_RESOURCE_FILE_MAP: dict[str, str] = {
    "dataset:sales_week15": "sales_week15.csv",
    "dataset:finance_sensitive": "finance_sensitive.csv",
}

DEFAULT_TASK_FILE_MAP: dict[str, str] = {
    "task:sales_report": "task_sales_report.md",
}


class FileStore:
    def __init__(
        self,
        docs_dir: Path,
        *,
        tasks_dir: Path | None = None,
        outputs_dir: Path | None = None,
        resource_map: dict[str, str] | None = None,
        task_map: dict[str, str] | None = None,
    ) -> None:
        self.docs_dir = docs_dir
        self.tasks_dir = tasks_dir or docs_dir.parent / "tasks"
        self.outputs_dir = outputs_dir or docs_dir.parent / "outputs"
        self.resource_map = dict(resource_map or DEFAULT_RESOURCE_FILE_MAP)
        self.task_map = dict(task_map or DEFAULT_TASK_FILE_MAP)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def file_path_for(self, resource_id: str) -> str | None:
        relative_name = self.resource_map.get(resource_id)
        if not relative_name:
            return None
        return str((self.docs_dir / relative_name).resolve())

    def read_document(self, resource_id: str) -> dict[str, str] | None:
        relative_name = self.resource_map.get(resource_id)
        if not relative_name:
            return None

        file_path = (self.docs_dir / relative_name).resolve()
        if not file_path.is_file():
            return None
        try:
            content = file_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not content:
            return None
        return {
            "resource_id": resource_id,
            "content": content,
            "source": "real_file",
            "file_path": str(file_path),
        }

    def task_path_for(self, task_id: str) -> str | None:
        relative_name = self.task_map.get(task_id)
        if not relative_name:
            return None
        return str((self.tasks_dir / relative_name).resolve())

    def read_task(self, task_id: str = "task:sales_report") -> dict[str, object] | None:
        relative_name = self.task_map.get(task_id)
        if not relative_name:
            return None

        file_path = (self.tasks_dir / relative_name).resolve()
        if not file_path.is_file():
            return None
        try:
            raw = file_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw:
            return None

        metadata: dict[str, object] = {}
        body_lines: list[str] = []
        in_metadata = True
        for line in raw.splitlines():
            if in_metadata:
                stripped = line.strip()
                if not stripped:
                    in_metadata = False
                    continue
                if stripped.startswith("#") or ":" not in line:
                    in_metadata = False
                    body_lines.append(line)
                    continue
                key, value = line.split(":", 1)
                metadata[key.strip().lstrip("\ufeff")] = value.strip()
                continue
            body_lines.append(line)

        metadata.setdefault("user_goal", "")
        metadata["task_file_path"] = str(file_path)
        metadata["task_body"] = "\n".join(body_lines).strip()

        for list_key in ("allowed_resources", "allowed_targets"):
            value = metadata.get(list_key, "")
            if isinstance(value, str):
                metadata[list_key] = [item.strip() for item in value.split(",") if item.strip()]

        return metadata

    def write_output(
        self,
        *,
        task_id: str,
        output_name: str,
        content: str,
    ) -> dict[str, str]:
        safe_name = self._safe_output_name(output_name, default_name=f"{task_id}_weekly_sales_report.md")
        task_safe_name = self._task_output_name(task_id=task_id, output_name=safe_name)
        file_path = (self.outputs_dir / task_safe_name).resolve()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = f"<!-- generated_at: {timestamp} -->\n{content.strip()}\n"
        file_path.write_text(payload, encoding="utf-8")

        latest_alias_path = (self.outputs_dir / safe_name).resolve()
        if latest_alias_path != file_path:
            latest_alias_path.write_text(payload, encoding="utf-8")

        return {
            "output_name": task_safe_name,
            "output_path": str(file_path),
            "latest_alias_path": str(latest_alias_path),
            "source": "real_output_file",
        }

    def _safe_output_name(self, value: str, *, default_name: str) -> str:
        candidate = value.strip() or default_name
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate)
        if not normalized:
            normalized = default_name
        if "." not in normalized:
            normalized += ".md"
        return normalized

    def _task_output_name(self, *, task_id: str, output_name: str) -> str:
        if output_name.startswith(f"{task_id}_"):
            return output_name
        return f"{task_id}_{output_name}"
