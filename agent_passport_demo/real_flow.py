from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import shorten
from uuid import uuid4

from .agents import AssistantAgent, DataQueryAgent, MailAgent, ReportAgent, ScenarioResult
from .audit import AuditLedger
from .delegation import DelegationManager
from .file_store import FileStore
from .gateway import AuthorizationError
from .models import now_utc
from .policy import PolicyStore


DEFAULT_GOAL = "帮我生成上周销售部业绩报表，并发送给部门张经理。"


@dataclass(frozen=True)
class FlowMutation:
    override_query_resource: str | None = None
    override_recipient: str | None = None
    revoke_root_query_permission: bool = False
    expire_query_delegation: bool = False
    query_ttl_seconds: int | None = None
    simulated_wait_seconds: int = 0
    tamper_query_token: bool = False
    replay_query: bool = False
    remove_mail_approval_ticket: bool = False


@dataclass(frozen=True)
class ScenarioProfile:
    scenario: str
    expected_status: str
    success_reason_code: str
    success_title: str
    deny_reason_code: str
    deny_title: str
    deny_detail: str
    user_goal: str = ""
    allowed_resources: tuple[str, ...] = ()
    allowed_targets: tuple[str, ...] = ()
    mutation: FlowMutation = FlowMutation()


@dataclass
class FlowRuntime:
    scenario: str
    task_id: str
    task_file_path: str
    user_goal: str
    allowed_resources: list[str]
    allowed_targets: list[str]
    assistant_plan: dict[str, object] = field(default_factory=dict)
    assistant_meta: dict[str, object] = field(default_factory=dict)
    query_request: dict[str, object] = field(default_factory=dict)
    query_request_meta: dict[str, object] = field(default_factory=dict)
    query_result: dict[str, object] = field(default_factory=dict)
    query_result_meta: dict[str, object] = field(default_factory=dict)
    report_request: dict[str, object] = field(default_factory=dict)
    report_request_meta: dict[str, object] = field(default_factory=dict)
    report_result: dict[str, object] = field(default_factory=dict)
    report_result_meta: dict[str, object] = field(default_factory=dict)
    mail_request: dict[str, object] = field(default_factory=dict)
    mail_request_meta: dict[str, object] = field(default_factory=dict)
    mail_result: dict[str, object] = field(default_factory=dict)
    mail_result_meta: dict[str, object] = field(default_factory=dict)
    query_token: str = ""
    report_token: str = ""
    mail_token: str = ""
    query_ttl_seconds: int = 0
    report_ttl_seconds: int = 0
    mail_ttl_seconds: int = 0
    query_resource: str = ""
    recipient: str = ""
    output_path: str = ""
    output_name: str = ""
    failure_stage: str = ""
    failure_reason: str = ""
    work_trace: list[dict[str, object]] = field(default_factory=list)


SCENARIO_PROFILES: dict[str, ScenarioProfile] = {
    "real_collaboration": ScenarioProfile(
        scenario="real_collaboration",
        expected_status="success",
        success_reason_code="task_completed",
        success_title="销售周报协作完成",
        deny_reason_code="task_denied",
        deny_title="销售周报协作被拦截",
        deny_detail="多智能体办公任务未能通过安全控制。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
    ),
    "unauthorized_query": ScenarioProfile(
        scenario="unauthorized_query",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="越权查询异常放行",
        deny_reason_code="resource_not_in_scope",
        deny_title="跨部门数据越权已拦截",
        deny_detail="数据查询 Agent 尝试访问财务数据，网关已拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(override_query_resource="dataset:finance_sensitive"),
    ),
    "wrong_recipient": ScenarioProfile(
        scenario="wrong_recipient",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="错误收件人异常放行",
        deny_reason_code="target_mismatch",
        deny_title="错误收件人已拦截",
        deny_detail="邮件发送 Agent 尝试把报表发给未授权目标，网关已拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(override_recipient="mail:finance_group"),
    ),
    "revoked_access": ScenarioProfile(
        scenario="revoked_access",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="撤权后查询异常放行",
        deny_reason_code="root_permission_revoked",
        deny_title="撤权后访问已拦截",
        deny_detail="根权限撤销后，系统拒绝继续签发查询委托。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(revoke_root_query_permission=True),
    ),
    "replay_attack": ScenarioProfile(
        scenario="replay_attack",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="重放攻击异常放行",
        deny_reason_code="delegation_exhausted",
        deny_title="重放攻击已拦截",
        deny_detail="一次性查询委托被重复消费时已被拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(replay_query=True),
    ),
    "tampered_token": ScenarioProfile(
        scenario="tampered_token",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="篡改令牌异常放行",
        deny_reason_code="capability_invalid_signature",
        deny_title="篡改令牌已拦截",
        deny_detail="查询 capability token 验签失败，系统已拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(tamper_query_token=True),
    ),
    "expired_delegation": ScenarioProfile(
        scenario="expired_delegation",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="超时令牌异常放行",
        deny_reason_code="capability_expired",
        deny_title="超时令牌已失效",
        deny_detail="查询令牌超过有效期后再次使用，网关已拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(expire_query_delegation=True, query_ttl_seconds=30, simulated_wait_seconds=31),
    ),
    "approval_missing": ScenarioProfile(
        scenario="approval_missing",
        expected_status="denied",
        success_reason_code="security_control_failed",
        success_title="缺失审批异常放行",
        deny_reason_code="approval_missing",
        deny_title="缺失审批已拦截",
        deny_detail="邮件发送动作缺失审批票据，网关已拒绝。",
        user_goal=DEFAULT_GOAL,
        allowed_resources=("dataset:sales_week15",),
        allowed_targets=("mail:manager_zhang",),
        mutation=FlowMutation(remove_mail_approval_ticket=True),
    ),
}


class RealCollaborationFlow:
    def __init__(
        self,
        *,
        assistant_agent: AssistantAgent,
        data_query_agent: DataQueryAgent,
        report_agent: ReportAgent,
        mail_agent: MailAgent,
        policy_store: PolicyStore,
        delegation_manager: DelegationManager,
        audit_ledger: AuditLedger,
        file_store: FileStore,
    ) -> None:
        self.assistant_agent = assistant_agent
        self.data_query_agent = data_query_agent
        self.report_agent = report_agent
        self.mail_agent = mail_agent
        self.policy_store = policy_store
        self.delegation_manager = delegation_manager
        self.audit_ledger = audit_ledger
        self.file_store = file_store

    def supported_scenarios(self) -> tuple[str, ...]:
        return tuple(SCENARIO_PROFILES.keys())

    def run_scenario(
        self,
        scenario: str,
        user_principal: str,
        *,
        user_goal: str | None = None,
    ) -> tuple[ScenarioResult, dict[str, object]]:
        profile = self._profile_for(scenario)
        runtime = self._build_runtime(profile=profile, user_goal=user_goal)
        self._record_task_start(runtime)

        assistant_plan, assistant_meta = self.assistant_agent.create_plan(
            user_goal=runtime.user_goal,
            allowed_resources=runtime.allowed_resources,
            allowed_targets=runtime.allowed_targets,
        )
        runtime.assistant_meta = assistant_meta
        if not assistant_plan:
            return self._finalize_model_failure(profile, runtime, "assistant", "assistant_failed", str(assistant_meta.get("error", "assistant_failed")))
        runtime.assistant_plan = assistant_plan
        runtime.query_resource = str(assistant_plan.get("dataset_resource", "")).strip()
        runtime.recipient = str(assistant_plan.get("recipient", "")).strip()
        self._append_trace(runtime, "assistant_plan", "success", "assistant_plan_ready", "个人助理已生成任务计划。")

        query_request, query_request_meta = self.data_query_agent.prepare_query_request(
            user_goal=runtime.user_goal,
            assistant_plan=assistant_plan,
        )
        runtime.query_request_meta = query_request_meta
        if not query_request:
            return self._finalize_model_failure(profile, runtime, "query_request", "query_request_failed", str(query_request_meta.get("error", "query_request_failed")))
        runtime.query_request = query_request
        if profile.mutation.override_query_resource:
            runtime.query_request["requested_resource"] = profile.mutation.override_query_resource
        self._append_trace(runtime, "query_request", "success", "query_request_ready", "数据查询 Agent 已提交查询请求。")

        if profile.mutation.revoke_root_query_permission:
            self._revoke_root_query_permission(user_principal, runtime.task_id, str(runtime.query_request.get("requested_resource", "")))

        query_delegation, query_denied_reason = self._issue_delegation(
            runtime=runtime,
            root_principal=user_principal,
            from_principal=self.assistant_agent.identity.principal,
            to_principal=self.data_query_agent.identity.principal,
            action="query",
            resource=str(runtime.query_request.get("requested_resource", "")),
            risk_level="medium",
            approval_required=False,
            approval_ticket=None,
            ttl_seconds=self._delegation_ttl_seconds("query", profile),
            max_uses=1,
            event_type="delegation_issued",
            summary="助理向数据查询 Agent 签发查询委托。",
        )
        if query_delegation is None:
            reason_code = query_denied_reason or profile.deny_reason_code
            return self._finalize_denied(profile, runtime, "query_delegation", reason_code, profile.deny_detail)
        runtime.query_token = query_delegation.capability_token
        runtime.query_ttl_seconds = int(query_delegation.ttl_seconds)

        if profile.mutation.expire_query_delegation:
            self._simulate_timeout_wait(runtime, query_delegation.ttl_seconds, profile.mutation.simulated_wait_seconds)
            expired_record = self.delegation_manager.expire_now(query_delegation.delegation_id)
            if expired_record is not None:
                runtime.query_token = expired_record.capability_token

        if profile.mutation.tamper_query_token:
            runtime.query_token = runtime.query_token[:-1] + ("0" if runtime.query_token[-1] != "0" else "1")

        try:
            dataset_record = self.data_query_agent.query_dataset_authorized(
                task_id=runtime.task_id,
                resource=str(runtime.query_request.get("requested_resource", "")),
                capability_token=runtime.query_token,
                auth_token=self.data_query_agent.identity.auth_token,
            )
            if profile.mutation.replay_query:
                self.data_query_agent.query_dataset_authorized(
                    task_id=runtime.task_id,
                    resource=str(runtime.query_request.get("requested_resource", "")),
                    capability_token=runtime.query_token,
                    auth_token=self.data_query_agent.identity.auth_token,
                )
        except AuthorizationError as exc:
            reason_code = self._latest_reason_code(runtime.task_id) or profile.deny_reason_code
            return self._finalize_denied(
                profile,
                runtime,
                "query_gateway",
                reason_code,
                self._localized_reason_text(profile, reason_code, str(exc)),
            )
        except FileNotFoundError:
            return self._finalize_denied(profile, runtime, "query_storage", "dataset_not_found", "授权数据文件不存在。")

        self._append_trace(runtime, "query_access", "success", "query_allowed", "数据查询访问已通过网关校验。")
        query_result, query_result_meta = self.data_query_agent.analyze_dataset(
            dataset_resource=str(runtime.query_request.get("requested_resource", "")),
            query_filter=str(runtime.query_request.get("query_filter", "")),
            selected_fields=runtime.query_request.get("selected_fields") if isinstance(runtime.query_request.get("selected_fields"), list) else [],
            dataset_text=str(dataset_record.get("content", "")),
            user_goal=runtime.user_goal,
        )
        runtime.query_result_meta = query_result_meta
        if not query_result:
            return self._finalize_model_failure(profile, runtime, "query_result", "data_query_failed", str(query_result_meta.get("error", "data_query_failed")))
        runtime.query_result = query_result
        self._append_trace(runtime, "query_result", "success", "query_result_ready", "数据查询 Agent 已生成结构化结果。")

        report_request, report_request_meta = self.report_agent.prepare_report_request(
            user_goal=runtime.user_goal,
            assistant_plan=assistant_plan,
            query_result=query_result,
        )
        runtime.report_request_meta = report_request_meta
        if not report_request:
            return self._finalize_model_failure(profile, runtime, "report_request", "report_request_failed", str(report_request_meta.get("error", "report_request_failed")))
        runtime.report_request = report_request
        self._append_trace(runtime, "report_request", "success", "report_request_ready", "报表生成 Agent 已提交报表生成请求。")

        report_delegation, report_denied_reason = self._issue_delegation(
            runtime=runtime,
            root_principal=user_principal,
            from_principal=self.data_query_agent.identity.principal,
            to_principal=self.report_agent.identity.principal,
            action="generate_report",
            resource=str(assistant_plan.get("report_resource", "artifact:weekly_sales_report")),
            risk_level="medium",
            approval_required=False,
            approval_ticket=None,
            ttl_seconds=self._delegation_ttl_seconds("generate_report", profile),
            max_uses=1,
            event_type="delegation_issued",
            summary="数据查询 Agent 向报表生成 Agent 签发报表委托。",
        )
        if report_delegation is None:
            reason_code = report_denied_reason or "root_permission_revoked"
            return self._finalize_denied(
                profile,
                runtime,
                "report_delegation",
                reason_code,
                "报表委托未获批准，系统已拒绝继续执行。"
                if reason_code != "root_permission_revoked"
                else "根权限已被撤销，无法继续签发报表委托。",
            )
        runtime.report_token = report_delegation.capability_token
        runtime.report_ttl_seconds = int(report_delegation.ttl_seconds)

        report_result, report_result_meta = self.report_agent.generate_report_authorized(
            task_id=runtime.task_id,
            report_resource=str(assistant_plan.get("report_resource", "artifact:weekly_sales_report")),
            capability_token=runtime.report_token,
            auth_token=self.report_agent.identity.auth_token,
            report_request=report_request,
            query_result=query_result,
            user_goal=runtime.user_goal,
        )
        runtime.report_result_meta = report_result_meta
        if not report_result:
            reason = str(report_result_meta.get("error", "report_failed"))
            if reason == "root_permission_revoked":
                return self._finalize_denied(profile, runtime, "report_gateway", reason, "报表生成阶段已被拦截。")
            return self._finalize_model_failure(profile, runtime, "report_result", "report_failed", reason)
        runtime.report_result = report_result
        report_file = self.file_store.write_output(
            task_id=runtime.task_id,
            output_name=str(report_request.get("report_name", "weekly_sales_report.md")),
            content=self._render_report_markdown(report_result),
        )
        runtime.output_path = str(report_file.get("output_path", ""))
        runtime.output_name = str(report_file.get("output_name", ""))
        self._append_trace(runtime, "report_result", "success", "report_generated", "报表生成 Agent 已完成输出文件写入。")

        mail_request, mail_request_meta = self.mail_agent.prepare_mail_request(
            user_goal=runtime.user_goal,
            assistant_plan=assistant_plan,
            report_result=report_result,
        )
        runtime.mail_request_meta = mail_request_meta
        if not mail_request:
            return self._finalize_model_failure(profile, runtime, "mail_request", "mail_request_failed", str(mail_request_meta.get("error", "mail_request_failed")))
        runtime.mail_request = mail_request
        if profile.mutation.override_recipient:
            runtime.mail_request["requested_target"] = profile.mutation.override_recipient
        self._append_trace(runtime, "mail_request", "success", "mail_request_ready", "邮件发送 Agent 已提交发送请求。")

        approval_ticket = None if profile.mutation.remove_mail_approval_ticket else f"APP-{runtime.task_id[-6:].upper()}"
        mail_delegation, mail_denied_reason = self._issue_delegation(
            runtime=runtime,
            root_principal=user_principal,
            from_principal=self.report_agent.identity.principal,
            to_principal=self.mail_agent.identity.principal,
            action="send_mail",
            resource=str(runtime.mail_request.get("requested_target", "")),
            risk_level="high",
            approval_required=True,
            approval_ticket=approval_ticket,
            ttl_seconds=self._delegation_ttl_seconds("send_mail", profile),
            max_uses=1,
            event_type="delegation_issued",
            summary="报表生成 Agent 向邮件发送 Agent 签发发送委托。",
        )
        if mail_delegation is None:
            reason_code = mail_denied_reason or profile.deny_reason_code
            return self._finalize_denied(
                profile,
                runtime,
                "mail_delegation",
                reason_code,
                "发送委托未获批准，系统已拒绝继续发送。"
                if reason_code == "target_mismatch"
                else "根权限已被撤销，无法继续签发发送委托。",
            )
        runtime.mail_token = mail_delegation.capability_token
        runtime.mail_ttl_seconds = int(mail_delegation.ttl_seconds)

        mail_result, mail_result_meta = self.mail_agent.compose_mail(
            recipient=str(runtime.mail_request.get("requested_target", "")),
            subject_style=str(runtime.mail_request.get("subject_style", "")),
            report_result=report_result,
            user_goal=runtime.user_goal,
        )
        runtime.mail_result_meta = mail_result_meta
        if not mail_result:
            return self._finalize_model_failure(profile, runtime, "mail_compose", "mail_failed", str(mail_result_meta.get("error", "mail_failed")))
        runtime.mail_result = mail_result

        try:
            send_result = self.mail_agent.send_message_authorized(
                task_id=runtime.task_id,
                target=str(runtime.mail_request.get("requested_target", "")),
                content=self._render_mail_text(mail_result, runtime.output_name),
                capability_token=runtime.mail_token,
                auth_token=self.mail_agent.identity.auth_token,
            )
        except AuthorizationError as exc:
            reason_code = self._latest_reason_code(runtime.task_id) or profile.deny_reason_code
            runtime.mail_result = {}
            return self._finalize_denied(profile, runtime, "mail_gateway", reason_code, str(exc))

        runtime.mail_result["delivery_record"] = send_result
        self._append_trace(runtime, "mail_send", "success", "mail_sent", "邮件发送 Agent 已完成投递。")
        return self._finalize_success(profile, runtime)

    def _render_report_markdown(self, report_result: dict[str, object]) -> str:
        lines = [f"# {report_result.get('title', '销售周报')}", "", str(report_result.get("executive_summary", "")).strip(), ""]
        table_rows = report_result.get("table_rows") if isinstance(report_result.get("table_rows"), list) else []
        if table_rows:
            lines.extend(["## 核心指标", "", "| 指标 | 数值 |", "| --- | --- |"])
            for row in table_rows:
                if not isinstance(row, dict):
                    continue
                lines.append(f"| {row.get('metric', '-')} | {row.get('value', '-')} |")
            lines.append("")
        for title, key in (
            ("关键发现", "key_findings"),
            ("风险提示", "risk_flags"),
            ("后续动作", "next_actions"),
        ):
            values = report_result.get(key) if isinstance(report_result.get(key), list) else []
            if not values:
                continue
            lines.append(f"## {title}")
            lines.append("")
            for value in values:
                lines.append(f"- {value}")
            lines.append("")
        return "\n".join(lines).strip()

    def _render_mail_text(self, mail_result: dict[str, object], output_name: str) -> str:
        bullets = mail_result.get("bullets") if isinstance(mail_result.get("bullets"), list) else []
        bullet_block = "\n".join(f"- {item}" for item in bullets)
        return (
            f"主题：{mail_result.get('subject', '-')}\n"
            f"正文：{mail_result.get('body', '-')}\n"
            f"附件：{output_name or '-'}\n"
            f"要点：\n{bullet_block}"
        ).strip()

    def _profile_for(self, scenario: str) -> ScenarioProfile:
        if scenario not in SCENARIO_PROFILES:
            raise ValueError(f"unsupported scenario: {scenario}")
        return SCENARIO_PROFILES[scenario]

    def _build_runtime(self, *, profile: ScenarioProfile, user_goal: str | None) -> FlowRuntime:
        task_payload = self.file_store.read_task("task:sales_report") or {}
        task_id = f"task_{uuid4().hex[:6]}"
        return FlowRuntime(
            scenario=profile.scenario,
            task_id=task_id,
            task_file_path=str(task_payload.get("task_file_path", "")),
            user_goal=(user_goal or profile.user_goal or str(task_payload.get("user_goal", "")) or DEFAULT_GOAL).strip(),
            allowed_resources=list(profile.allowed_resources or tuple(task_payload.get("allowed_resources", []))),
            allowed_targets=list(profile.allowed_targets or tuple(task_payload.get("allowed_targets", []))),
        )

    def _record_task_start(self, runtime: FlowRuntime) -> None:
        self._append_trace(runtime, "task_start", "success", "task_started", "任务已创建并进入多智能体编排流程。")
        self.audit_ledger.record(
            event_type="task_lifecycle",
            task_id=runtime.task_id,
            principal="user:xiaoming",
            action="task_start",
            resource="task:sales_report",
            decision="allow",
            reason="task started",
            metadata={"reason_code": "task_started", "summary": runtime.user_goal},
        )

    def _append_trace(self, runtime: FlowRuntime, stage: str, status: str, reason_code: str, summary: str) -> None:
        runtime.work_trace.append(
            {
                "stage": stage,
                "status": status,
                "reason_code": reason_code,
                "summary": summary,
                "timestamp": now_utc().isoformat(timespec="seconds"),
            }
        )

    def _issue_delegation(
        self,
        *,
        runtime: FlowRuntime,
        root_principal: str,
        from_principal: str,
        to_principal: str,
        action: str,
        resource: str,
        risk_level: str,
        approval_required: bool,
        approval_ticket: str | None,
        ttl_seconds: int,
        max_uses: int,
        event_type: str,
        summary: str,
    ) -> tuple[object | None, str | None]:
        if not self.policy_store.has_permission(root_principal, action, resource):
            reason_code = self._delegation_denied_reason(runtime, action, resource)
            self.audit_ledger.record(
                event_type=event_type,
                task_id=runtime.task_id,
                principal=from_principal,
                action=action,
                resource=resource,
                decision="deny",
                reason=reason_code,
                metadata={"reason_code": reason_code, "summary": summary},
            )
            return None, reason_code
        record = self.delegation_manager.issue(
            root_principal=root_principal,
            from_principal=from_principal,
            to_principal=to_principal,
            task_id=runtime.task_id,
            action=action,
            resource=resource,
            risk_level=risk_level,
            approval_required=approval_required,
            approval_ticket=approval_ticket,
            ttl_seconds=ttl_seconds,
            max_uses=max_uses,
        )
        self.audit_ledger.record(
            event_type=event_type,
            task_id=runtime.task_id,
            principal=from_principal,
            action=action,
            resource=resource,
            decision="allow",
            reason="delegation issued",
            metadata={
                "reason_code": "delegation_issued",
                "delegation_id": record.delegation_id,
                "root_principal": root_principal,
                "ttl_seconds": record.ttl_seconds,
                "expires_at": record.expires_at.isoformat(timespec="seconds"),
                "summary": summary,
            },
        )
        return record, None

    def _delegation_ttl_seconds(self, action: str, profile: ScenarioProfile) -> int:
        if action == "query" and profile.mutation.query_ttl_seconds is not None:
            return max(1, int(profile.mutation.query_ttl_seconds))
        return {
            "query": 30,
            "generate_report": 45,
            "send_mail": 45,
        }.get(action, 30)

    def _simulate_timeout_wait(self, runtime: FlowRuntime, ttl_seconds: int, wait_seconds: int) -> None:
        delay = max(wait_seconds, ttl_seconds + 1)
        self._append_trace(
            runtime,
            "query_timeout_wait",
            "pending",
            "delegation_timeout_wait",
            f"已模拟任务卡住 {delay} 秒，等待查询令牌超过有效期。",
        )
        self.audit_ledger.record(
            event_type="task_lifecycle",
            task_id=runtime.task_id,
            principal="user:xiaoming",
            action="task_wait",
            resource="task:sales_report",
            decision="deny",
            reason="task delayed for timeout simulation",
            metadata={
                "reason_code": "delegation_timeout_wait",
                "reason_text": f"任务停留 {delay} 秒，等待查询令牌超时失效。",
                "ttl_seconds": ttl_seconds,
                "wait_seconds": delay,
                "summary": f"已模拟任务卡住 {delay} 秒，等待查询令牌超过有效期。",
            },
        )
        self.audit_ledger.record(
            event_type="policy_change",
            task_id=runtime.task_id,
            principal=self.assistant_agent.identity.principal,
            action="query",
            resource=str(runtime.query_request.get("requested_resource", "")),
            decision="deny",
            reason="delegation expired",
            metadata={
                "reason_code": "capability_expired",
                "reason_text": f"查询令牌已超过 {ttl_seconds} 秒有效期，系统终止任务并发出超时告警。",
                "ttl_seconds": ttl_seconds,
                "wait_seconds": delay,
                "summary": f"查询令牌已超过 {ttl_seconds} 秒有效期，系统准备终止任务。",
            },
        )

    def _delegation_denied_reason(self, runtime: FlowRuntime, action: str, resource: str) -> str:
        if action == "query" and resource not in runtime.allowed_resources:
            return "resource_not_in_scope"
        if action == "send_mail" and resource not in runtime.allowed_targets:
            return "target_mismatch"
        return "root_permission_revoked"

    def _revoke_root_query_permission(self, root_principal: str, task_id: str, resource: str) -> None:
        self.policy_store.revoke_permission(root_principal, "query", resource)
        self.delegation_manager.revoke_for_root_resource(
            root_principal=root_principal,
            action="query",
            resource=resource,
        )
        self.audit_ledger.record(
            event_type="policy_change",
            task_id=task_id,
            principal=root_principal,
            action="query",
            resource=resource,
            decision="deny",
            reason="root permission revoked",
            metadata={"reason_code": "root_permission_revoked", "summary": "已模拟撤销根权限。"},
        )

    def _latest_reason_code(self, task_id: str) -> str | None:
        events = self.audit_ledger.events(task_id=task_id)
        if not events:
            return None
        return str(events[-1].get("reason_code", "")).strip() or None

    def _localized_reason_text(self, profile: ScenarioProfile, reason_code: str, fallback: str) -> str:
        if reason_code == "capability_expired":
            ttl_seconds = profile.mutation.query_ttl_seconds or self._delegation_ttl_seconds("query", profile)
            return f"查询令牌超过 {ttl_seconds} 秒有效期，系统已终止任务并发出超时告警。"
        if reason_code == "delegation_exhausted":
            return "查询令牌已被首次消费，再次调用会被识别为重放攻击并直接拦截。"
        if reason_code == "approval_missing":
            return "高风险发送动作缺少审批票据，系统已拒绝继续发送。"
        if reason_code == "target_mismatch":
            return "发送目标超出本次任务授权范围，系统已阻断错误发送。"
        if reason_code == "resource_not_in_scope":
            return "查询资源超出本次任务授权范围，系统已阻断越权访问。"
        return fallback

    def _finalize_model_failure(
        self,
        profile: ScenarioProfile,
        runtime: FlowRuntime,
        stage: str,
        reason_code: str,
        reason_text: str,
    ) -> tuple[ScenarioResult, dict[str, object]]:
        self.delegation_manager.revoke_for_task(runtime.task_id, reason="task_terminated")
        runtime.failure_stage = stage
        runtime.failure_reason = reason_text
        self._append_trace(runtime, stage, "error", reason_code, reason_text)
        self.audit_ledger.record(
            event_type="task_lifecycle",
            task_id=runtime.task_id,
            principal="user:xiaoming",
            action="task_finalize",
            resource="task:sales_report",
            decision="deny",
            reason="task failed",
            metadata={"reason_code": reason_code, "reason_text": reason_text},
        )
        self.assistant_agent.update_runtime_status(
            task_id=runtime.task_id,
            user_goal=runtime.user_goal,
            assistant_meta=runtime.assistant_meta,
            query_meta={**runtime.query_request_meta, **runtime.query_result_meta},
            report_meta={**runtime.report_request_meta, **runtime.report_result_meta},
            mail_meta={**runtime.mail_request_meta, **runtime.mail_result_meta},
        )
        result = ScenarioResult(
            status="error",
            title="模型执行失败",
            detail=reason_text,
            task_id=runtime.task_id,
            reason_code=reason_code,
        )
        return result, self._build_payload(runtime, result)

    def _finalize_denied(
        self,
        profile: ScenarioProfile,
        runtime: FlowRuntime,
        stage: str,
        reason_code: str,
        reason_text: str,
    ) -> tuple[ScenarioResult, dict[str, object]]:
        self.delegation_manager.revoke_for_task(runtime.task_id, reason="task_terminated")
        runtime.failure_stage = stage
        runtime.failure_reason = reason_text
        self._append_trace(runtime, stage, "denied", reason_code, reason_text)
        self.audit_ledger.record(
            event_type="task_lifecycle",
            task_id=runtime.task_id,
            principal="user:xiaoming",
            action="task_finalize",
            resource="task:sales_report",
            decision="deny",
            reason="task denied",
            metadata={"reason_code": reason_code, "reason_text": reason_text},
        )
        self.assistant_agent.update_runtime_status(
            task_id=runtime.task_id,
            user_goal=runtime.user_goal,
            assistant_meta=runtime.assistant_meta,
            query_meta={**runtime.query_request_meta, **runtime.query_result_meta},
            report_meta={**runtime.report_request_meta, **runtime.report_result_meta},
            mail_meta={**runtime.mail_request_meta, **runtime.mail_result_meta},
        )
        result = ScenarioResult(
            status="denied",
            title=profile.deny_title,
            detail=reason_text or profile.deny_detail,
            task_id=runtime.task_id,
            reason_code=reason_code,
        )
        return result, self._build_payload(runtime, result)

    def _finalize_success(self, profile: ScenarioProfile, runtime: FlowRuntime) -> tuple[ScenarioResult, dict[str, object]]:
        self.delegation_manager.revoke_for_task(runtime.task_id, reason="task_completed_cleanup")
        self._append_trace(runtime, "task_finalize", "success", profile.success_reason_code, "多智能体办公链路执行完成。")
        self.audit_ledger.record(
            event_type="task_lifecycle",
            task_id=runtime.task_id,
            principal="user:xiaoming",
            action="task_finalize",
            resource="task:sales_report",
            decision="allow",
            reason="real collaboration completed",
            metadata={"reason_code": profile.success_reason_code},
        )
        self.assistant_agent.update_runtime_status(
            task_id=runtime.task_id,
            user_goal=runtime.user_goal,
            assistant_meta=runtime.assistant_meta,
            query_meta={**runtime.query_request_meta, **runtime.query_result_meta},
            report_meta={**runtime.report_request_meta, **runtime.report_result_meta},
            mail_meta={**runtime.mail_request_meta, **runtime.mail_result_meta},
        )
        result = ScenarioResult(
            status="success",
            title=profile.success_title,
            detail=f"已完成销售数据查询、报表生成并发送给授权经理。输出文件：{runtime.output_name or '-'}",
            task_id=runtime.task_id,
            reason_code=profile.success_reason_code,
        )
        return result, self._build_payload(runtime, result)

    def _build_payload(self, runtime: FlowRuntime, result: ScenarioResult) -> dict[str, object]:
        return {
            "scenario": runtime.scenario,
            "task_id": runtime.task_id,
            "task_file_path": runtime.task_file_path,
            "user_goal": runtime.user_goal,
            "status": result.status,
            "reason_code": result.reason_code,
            "reason_text": result.detail,
            "assistant_plan": runtime.assistant_plan,
            "query_request": runtime.query_request,
            "query_result": runtime.query_result,
            "report_request": runtime.report_request,
            "report_result": runtime.report_result,
            "mail_request": runtime.mail_request,
            "mail_result": runtime.mail_result,
            "query_resource": runtime.query_resource,
            "query_ttl_seconds": runtime.query_ttl_seconds,
            "report_ttl_seconds": runtime.report_ttl_seconds,
            "mail_ttl_seconds": runtime.mail_ttl_seconds,
            "planned_recipient": str(runtime.assistant_plan.get("recipient", "")).strip(),
            "final_recipient": str(runtime.mail_request.get("requested_target", "")).strip(),
            "report_output_name": runtime.output_name,
            "report_output_path": runtime.output_path,
            "failure_stage": runtime.failure_stage,
            "failure_reason": runtime.failure_reason,
            "assistant_latency": runtime.assistant_meta.get("latency_ms"),
            "query_latency": runtime.query_result_meta.get("latency_ms"),
            "report_latency": runtime.report_result_meta.get("latency_ms"),
            "mail_latency": runtime.mail_result_meta.get("latency_ms"),
            "work_trace": runtime.work_trace,
            "task_summary": shorten(result.detail, width=180, placeholder="..."),
        }
