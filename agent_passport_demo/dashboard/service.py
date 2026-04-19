from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..agents import AssistantAgent, DataQueryAgent, MailAgent, ReportAgent, ScenarioResult
from ..audit import AuditLedger
from ..benchmark import DEFAULT_BENCHMARK_CASES
from ..data import DemoDataStore
from ..delegation import DelegationManager
from ..file_store import FileStore
from ..frontend import DashboardFrontend
from ..gateway import AuthorizationGateway
from ..llm_client import AgentLLMClient
from ..models import AgentIdentity, now_utc
from ..policy import PolicyStore
from ..real_flow import RealCollaborationFlow
from ..registry import AgentRegistry
from ..storage import DemoDatabase
from .exporter import DashboardExporterMixin
from .presenters import DashboardPresenterMixin
from .views import DashboardViewMixin


def _parse_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off", ""}:
        return False
    raise ValueError("invalid boolean value")


class DemoService(DashboardViewMixin, DashboardPresenterMixin, DashboardExporterMixin):
    def __init__(self) -> None:
        self.user_principal = "user:xiaoming"
        self.display_timezone = ZoneInfo("Asia/Shanghai")
        try:
            self.debug_state = _parse_bool(os.getenv("DEMO_DEBUG_STATE"), default=False)
        except ValueError:
            self.debug_state = False

        project_root = Path(__file__).resolve().parent.parent.parent
        self.workdir = project_root / "workdir"
        self.templates_dir = project_root / "templates"
        self.static_dir = project_root / "static"
        self.docs_dir = self.workdir / "docs"
        self.tasks_dir = self.workdir / "tasks"
        self.outputs_dir = self.workdir / "outputs"
        self.artifacts_dir = project_root / "artifacts"
        self.db_path = project_root / "agent_passport_state.db"
        self.capability_signing_key = "agent-passport-demo-signing-key"

        self.frontend = DashboardFrontend(self.templates_dir)
        self.database = DemoDatabase(self.db_path)

        self.last_result: ScenarioResult | None = None
        self.last_real_collaboration: dict[str, object] | None = None
        self.latest_benchmark_report: dict[str, object] | None = None
        self.last_authorization_request: dict[str, object] | None = None
        self.last_authorization_response: dict[str, object] | None = None
        self.latest_artifact_zip: Path | None = None
        self.latest_scenario_artifact_zip: Path | None = None
        self.latest_benchmark_artifact_zip: Path | None = None
        self._last_unified_payload: dict[str, object] | None = None

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.reset(clear_history=True)

    def reset(self, *, clear_history: bool) -> None:
        preserved_last_result = self.last_result if not clear_history else None
        preserved_last_real = self.last_real_collaboration if not clear_history else None
        preserved_benchmark = self.latest_benchmark_report if not clear_history else None
        preserved_auth_request = self.last_authorization_request if not clear_history else None
        preserved_auth_response = self.last_authorization_response if not clear_history else None
        preserved_latest_artifact = self.latest_artifact_zip if not clear_history else None
        preserved_scenario_artifact = self.latest_scenario_artifact_zip if not clear_history else None
        preserved_benchmark_artifact = self.latest_benchmark_artifact_zip if not clear_history else None

        self.database.reset_runtime(clear_history=clear_history)
        self.policy_store = PolicyStore(self.database)
        self.audit_ledger = AuditLedger(self.database)
        self.delegation_manager = DelegationManager(self.database, signing_key=self.capability_signing_key)
        self.file_store = FileStore(self.docs_dir, tasks_dir=self.tasks_dir, outputs_dir=self.outputs_dir)
        self.data_store = DemoDataStore(self.database, file_store=self.file_store)

        assistant_identity = AgentIdentity(
            principal="agent:assistant",
            role="assistant",
            description="负责承接用户办公任务并拆解协作计划。",
            auth_token=f"agt_{uuid4().hex[:10]}",
            trust_level="verified-workload",
            owner_user=self.user_principal,
        )
        data_query_identity = AgentIdentity(
            principal="agent:data_query",
            role="data_query",
            description="负责在授权范围内查询销售业务数据。",
            auth_token=f"agt_{uuid4().hex[:10]}",
            trust_level="verified-workload",
            owner_user=self.user_principal,
        )
        report_identity = AgentIdentity(
            principal="agent:report",
            role="report",
            description="负责把查询结果生成正式周报。",
            auth_token=f"agt_{uuid4().hex[:10]}",
            trust_level="verified-workload",
            owner_user=self.user_principal,
        )
        mail_identity = AgentIdentity(
            principal="agent:mail",
            role="mail",
            description="负责把最终报表发送给授权经理。",
            auth_token=f"agt_{uuid4().hex[:10]}",
            trust_level="verified-workload",
            owner_user=self.user_principal,
        )

        self.identities = [assistant_identity, data_query_identity, report_identity, mail_identity]
        self.agent_registry = AgentRegistry(self.identities)
        self.gateway = AuthorizationGateway(
            policy_store=self.policy_store,
            delegation_manager=self.delegation_manager,
            audit_ledger=self.audit_ledger,
            agent_registry=self.agent_registry,
        )

        self.llm_client = AgentLLMClient()
        self.assistant_agent = AssistantAgent(identity=assistant_identity, llm_client=self.llm_client)
        self.data_query_agent = DataQueryAgent(
            identity=data_query_identity,
            gateway=self.gateway,
            data_store=self.data_store,
            llm_client=self.llm_client,
        )
        self.report_agent = ReportAgent(
            identity=report_identity,
            gateway=self.gateway,
            llm_client=self.llm_client,
        )
        self.mail_agent = MailAgent(
            identity=mail_identity,
            gateway=self.gateway,
            data_store=self.data_store,
            llm_client=self.llm_client,
        )
        self.real_collaboration_flow = RealCollaborationFlow(
            assistant_agent=self.assistant_agent,
            data_query_agent=self.data_query_agent,
            report_agent=self.report_agent,
            mail_agent=self.mail_agent,
            policy_store=self.policy_store,
            delegation_manager=self.delegation_manager,
            audit_ledger=self.audit_ledger,
            file_store=self.file_store,
        )

        self.run_history = self.database.list_scenario_runs()
        self._last_unified_payload = None

        if clear_history:
            self.last_result = None
            self.last_real_collaboration = None
            self.latest_benchmark_report = None
            self.last_authorization_request = None
            self.last_authorization_response = None
            self.latest_artifact_zip = None
            self.latest_scenario_artifact_zip = None
            self.latest_benchmark_artifact_zip = None
        else:
            self.last_result = preserved_last_result
            self.last_real_collaboration = preserved_last_real
            self.latest_benchmark_report = preserved_benchmark
            self.last_authorization_request = preserved_auth_request
            self.last_authorization_response = preserved_auth_response
            self.latest_artifact_zip = preserved_latest_artifact
            self.latest_scenario_artifact_zip = preserved_scenario_artifact
            self.latest_benchmark_artifact_zip = preserved_benchmark_artifact

    def _scenario_handlers(self) -> dict[str, Callable[[str, bool], ScenarioResult]]:
        return {
            scenario: (
                lambda user_principal, update_display=True, _scenario=scenario: self._run_unified_flow_scenario(
                    _scenario,
                    user_principal,
                    update_display=update_display,
                )
            )
            for scenario in self.real_collaboration_flow.supported_scenarios()
        }

    def _run_unified_flow_scenario(
        self,
        scenario: str,
        user_principal: str,
        *,
        update_display: bool,
    ) -> ScenarioResult:
        result, payload = self.real_collaboration_flow.run_scenario(scenario, user_principal)
        self._last_unified_payload = payload

        if update_display:
            if scenario == "real_collaboration":
                self.last_real_collaboration = payload
            self.last_result = result
        return result

    def run_scenario(self, name: str, *, update_display: bool = True) -> ScenarioResult:
        scenarios = self._scenario_handlers()
        if name not in scenarios:
            raise ValueError(f"unsupported scenario: {name}")

        started_at = now_utc().isoformat(timespec="seconds")
        self.reset(clear_history=False)
        result = scenarios[name](self.user_principal, update_display)
        finished_at = now_utc().isoformat(timespec="seconds")

        self.database.record_scenario_run(
            scenario_name=name,
            task_id=result.task_id,
            status=result.status,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.run_history = self.database.list_scenario_runs()

        self._export_task_artifact(
            scenario_name=name,
            task_id=result.task_id,
            started_at=started_at,
            finished_at=finished_at,
            result=result,
            real_collaboration_payload=(dict(self._last_unified_payload) if isinstance(self._last_unified_payload, dict) else None),
            mark_latest=update_display,
        )
        return result

    def run_benchmark(self) -> dict[str, object]:
        case_rows: list[dict[str, object]] = []
        for case in DEFAULT_BENCHMARK_CASES:
            result = self.run_scenario(case.name, update_display=False)
            passed = result.status == case.expected_status and result.reason_code == case.expected_reason_code
            case_rows.append(
                {
                    "name": case.name,
                    "title": case.title,
                    "category": case.category,
                    "objective": case.objective,
                    "expected_status": case.expected_status,
                    "expected_reason_code": case.expected_reason_code,
                    "expected_outcome": case.expected_outcome,
                    "actual_status": result.status,
                    "actual_reason_code": result.reason_code,
                    "actual_title": result.title,
                    "actual_detail": result.detail,
                    "task_id": result.task_id,
                    "passed": passed,
                }
            )

        total = len(case_rows)
        passed_count = sum(1 for row in case_rows if bool(row["passed"]))
        denied_cases = [row for row in case_rows if row["expected_status"] == "denied"]
        blocked_count = sum(1 for row in denied_cases if row["actual_status"] == "denied")

        report = {
            "total": total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "pass_rate": self._format_ratio(passed_count, total),
            "blocked_count": blocked_count,
            "blocked_rate": self._format_ratio(blocked_count, len(denied_cases)),
            "latest_run_at": now_utc().isoformat(timespec="seconds"),
            "rows": case_rows,
        }
        self.latest_benchmark_report = report

        last_task_id = str(case_rows[-1]["task_id"]) if case_rows else "-"
        self.last_result = ScenarioResult(
            status="success" if passed_count == total else "error",
            title="批量安全评测完成",
            detail=f"共执行 {total} 个用例，其中 {passed_count} 个符合预期。",
            task_id=last_task_id,
            reason_code="benchmark_completed",
        )
        self._export_benchmark_artifact(report)
        return report

    def authorize_request(
        self,
        payload: dict[str, object],
        *,
        audit_mode_override: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        subject = payload.get("subject") or {}
        action = payload.get("action") or {}
        resource = payload.get("resource") or {}
        context = payload.get("context") or {}

        principal = str(subject.get("id", "")).strip()
        action_name = str(action.get("name", "")).strip()
        resource_id = str(resource.get("id", "")).strip()
        task_id = str(context.get("task_id", "")).strip()
        auth_token = context.get("auth_token")
        capability_token = context.get("capability_token")

        try:
            consume = _parse_bool(context.get("consume", False), default=False)
        except ValueError:
            response = {
                "decision": "deny",
                "reason_code": "invalid_request",
                "reason_text": "context.consume must be a boolean",
                "policy_rule": "request validation",
            }
            self.last_authorization_request = payload
            self.last_authorization_response = response
            return 400, response

        audit_mode = str(audit_mode_override if audit_mode_override is not None else context.get("audit_mode", "full")).strip().lower()
        if not principal or not action_name or not resource_id or not task_id:
            response = {
                "decision": "deny",
                "reason_code": "invalid_request",
                "reason_text": "subject.id, action.name, resource.id and context.task_id are required",
                "policy_rule": "request validation",
            }
            self.last_authorization_request = payload
            self.last_authorization_response = response
            return 400, response
        if audit_mode not in {"full", "preview", "off"}:
            response = {
                "decision": "deny",
                "reason_code": "invalid_request",
                "reason_text": "context.audit_mode must be one of: full, preview, off",
                "policy_rule": "request validation",
            }
            self.last_authorization_request = payload
            self.last_authorization_response = response
            return 400, response

        response = self.gateway.authorize(
            principal=principal,
            auth_token=None if auth_token is None else str(auth_token),
            task_id=task_id,
            action=action_name,
            resource=resource_id,
            capability_token=None if capability_token is None else str(capability_token),
            consume=consume,
            record_audit=(audit_mode == "full"),
        )

        if audit_mode == "preview":
            self.audit_ledger.record(
                event_type="api_probe",
                task_id=task_id,
                principal=principal,
                action=action_name,
                resource=resource_id,
                decision=str(response.get("decision", "deny")),
                reason=str(response.get("reason_text", "api authorize preview")),
                metadata={
                    "reason_code": str(response.get("reason_code", "unknown")),
                    "reason_text": str(response.get("reason_text", "")),
                    "policy_rule": str(response.get("policy_rule", "")),
                    "audit_mode": "preview",
                    "internal_event": True,
                },
            )

        response["audit_mode"] = audit_mode
        self.last_authorization_request = payload
        self.last_authorization_response = response
        return 200, response

    def state_payload(self, *, debug: bool | None = None) -> dict[str, object]:
        include_debug = bool(debug) if debug is not None else self.debug_state
        if include_debug:
            return self._full_state_payload()
        return self._public_state_payload()

    def _public_state_payload(self) -> dict[str, object]:
        benchmark = self._benchmark_report()
        runtime_payload = self.last_real_collaboration if isinstance(self.last_real_collaboration, dict) else {}
        runtime_model = self.assistant_agent.planner_status()
        return {
            "last_result": None if self.last_result is None else self.last_result.__dict__,
            "summary": {
                "resource_count": len(self.data_store.export_resources()),
                "policy_count": len(self.policy_store.export()),
                "delegation_count": len(self.delegation_manager.export()),
                "audit_event_count": len(self.audit_ledger.events()),
                "message_count": len(self.data_store.sent_messages),
                "scenario_run_count": len(self.run_history),
            },
            "scenario_history": self.run_history[:12],
            "benchmark_report": {
                "total": benchmark["total"],
                "passed_count": benchmark["passed_count"],
                "failed_count": benchmark["failed_count"],
                "pass_rate": benchmark["pass_rate"],
                "blocked_count": benchmark["blocked_count"],
                "blocked_rate": benchmark["blocked_rate"],
                "latest_run_at": benchmark["latest_run_at"],
            },
            "planner": runtime_model,
            "real_collaboration": {
                "task_id": runtime_payload.get("task_id", ""),
                "status": runtime_payload.get("status", "idle"),
                "reason_code": runtime_payload.get("reason_code", ""),
                "reason_text": runtime_payload.get("reason_text", ""),
                "assistant_latency": runtime_payload.get("assistant_latency", 0),
                "query_latency": runtime_payload.get("query_latency", 0),
                "report_latency": runtime_payload.get("report_latency", 0),
                "mail_latency": runtime_payload.get("mail_latency", 0),
                "query_resource": runtime_payload.get("query_resource", ""),
                "planned_recipient": runtime_payload.get("planned_recipient", ""),
                "final_recipient": runtime_payload.get("final_recipient", ""),
                "failure_stage": runtime_payload.get("failure_stage", ""),
                "failure_reason": runtime_payload.get("failure_reason", ""),
            },
        }

    def _full_state_payload(self) -> dict[str, object]:
        return {
            "last_result": None if self.last_result is None else self.last_result.__dict__,
            "resources": self.data_store.export_resources(),
            "policies": self.policy_store.export(),
            "delegations": self.delegation_manager.export(),
            "audit": self.audit_ledger.events(),
            "messages": self.data_store.sent_messages,
            "scenario_history": self.run_history,
            "agents": self.agent_registry.export(),
            "benchmark_report": self._benchmark_report(),
            "last_authorization_request": (
                None if self.last_authorization_request is None else self._mask_decision_payload(self.last_authorization_request)
            ),
            "last_authorization_response": self.last_authorization_response,
            "planner": self.assistant_agent.planner_status(),
            "last_payload": self._last_unified_payload,
            "real_collaboration": self.last_real_collaboration,
        }

    def _benchmark_report(self) -> dict[str, object]:
        if self.latest_benchmark_report is not None:
            return self.latest_benchmark_report
        return {
            "total": 0,
            "passed_count": 0,
            "failed_count": 0,
            "pass_rate": "0 / 0",
            "blocked_count": 0,
            "blocked_rate": "0 / 0",
            "latest_run_at": "尚未运行",
            "rows": [],
        }

    def _format_ratio(self, numerator: int, denominator: int) -> str:
        if denominator <= 0:
            return "0 / 0"
        percentage = int((numerator / denominator) * 100)
        return f"{numerator} / {denominator} ({percentage}%)"
