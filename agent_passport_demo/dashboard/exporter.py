from __future__ import annotations

import html
import json
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

from ..agents import ScenarioResult
from ..models import now_utc


class DashboardExporterMixin:
    def _latest_artifact(self, *, prefer_benchmark: bool = False) -> Path | None:
        if prefer_benchmark:
            if getattr(self, "latest_benchmark_artifact_zip", None) is not None and self.latest_benchmark_artifact_zip.is_file():
                return self.latest_benchmark_artifact_zip
        else:
            if getattr(self, "latest_scenario_artifact_zip", None) is not None and self.latest_scenario_artifact_zip.is_file():
                return self.latest_scenario_artifact_zip
        if self.latest_artifact_zip is not None and self.latest_artifact_zip.is_file():
            return self.latest_artifact_zip
        return None

    def _artifact_download_html(self, latest_artifact: Path | None) -> str:
        if latest_artifact is None:
            return "<span class='artifact-disabled'>运行任务后会生成最新归档文件</span>"
        href = f"/artifacts/{quote(latest_artifact.name)}"
        return f"<a class='artifact-link' href='{html.escape(href, quote=True)}' download>下载最新归档</a>"

    def _write_artifact_bundle(
        self,
        *,
        bundle_name: str,
        json_files: dict[str, object],
        text_files: dict[str, str] | None = None,
    ) -> Path:
        bundle_dir = self.artifacts_dir / bundle_name
        zip_path = self.artifacts_dir / f"{bundle_name}.zip"
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        for relative_path, payload in json_files.items():
            target = bundle_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative_path.endswith(".jsonl") and isinstance(payload, list):
                target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in payload), encoding="utf-8")
            else:
                target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        for relative_path, content in (text_files or {}).items():
            target = bundle_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in bundle_dir.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, arcname=f"{bundle_name}/{file_path.relative_to(bundle_dir)}")
        self.latest_artifact_zip = zip_path
        return zip_path

    def _export_task_artifact(
        self,
        *,
        scenario_name: str,
        task_id: str,
        started_at: str,
        finished_at: str,
        result: ScenarioResult,
        real_collaboration_payload: dict[str, object] | None = None,
        mark_latest: bool = True,
    ) -> Path:
        audit_rows = self.audit_ledger.events(task_id=task_id, include_internal=True)
        delegations = [row for row in self.delegation_manager.export() if str(row["task_id"]) == task_id]
        messages = [row for row in self.data_store.sent_messages if str(row.get("task_id", "")) == task_id]
        runtime_status = self.assistant_agent.planner_status()

        summary = {
            "artifact_type": "scenario_run",
            "scenario": scenario_name,
            "task_id": task_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": result.status,
            "title": result.title,
            "detail": result.detail,
            "reason_code": result.reason_code,
            "audit_event_count": len(audit_rows),
            "delegation_count": len(delegations),
            "message_count": len(messages),
            "runtime_model": runtime_status,
            "real_collaboration": real_collaboration_payload if isinstance(real_collaboration_payload, dict) else None,
        }
        text_summary = "\n".join(
            [
                f"场景：{self._scenario_label(scenario_name)}",
                f"任务：{task_id}",
                f"状态：{self._status_label(result.status)}",
                f"结论：{result.title}",
                f"说明：{result.detail}",
                f"原因代码：{result.reason_code or '-'}",
                f"审计事件：{len(audit_rows)}",
                f"委托数量：{len(delegations)}",
                f"消息数量：{len(messages)}",
            ]
        )
        bundle_name = f"scenario_{scenario_name}_{task_id}"
        archive = self._write_artifact_bundle(
            bundle_name=bundle_name,
            json_files={
                "summary.json": summary,
                "audit.json": audit_rows,
                "audit.jsonl": audit_rows,
                "delegations.json": delegations,
                "messages.json": messages,
            },
            text_files={"summary.md": text_summary},
        )
        if mark_latest:
            self.latest_scenario_artifact_zip = archive
        return archive

    def _export_benchmark_artifact(self, report: dict[str, object]) -> Path:
        timestamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        summary = {
            "artifact_type": "benchmark_run",
            "generated_at": report["latest_run_at"],
            "total": report["total"],
            "passed_count": report["passed_count"],
            "failed_count": report["failed_count"],
            "pass_rate": report["pass_rate"],
            "blocked_count": report["blocked_count"],
            "blocked_rate": report["blocked_rate"],
            "runtime_model": self.assistant_agent.planner_status(),
        }
        text_summary = "\n".join(
            [
                "批量安全评测结果",
                f"生成时间：{report['latest_run_at']}",
                f"总用例：{report['total']}",
                f"符合预期：{report['passed_count']}",
                f"失败用例：{report['failed_count']}",
                f"通过率：{report['pass_rate']}",
                f"拦截率：{report['blocked_rate']}",
            ]
        )
        archive = self._write_artifact_bundle(
            bundle_name=f"benchmark_{timestamp}",
            json_files={
                "summary.json": summary,
                "benchmark_rows.json": list(report["rows"]),
                "audit.json": self.audit_ledger.events(include_internal=True),
                "audit.jsonl": self.audit_ledger.events(include_internal=True),
                "delegations.json": self.delegation_manager.export(),
                "messages.json": self.data_store.sent_messages,
                "run_history.json": self.run_history,
            },
            text_files={"summary.md": text_summary},
        )
        self.latest_benchmark_artifact_zip = archive
        return archive
