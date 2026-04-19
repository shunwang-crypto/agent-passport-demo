from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import html
import json
from types import SimpleNamespace

from ..benchmark import DEFAULT_BENCHMARK_CASES


class DashboardViewMixin:
    def render_dashboard(
        self,
        view: str = "overview",
        filters: dict[str, str] | None = None,
    ) -> str:
        current_view = self.frontend.sanitize_view(view)
        filter_state = self._normalize_filters(filters or {})
        benchmark_report = self._benchmark_report()
        result = self._display_result_for_view(current_view=current_view, benchmark_report=benchmark_report)
        payload = self._payload_for_result(result)
        delegations = self.delegation_manager.export()
        latest_artifact = self._latest_artifact(prefer_benchmark=current_view == "benchmark")
        filtered_audit = self._filtered_audit_rows(current_view=current_view, filter_state=filter_state)

        runtime_status = self.assistant_agent.planner_status()
        summary_cards_html = self._top_summary_cards(
            result=result,
            benchmark_report=benchmark_report,
            delegations=delegations,
            audit_rows=filtered_audit,
        )

        context = {
            "real_collaboration_button_hint": html.escape(self._real_collaboration_button_hint(runtime_status)),
            "summary_cards": summary_cards_html,
            "last_status_label": html.escape(self._status_label(result.status if result else "idle")),
            "last_status_class": self._status_class(result.status if result else "idle"),
            "last_title": html.escape(result.title if result else "尚未运行任务"),
            "last_detail": html.escape(result.detail if result else "点击“真实协作”运行当前办公任务。"),
            "last_meta_line": html.escape(self._last_meta_line(result, benchmark_report)),
            "artifact_download_html": self._artifact_download_html(latest_artifact),
        }

        context.update(
            self._view_context(
                current_view=current_view,
                payload=payload,
                result=result,
                benchmark_report=benchmark_report,
                filter_state=filter_state,
                filtered_audit=filtered_audit,
                delegations=delegations,
            )
        )
        return self.frontend.render_page(current_view=current_view, context=context)

    def _view_context(
        self,
        *,
        current_view: str,
        payload: dict[str, object],
        result,
        benchmark_report: dict[str, object],
        filter_state: dict[str, str],
        filtered_audit: list[dict[str, object]],
        delegations: list[dict[str, object]],
    ) -> dict[str, str]:
        if current_view == "overview":
            return self._overview_context(payload=payload, result=result)
        if current_view == "graph":
            return self._graph_context(payload=payload, result=result)
        if current_view == "token":
            return self._token_context(delegations=delegations)
        if current_view == "benchmark":
            return self._benchmark_context(benchmark_report=benchmark_report)
        if current_view == "details":
            return self._details_context(filter_state=filter_state, filtered_audit=filtered_audit)
        if current_view == "decision":
            return self._decision_context()
        return {}

    def _overview_context(self, *, payload: dict[str, object], result) -> dict[str, str]:
        return {
            "overview_capability_cards": self._overview_capability_cards(),
            "task_focus_summary": self._task_focus_summary(payload=payload, result=result),
            "agent_status_cards": self._agent_stage_cards(payload),
            "plan_summary_html": self._assistant_plan_summary(payload),
            "query_summary_html": self._query_result_summary(payload),
            "report_summary_html": self._report_result_summary(payload),
            "mail_summary_html": self._mail_result_summary(payload),
            "failure_panel": self._failure_panel(payload),
            "security_validation_cards": self._security_validation_cards(),
        }

    def _graph_context(self, *, payload: dict[str, object], result) -> dict[str, str]:
        resources = self.data_store.export_resources()
        policies = self.policy_store.export()
        task_id = str(payload.get("task_id", "")).strip() or (str(result.task_id) if result else "")
        return {
            "resource_rows": self._resource_rows(resources),
            "policy_rows": self._policy_rows(policies),
            "relationship_graph": self._relationship_graph(resources),
            "agent_scope_cards": self._agent_scope_cards(),
            "graph_runtime_hint": html.escape(
                f"当前任务 {task_id or '-'}；状态 {self._status_label(result.status if result else 'idle')}。"
            ),
        }

    def _token_context(self, *, delegations: list[dict[str, object]]) -> dict[str, str]:
        return {
            "token_summary_cards": self._token_summary_cards(delegations),
            "agent_identity_cards": self._agent_identity_cards(),
            "delegation_task_cards": self._delegation_task_cards(delegations),
            "delegation_rows": self._delegation_rows(delegations),
            "message_rows": self._message_rows(),
        }

    def _benchmark_context(self, *, benchmark_report: dict[str, object]) -> dict[str, str]:
        return {
            "benchmark_catalog_count": str(len(DEFAULT_BENCHMARK_CASES)),
            "benchmark_summary_cards": self._benchmark_summary_cards(benchmark_report),
            "benchmark_rows": self._benchmark_rows(list(benchmark_report.get("rows", []))),
            "benchmark_latest_run_at": html.escape(self._format_display_time(benchmark_report.get("latest_run_at", ""))),
        }

    def _details_context(
        self,
        *,
        filter_state: dict[str, str],
        filtered_audit: list[dict[str, object]],
    ) -> dict[str, str]:
        return {
            "audit_filter_links": self._audit_filter_links(filter_state),
            "current_filter_hint": html.escape(self._current_filter_hint(filter_state)),
            "audit_keyword": html.escape(filter_state.get("keyword", "")),
            "audit_task_query": html.escape(filter_state.get("task_id", "")),
            "audit_time_range_options": self._audit_time_range_options(filter_state.get("time_range", "all")),
            "audit_filter_task": html.escape(filter_state.get("task_id", "")),
            "audit_filter_agent": html.escape(filter_state.get("principal", "")),
            "audit_filter_decision": html.escape(filter_state.get("decision", "")),
            "audit_summary_cards": self._audit_summary_cards(filtered_audit),
            "audit_task_cards": self._audit_task_cards(filtered_audit),
            "audit_rows": self._audit_rows(filtered_audit),
            "timeline_items_full": self._timeline_items(filtered_audit),
            "run_history_cards": self._run_history_cards(),
        }

    def _decision_context(self) -> dict[str, str]:
        return {
            "decision_contract_cards": self._decision_contract_cards(),
            "decision_request_summary": self._decision_request_summary(
                self.last_authorization_request or self._decision_example_payload()
            ),
            "decision_response_summary": self._decision_response_summary(
                self.last_authorization_response
                or {
                    "decision": "pending",
                    "reason_text": "尚未执行授权接口验证。",
                    "reason": "",
                    "audited": False,
                }
            ),
            "decision_request_json": self._decision_request_json(),
            "decision_response_json": self._decision_response_json(),
            "decision_curl_command": self._decision_curl_command(),
        }

    def _filtered_audit_rows(
        self,
        *,
        current_view: str,
        filter_state: dict[str, str],
    ) -> list[dict[str, object]]:
        task_filter = filter_state["task_id"] or None
        principal_filter = filter_state["principal"] or None
        decision_filter = filter_state["decision"] or None

        rows = self.audit_ledger.events(
            task_id=task_filter,
            principal=principal_filter,
            decision=decision_filter,
        )
        return self._apply_local_audit_filters(
            rows,
            keyword=filter_state.get("keyword", ""),
            time_range=filter_state.get("time_range", "all"),
        )

    def _normalize_filters(self, filters: dict[str, str]) -> dict[str, str]:
        task_id = (filters.get("task") or "").strip()
        force_all = "1" if task_id == "all" else ""
        if task_id in {"all", "current"}:
            task_id = "" if task_id == "all" else (self._current_display_task_id() or "")

        principal = (filters.get("agent") or "").strip()
        decision = (filters.get("decision") or "").strip().lower()
        if decision not in {"allow", "deny"}:
            decision = ""

        keyword = (filters.get("keyword") or "").strip()
        time_range = (filters.get("time_range") or "all").strip().lower()
        if time_range not in {"1h", "24h", "all"}:
            time_range = "all"

        return {
            "task_id": task_id,
            "principal": principal,
            "decision": decision,
            "force_all": force_all,
            "keyword": keyword,
            "time_range": time_range,
        }

    def _apply_local_audit_filters(
        self,
        rows: list[dict[str, object]],
        *,
        keyword: str,
        time_range: str,
    ) -> list[dict[str, object]]:
        lowered_keyword = keyword.strip().lower()
        threshold = self._time_range_threshold(time_range)
        filtered: list[dict[str, object]] = []
        for row in rows:
            if threshold is not None:
                event_time = self._parse_event_timestamp(row.get("timestamp"))
                if event_time is None or event_time < threshold:
                    continue

            if lowered_keyword:
                haystack = " ".join(
                    [
                        str(row.get("task_id", "")),
                        str(row.get("principal", "")),
                        str(row.get("reason_code", "")),
                        str(row.get("reason_text", "")),
                        str(row.get("metadata", {}).get("summary", ""))
                        if isinstance(row.get("metadata"), dict)
                        else "",
                    ]
                ).lower()
                if lowered_keyword not in haystack:
                    continue

            filtered.append(row)
        return filtered

    def _time_range_threshold(self, time_range: str) -> datetime | None:
        now = datetime.now(tz=timezone.utc)
        if time_range == "1h":
            return now - timedelta(hours=1)
        if time_range == "24h":
            return now - timedelta(hours=24)
        return None

    def _parse_event_timestamp(self, value: object) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _display_result_for_view(self, *, current_view: str, benchmark_report: dict[str, object]):
        result = self.last_result
        if current_view == "benchmark":
            if result is not None and str(result.reason_code) == "benchmark_completed":
                return result
            total = int(benchmark_report.get("total", 0) or 0)
            if total > 0:
                rows = benchmark_report.get("rows") if isinstance(benchmark_report.get("rows"), list) else []
                task_id = str(rows[-1].get("task_id", "-")) if rows else "-"
                passed = int(benchmark_report.get("passed_count", 0) or 0)
                failed = int(benchmark_report.get("failed_count", 0) or 0)
                return SimpleNamespace(
                    status="success" if failed == 0 else "error",
                    title="批量安全评测完成",
                    detail=f"共执行 {total} 个用例，其中 {passed} 个符合预期。",
                    task_id=task_id,
                    reason_code="benchmark_completed",
                )
            return result

        if result is not None and str(result.reason_code) != "benchmark_completed":
            return result

        payload = self.last_real_collaboration if isinstance(self.last_real_collaboration, dict) else {}
        task_id = str(payload.get("task_id", "")).strip()
        if not task_id:
            return result
        return SimpleNamespace(
            status=str(payload.get("status", "idle")),
            title="真实办公协作结果",
            detail=str(payload.get("reason_text", "")) or "-",
            task_id=task_id,
            reason_code=str(payload.get("reason_code", "")),
        )

    def _payload_for_result(self, result) -> dict[str, object]:
        if isinstance(self._last_unified_payload, dict):
            payload_task = str(self._last_unified_payload.get("task_id", "")).strip()
            if result is None or payload_task == str(result.task_id).strip():
                return self._last_unified_payload
        payload = self.last_real_collaboration if isinstance(self.last_real_collaboration, dict) else {}
        return payload if payload else {}

    def _current_display_task_id(self) -> str | None:
        if self.last_result is not None and str(self.last_result.reason_code) != "benchmark_completed":
            task_id = str(self.last_result.task_id).strip()
            if task_id:
                return task_id
        if isinstance(self._last_unified_payload, dict):
            task_id = str(self._last_unified_payload.get("task_id", "")).strip()
            if task_id:
                return task_id
        if isinstance(self.last_real_collaboration, dict):
            task_id = str(self.last_real_collaboration.get("task_id", "")).strip()
            if task_id:
                return task_id
        return None

    def _real_collaboration_button_hint(self, status: dict[str, object]) -> str:
        if bool(status.get("enabled")):
            return ""
        return "在线模型未启用；真实办公链路会直接返回模型失败结果。"

    def _decision_example_payload(self) -> dict[str, object]:
        rows = self.delegation_manager.export(include_sensitive=True)
        active_row = next(
            (
                row
                for row in rows
                if not bool(row.get("revoked")) and int(row.get("uses", 0)) < int(row.get("max_uses", 0))
            ),
            None,
        )
        if active_row is not None:
            identity = self.agent_registry.get(str(active_row.get("to_principal", "")))
            return {
                "subject": {"type": "agent", "id": str(active_row.get("to_principal", ""))},
                "action": {"name": str(active_row.get("action", ""))},
                "resource": {"id": str(active_row.get("resource", ""))},
                "context": {
                    "task_id": str(active_row.get("task_id", "")),
                    "auth_token": "" if identity is None else identity.auth_token,
                    "capability_token": str(active_row.get("capability_token", "")),
                    "consume": False,
                    "audit_mode": "full",
                },
            }
        return {
            "subject": {"type": "agent", "id": "agent:data_query"},
            "action": {"name": "query"},
            "resource": {"id": "dataset:sales_week15"},
            "context": {
                "task_id": "task_demo",
                "auth_token": "<agent_auth_token>",
                "capability_token": "<signed_capability_token>",
                "consume": False,
                "audit_mode": "full",
            },
        }

    def _decision_request_json(self) -> str:
        payload = self.last_authorization_request or self._decision_example_payload()
        return self._json_pretty(self._mask_decision_payload(payload))

    def _decision_response_json(self) -> str:
        payload = self.last_authorization_response or {
            "decision": "pending",
            "reason_text": "尚未执行授权接口验证。",
        }
        return self._json_pretty(payload)

    def _decision_curl_command(self) -> str:
        payload = json.dumps(self._mask_decision_payload(self._decision_example_payload()), ensure_ascii=False)
        command = (
            "curl -X POST http://127.0.0.1:8000/api/authorize "
            '-H "Content-Type: application/json" '
            f"-d '{payload}'"
        )
        return html.escape(command)

    def _mask_decision_payload(self, payload: dict[str, object]) -> dict[str, object]:
        masked = deepcopy(payload)
        context = masked.get("context")
        if not isinstance(context, dict):
            return masked
        for field in ("auth_token", "capability_token"):
            value = context.get(field)
            if isinstance(value, str) and value:
                context[field] = self._mask_token(value)
        return masked

    def _mask_token(self, token: str) -> str:
        if len(token) <= 8:
            return token
        return f"{token[:4]}...{token[-4:]}"

    def _decision_contract_cards(self) -> str:
        cards = [
            ("输入结构", "请求提交执行主体、申请动作、目标资源和任务上下文。"),
            ("决策口径", "接口与真实协作链路复用同一套授权网关和拦截规则。"),
            ("审计级别", "支持 full、preview、off 三种审计写入方式。"),
        ]
        return "".join(
            "<article class='stack-card'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<p>{html.escape(detail)}</p>"
            "</article>"
            for title, detail in cards
        )
