from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .data import DemoDataStore
from .gateway import AuthorizationGateway
from .llm_client import AgentLLMClient
from .models import AgentIdentity


@dataclass
class ScenarioResult:
    status: str
    title: str
    detail: str
    task_id: str
    reason_code: str = ""


class DataQueryAgent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        gateway: AuthorizationGateway,
        data_store: DemoDataStore,
        llm_client: AgentLLMClient,
    ) -> None:
        self.identity = identity
        self.gateway = gateway
        self.data_store = data_store
        self.llm_client = llm_client

    def prepare_query_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        expected_resource = str(assistant_plan.get("dataset_resource", "")).strip()
        effective_plan = self._with_query_defaults(user_goal=user_goal, assistant_plan=assistant_plan)

        payload, meta = self.llm_client.data_query_request(
            user_goal=user_goal,
            assistant_plan=effective_plan,
        )
        if meta.get("error"):
            return {}, meta

        normalized, validation_error = self._normalize_query_request_payload(
            payload,
            expected_resource=expected_resource,
        )
        if normalized is not None:
            return normalized, meta

        first_error = str(payload.get("error", validation_error)).strip() or validation_error
        retry_plan = dict(effective_plan)
        retry_plan["query_request_policy"] = "must_use_defaults_if_missing"

        retry_payload, retry_meta = self.llm_client.data_query_request(
            user_goal=user_goal,
            assistant_plan=retry_plan,
        )
        if not retry_meta.get("error"):
            retry_normalized, retry_validation_error = self._normalize_query_request_payload(
                retry_payload,
                expected_resource=expected_resource,
            )
            if retry_normalized is not None:
                retry_meta["retry"] = "query_request_recovered"
                retry_meta["first_error"] = first_error
                return retry_normalized, retry_meta
            first_error = str(retry_payload.get("error", retry_validation_error)).strip() or first_error
            meta = retry_meta

        fallback_request = self._build_default_query_request(
            user_goal=user_goal,
            assistant_plan=effective_plan,
            model_error=first_error,
        )
        if fallback_request is not None:
            meta["fallback"] = "query_request_defaults"
            meta["fallback_reason"] = first_error
            return fallback_request, meta

        meta["error"] = first_error or "data_query_request_failed"
        meta["mode"] = "error"
        return {}, meta

    def _normalize_query_request_payload(
        self,
        payload: dict[str, object],
        *,
        expected_resource: str,
    ) -> tuple[dict[str, object] | None, str]:
        if str(payload.get("status", "")).strip().lower() != "ok":
            return None, str(payload.get("error", "data_query_request_failed")).strip() or "data_query_request_failed"

        requested_resource = str(payload.get("requested_resource", "")).strip()
        query_filter = str(payload.get("query_filter", "")).strip()
        selected_fields = self._ensure_string_list(payload.get("selected_fields"))
        reason = str(payload.get("reason", "")).strip()

        if not requested_resource:
            return None, "query_request_missing_resource"
        if expected_resource and requested_resource != expected_resource:
            return None, "query_request_resource_mismatch"
        if not query_filter:
            return None, "query_request_missing_filter"
        if not selected_fields:
            return None, "query_request_missing_fields"
        if not reason:
            return None, "query_request_missing_reason"

        return {
            "status": "ok",
            "requested_resource": requested_resource,
            "query_filter": query_filter,
            "selected_fields": selected_fields,
            "reason": reason,
        }, ""

    def _with_query_defaults(self, *, user_goal: str, assistant_plan: dict[str, object]) -> dict[str, object]:
        enriched = dict(assistant_plan)
        scope = str(enriched.get("query_scope", "")).strip()
        if not scope and user_goal.strip():
            enriched["query_scope"] = user_goal.strip()

        resource = str(enriched.get("dataset_resource", "")).strip()
        week_hint = self._extract_week_hint(resource)
        default_filter_hint = "department = 销售部"
        if week_hint:
            default_filter_hint = f"week = {week_hint} AND department = 销售部"

        enriched["query_request_defaults"] = {
            "default_filter_hint": default_filter_hint,
            "default_selected_fields": ["revenue", "orders", "conversion_rate"],
        }
        return enriched

    def _build_default_query_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
        model_error: str,
    ) -> dict[str, object] | None:
        requested_resource = str(assistant_plan.get("dataset_resource", "")).strip()
        if not requested_resource:
            return None

        query_filter = self._build_default_query_filter(user_goal=user_goal, assistant_plan=assistant_plan)
        if not query_filter:
            return None

        return {
            "status": "ok",
            "requested_resource": requested_resource,
            "query_filter": query_filter,
            "selected_fields": ["revenue", "orders", "conversion_rate"],
            "reason": (
                "模型返回异常，已按受控默认规则补全查询请求："
                "仅使用 assistant_plan 指定数据集，并使用周报标准指标字段。"
                if model_error
                else "按受控默认规则补全查询请求。"
            ),
        }

    def _build_default_query_filter(self, *, user_goal: str, assistant_plan: dict[str, object]) -> str:
        scope = str(assistant_plan.get("query_scope", "")).strip()
        resource = str(assistant_plan.get("dataset_resource", "")).strip()
        week_hint = self._extract_week_hint(resource)

        parts: list[str] = []
        if week_hint:
            parts.append(f"week = {week_hint}")
        if "销售" in user_goal or "sales" in user_goal.lower() or "sales" in scope.lower():
            parts.append("department = 销售部")
        if parts:
            return " AND ".join(parts)
        if scope:
            return scope
        if user_goal.strip():
            return user_goal.strip()
        return "latest complete week sales performance"

    def _extract_week_hint(self, resource: str) -> str:
        lowered = resource.strip().lower()
        if not lowered:
            return ""
        matched = re.search(r"week[_:-]?(\d+)", lowered)
        if not matched:
            return ""
        return matched.group(1)

    def query_dataset_authorized(
        self,
        *,
        task_id: str,
        resource: str,
        capability_token: str,
        auth_token: str,
    ) -> dict[str, str]:
        self.gateway.check(
            principal=self.identity.principal,
            auth_token=auth_token,
            task_id=task_id,
            action="query",
            resource=resource,
            capability_token=capability_token,
        )
        return self.data_store.read_document_record(resource)

    def analyze_dataset(
        self,
        *,
        dataset_resource: str,
        query_filter: str,
        selected_fields: list[str],
        dataset_text: str,
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, meta = self.llm_client.data_query(
            dataset_resource=dataset_resource,
            query_filter=query_filter,
            selected_fields=selected_fields,
            dataset_text=dataset_text,
            user_goal=user_goal,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "data_query_failed")).strip() or "data_query_failed"
            meta["mode"] = "error"
            return {}, meta

        metrics_raw = payload.get("metrics")
        metrics: list[dict[str, str]] = []
        if isinstance(metrics_raw, list):
            for item in metrics_raw[:8]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                value = str(item.get("value", "")).strip()
                if not name or not value:
                    continue
                metrics.append({"name": name, "value": value})

        result = {
            "status": "ok",
            "summary": str(payload.get("summary", "")).strip(),
            "metrics": metrics,
            "highlights": self._ensure_string_list(payload.get("highlights")),
            "risks": self._ensure_string_list(payload.get("risks")),
            "evidence": self._ensure_string_list(payload.get("evidence")),
        }
        if not result["summary"]:
            meta["error"] = "data_query_missing_summary"
            meta["mode"] = "error"
            return {}, meta
        if len(metrics) < 3:
            meta["error"] = "data_query_missing_metrics"
            meta["mode"] = "error"
            return {}, meta
        if not result["evidence"]:
            meta["error"] = "data_query_missing_evidence"
            meta["mode"] = "error"
            return {}, meta
        return result, meta

    def _ensure_string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
            if len(cleaned) >= 10:
                break
        return cleaned


class ReportAgent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        gateway: AuthorizationGateway,
        llm_client: AgentLLMClient,
    ) -> None:
        self.identity = identity
        self.gateway = gateway
        self.llm_client = llm_client

    def prepare_report_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
        query_result: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, meta = self.llm_client.report_request(
            user_goal=user_goal,
            assistant_plan=assistant_plan,
            query_result=query_result,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "report_request_failed")).strip() or "report_request_failed"
            meta["mode"] = "error"
            return {}, meta

        report_name = str(payload.get("report_name", "")).strip()
        output_format = str(payload.get("output_format", "")).strip().lower()
        sections = self._ensure_string_list(payload.get("sections"))
        reason = str(payload.get("reason", "")).strip()

        if not report_name:
            meta["error"] = "report_request_missing_name"
            meta["mode"] = "error"
            return {}, meta
        if output_format != "markdown":
            meta["error"] = "report_request_invalid_format"
            meta["mode"] = "error"
            return {}, meta
        if len(sections) < 3:
            meta["error"] = "report_request_missing_sections"
            meta["mode"] = "error"
            return {}, meta
        if not reason:
            meta["error"] = "report_request_missing_reason"
            meta["mode"] = "error"
            return {}, meta

        return {
            "status": "ok",
            "report_name": report_name,
            "output_format": output_format,
            "sections": sections,
            "reason": reason,
        }, meta

    def generate_report_authorized(
        self,
        *,
        task_id: str,
        report_resource: str,
        capability_token: str,
        auth_token: str,
        report_request: dict[str, object],
        query_result: dict[str, object],
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        self.gateway.check(
            principal=self.identity.principal,
            auth_token=auth_token,
            task_id=task_id,
            action="generate_report",
            resource=report_resource,
            capability_token=capability_token,
        )
        payload, meta = self.llm_client.report(
            report_name=str(report_request.get("report_name", "")).strip(),
            output_format=str(report_request.get("output_format", "")).strip(),
            sections=report_request.get("sections") if isinstance(report_request.get("sections"), list) else [],
            query_result=query_result,
            user_goal=user_goal,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "report_failed")).strip() or "report_failed"
            meta["mode"] = "error"
            return {}, meta

        table_rows_raw = payload.get("table_rows")
        table_rows: list[dict[str, str]] = []
        if isinstance(table_rows_raw, list):
            for item in table_rows_raw[:8]:
                if not isinstance(item, dict):
                    continue
                metric = str(item.get("metric", "")).strip()
                value = str(item.get("value", "")).strip()
                if metric and value:
                    table_rows.append({"metric": metric, "value": value})

        report_result = {
            "status": "ok",
            "title": str(payload.get("title", "")).strip(),
            "executive_summary": str(payload.get("executive_summary", "")).strip(),
            "key_findings": self._ensure_string_list(payload.get("key_findings")),
            "risk_flags": self._ensure_string_list(payload.get("risk_flags")),
            "next_actions": self._ensure_string_list(payload.get("next_actions")),
            "table_rows": table_rows,
        }
        if not report_result["title"] or not report_result["executive_summary"]:
            meta["error"] = "report_missing_title_or_summary"
            meta["mode"] = "error"
            return {}, meta
        if len(table_rows) < 3:
            meta["error"] = "report_missing_table_rows"
            meta["mode"] = "error"
            return {}, meta
        return report_result, meta

    def _ensure_string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
            if len(cleaned) >= 8:
                break
        return cleaned


class MailAgent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        gateway: AuthorizationGateway,
        data_store: DemoDataStore,
        llm_client: AgentLLMClient,
    ) -> None:
        self.identity = identity
        self.gateway = gateway
        self.data_store = data_store
        self.llm_client = llm_client

    def prepare_mail_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
        report_result: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, meta = self.llm_client.mail_request(
            user_goal=user_goal,
            assistant_plan=assistant_plan,
            report_result=report_result,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "mail_request_failed")).strip() or "mail_request_failed"
            meta["mode"] = "error"
            return {}, meta

        requested_target = str(payload.get("requested_target", "")).strip()
        expected_target = str(assistant_plan.get("recipient", "")).strip()
        subject_style = str(payload.get("subject_style", "")).strip()
        approval_required = bool(payload.get("approval_required"))
        reason = str(payload.get("reason", "")).strip()

        if requested_target != expected_target:
            meta["error"] = "mail_request_target_mismatch"
            meta["mode"] = "error"
            return {}, meta
        if not subject_style:
            meta["error"] = "mail_request_missing_subject_style"
            meta["mode"] = "error"
            return {}, meta
        if not approval_required:
            meta["error"] = "mail_request_missing_approval_flag"
            meta["mode"] = "error"
            return {}, meta
        if not reason:
            meta["error"] = "mail_request_missing_reason"
            meta["mode"] = "error"
            return {}, meta

        return {
            "status": "ok",
            "requested_target": requested_target,
            "subject_style": subject_style,
            "approval_required": approval_required,
            "reason": reason,
        }, meta

    def compose_mail(
        self,
        *,
        recipient: str,
        subject_style: str,
        report_result: dict[str, object],
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, meta = self.llm_client.mail(
            recipient=recipient,
            subject_style=subject_style,
            report_result=report_result,
            user_goal=user_goal,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "mail_failed")).strip() or "mail_failed"
            meta["mode"] = "error"
            return {}, meta

        mail_result = {
            "status": "ok",
            "subject": str(payload.get("subject", "")).strip(),
            "body": str(payload.get("body", "")).strip(),
            "bullets": self._ensure_string_list(payload.get("bullets")),
            "risk_note": str(payload.get("risk_note", "")).strip(),
        }
        if not mail_result["subject"] or not mail_result["body"]:
            meta["error"] = "mail_missing_subject_or_body"
            meta["mode"] = "error"
            return {}, meta
        return mail_result, meta

    def send_message_authorized(
        self,
        *,
        task_id: str,
        target: str,
        content: str,
        capability_token: str,
        auth_token: str,
    ) -> dict[str, str]:
        self.gateway.check(
            principal=self.identity.principal,
            auth_token=auth_token,
            task_id=task_id,
            action="send_mail",
            resource=target,
            capability_token=capability_token,
        )
        return self.data_store.send_message(task_id, target, content)

    def _ensure_string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
            if len(cleaned) >= 8:
                break
        return cleaned


class AssistantAgent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        llm_client: AgentLLMClient,
    ) -> None:
        self.identity = identity
        self.llm_client = llm_client
        self._last_runtime: dict[str, Any] = {
            "task_id": "",
            "user_goal": "",
            "assistant": {},
            "query": {},
            "report": {},
            "mail": {},
        }

    def reset_runtime_status(self) -> None:
        self._last_runtime = {
            "task_id": "",
            "user_goal": "",
            "assistant": {},
            "query": {},
            "report": {},
            "mail": {},
        }

    def update_runtime_status(
        self,
        *,
        task_id: str,
        user_goal: str,
        assistant_meta: dict[str, object],
        query_meta: dict[str, object],
        report_meta: dict[str, object],
        mail_meta: dict[str, object],
    ) -> None:
        self._last_runtime = {
            "task_id": task_id,
            "user_goal": user_goal,
            "assistant": dict(assistant_meta),
            "query": dict(query_meta),
            "report": dict(report_meta),
            "mail": dict(mail_meta),
        }

    def planner_status(self) -> dict[str, object]:
        return {
            "provider": self.llm_client.provider,
            "model": self.llm_client.model,
            "enabled": self.llm_client.enabled,
            "task_id": str(self._last_runtime.get("task_id", "")),
            "user_goal": str(self._last_runtime.get("user_goal", "")),
            "assistant": self._last_runtime.get("assistant", {}),
            "query": self._last_runtime.get("query", {}),
            "report": self._last_runtime.get("report", {}),
            "mail": self._last_runtime.get("mail", {}),
        }

    def create_plan(
        self,
        *,
        user_goal: str,
        allowed_resources: list[str],
        allowed_targets: list[str],
    ) -> tuple[dict[str, object], dict[str, object]]:
        payload, meta = self.llm_client.assistant(
            user_goal=user_goal,
            allowed_resources=allowed_resources,
            allowed_targets=allowed_targets,
        )
        if meta.get("error"):
            return {}, meta

        if str(payload.get("status", "")).strip().lower() != "ok":
            meta["error"] = str(payload.get("error", "assistant_failed")).strip() or "assistant_failed"
            meta["mode"] = "error"
            return {}, meta

        dataset_resource = str(payload.get("dataset_resource", "")).strip()
        recipient = str(payload.get("recipient", "")).strip()
        report_resource = str(payload.get("report_resource", "")).strip()
        report_type = str(payload.get("report_type", "")).strip()
        query_scope = str(payload.get("query_scope", "")).strip()
        reason = str(payload.get("reason", "")).strip()
        approval_required = bool(payload.get("approval_required"))
        action_sequence = payload.get("action_sequence")

        if dataset_resource not in allowed_resources:
            meta["error"] = "assistant_dataset_out_of_scope"
            meta["mode"] = "error"
            return {}, meta
        if recipient not in allowed_targets:
            meta["error"] = "assistant_recipient_out_of_scope"
            meta["mode"] = "error"
            return {}, meta
        if report_resource != "artifact:weekly_sales_report":
            meta["error"] = "assistant_invalid_report_resource"
            meta["mode"] = "error"
            return {}, meta
        if not isinstance(action_sequence, list) or [str(x).strip().lower() for x in action_sequence] != [
            "query",
            "generate_report",
            "send_mail",
        ]:
            meta["error"] = "assistant_invalid_action_sequence"
            meta["mode"] = "error"
            return {}, meta
        if not report_type or not query_scope or not reason or not approval_required:
            meta["error"] = "assistant_missing_required_fields"
            meta["mode"] = "error"
            return {}, meta

        return {
            "dataset_resource": dataset_resource,
            "recipient": recipient,
            "report_resource": report_resource,
            "report_type": report_type,
            "query_scope": query_scope,
            "action_sequence": ["query", "generate_report", "send_mail"],
            "approval_required": approval_required,
            "reason": reason,
        }, meta
