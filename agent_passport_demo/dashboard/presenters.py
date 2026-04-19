from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from textwrap import shorten
from urllib.parse import urlencode


class DashboardPresenterMixin:
    def _detail_list(self, rows: list[tuple[str, str]]) -> str:
        items = "".join(
            "<div class='detail-row'>"
            f"<span class='detail-key'>{html.escape(label)}</span>"
            f"<span class='detail-value'>{html.escape(value)}</span>"
            "</div>"
            for label, value in rows
        )
        return f"<div class='detail-list'>{items}</div>"

    def _bullet_group(self, title: str, items: list[str], *, empty_text: str = "-") -> str:
        content = "".join(f"<li>{html.escape(item)}</li>" for item in items if str(item).strip())
        if not content:
            content = f"<li>{html.escape(empty_text)}</li>"
        return (
            "<section class='summary-group'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<ul>{content}</ul>"
            "</section>"
        )

    def _reason_label(self, reason: str) -> str:
        mapping = {
            "task_completed": "任务按计划完成",
            "benchmark_completed": "批量验证完成",
            "task_started": "任务已发起",
            "task_finalized": "任务已结束",
            "resource_not_in_scope": "申请资源超出本次任务范围",
            "target_not_in_scope": "发送目标超出本次任务范围",
            "target_mismatch": "发送目标超出本次任务范围",
            "delegation_revoked": "上游委托已撤销",
            "delegation_issued": "委托签发完成",
            "delegation_valid": "委托校验通过",
            "root_permission_revoked": "根权限已撤销",
            "delegation_exhausted": "委托已被消费，不能重复使用",
            "capability_signature_invalid": "能力令牌签名无效",
            "capability_invalid_signature": "能力令牌签名无效",
            "capability_invalid": "能力令牌校验失败",
            "capability_expired": "能力令牌已过期",
            "capability_not_yet_valid": "能力令牌尚未生效",
            "capability_iat_out_of_range": "能力令牌签发时间异常",
            "capability_missing_claim": "能力令牌字段缺失",
            "capability_invalid_audience": "能力令牌适用对象不匹配",
            "approval_required": "高风险发送缺少审批",
            "approval_missing": "未提供审批票据",
            "replay_detected": "发现重复使用已消费委托",
            "llm_disabled": "在线模型服务未启用",
            "missing_api_key": "未配置在线模型密钥",
            "assistant_failed": "个人助理阶段执行失败",
            "query_failed": "数据查询阶段执行失败",
            "data_query_failed": "数据查询阶段执行失败",
            "report_failed": "报表生成阶段执行失败",
            "mail_failed": "邮件发送阶段执行失败",
        }
        return mapping.get(reason, reason or "-")

    def _event_label(self, event_type: str) -> str:
        return {
            "task_lifecycle": "任务流转",
            "delegation_issued": "委托签发",
            "access_check": "访问校验",
            "policy_change": "策略变更",
            "api_probe": "接口验证",
        }.get(event_type, event_type or "-")

    def _decision_label(self, decision: str) -> str:
        return {
            "allow": "允许执行",
            "deny": "已拦截",
            "pending": "待处理",
            "success": "成功",
            "error": "失败",
        }.get(decision, decision or "-")

    def _principal_label(self, principal: str) -> str:
        return {
            "agent:assistant": "个人助理智能体",
            "agent:data_query": "数据查询智能体",
            "agent:report": "报表生成智能体",
            "agent:mail": "邮件发送智能体",
            "user:xiaoming": "业务用户小明",
            "user:alice": "业务用户 alice",
            "policy-enforcement": "授权网关",
        }.get(principal, principal or "-")

    def _metric_cards(self, cards: list[tuple[str, str]]) -> str:
        return "".join(
            "<article class='metric-card'>"
            f"<span class='metric-label'>{html.escape(label)}</span>"
            f"<strong class='metric-value'>{html.escape(value)}</strong>"
            "</article>"
            for label, value in cards
        )

    def _status_label(self, status: str) -> str:
        return {
            "idle": "待运行",
            "success": "执行成功",
            "denied": "已拒绝",
            "error": "执行失败",
        }.get(status, status)

    def _status_class(self, status: str) -> str:
        return {
            "idle": "status-idle",
            "success": "status-allow",
            "denied": "status-deny",
            "error": "status-deny",
        }.get(status, "status-idle")

    def _scenario_label(self, name: str) -> str:
        return {
            "real_collaboration": "正常办公协作",
            "unauthorized_query": "跨部门数据越权",
            "wrong_recipient": "错误收件目标",
            "revoked_access": "撤权后访问验证",
            "replay_attack": "重放攻击验证",
            "tampered_token": "令牌签名篡改",
            "approval_missing": "审批缺失验证",
        }.get(name, name)

    def _top_summary_cards(
        self,
        *,
        result,
        benchmark_report: dict[str, object],
        delegations: list[dict[str, object]],
        audit_rows: list[dict[str, object]],
    ) -> str:
        if result and str(result.reason_code) == "benchmark_completed":
            cards = [
                ("最近运行", "批量安全评测"),
                ("通过率", str(benchmark_report.get("pass_rate", "0 / 0"))),
                ("拦截率", str(benchmark_report.get("blocked_rate", "0 / 0"))),
                ("用例数", str(benchmark_report.get("total", 0))),
            ]
            return self._metric_cards(cards)

        cards = [
            ("当前任务", "-" if not result else str(result.task_id)),
            ("任务状态", "待运行" if not result else self._status_label(str(result.status))),
            ("有效委托", str(len(delegations))),
            ("审计事件", str(len(audit_rows))),
        ]
        return self._metric_cards(cards)

    def _last_meta_line(self, result, benchmark_report: dict[str, object]) -> str:
        if not result:
            return "尚未运行任务。"
        if str(result.reason_code) == "benchmark_completed":
            return (
                f"最近一次评测：{benchmark_report.get('total', 0)} 个用例，"
                f"通过率 {benchmark_report.get('pass_rate', '0 / 0')}"
            )
        return f"当前任务 ID：{result.task_id}"

    def _agent_stage_cards(self, payload: dict[str, object]) -> str:
        plan = payload.get("assistant_plan") if isinstance(payload.get("assistant_plan"), dict) else {}
        query_request = payload.get("query_request") if isinstance(payload.get("query_request"), dict) else {}
        report_request = payload.get("report_request") if isinstance(payload.get("report_request"), dict) else {}
        query_result = payload.get("query_result") if isinstance(payload.get("query_result"), dict) else {}
        report_result = payload.get("report_result") if isinstance(payload.get("report_result"), dict) else {}
        mail_request = payload.get("mail_request") if isinstance(payload.get("mail_request"), dict) else {}
        mail_result = payload.get("mail_result") if isinstance(payload.get("mail_result"), dict) else {}
        failure_stage = str(payload.get("failure_stage", "")).strip()
        failure_reason = str(payload.get("failure_reason", "")).strip()

        if not any([plan, query_request, report_request, query_result, report_result, mail_request, mail_result, failure_stage]):
            cards = [
                ("个人助理智能体", "当前动作：等待接收任务", "阶段结果：待执行"),
                ("数据查询智能体", "当前动作：等待授权查询", "阶段结果：待执行"),
                ("报表生成智能体", "当前动作：等待数据结果", "阶段结果：待执行"),
                ("邮件发送智能体", "当前动作：等待最终发送请求", "阶段结果：待执行"),
            ]
            return "".join(
                "<article class='stack-card'>"
                f"<strong>{html.escape(title)}</strong>"
                f"<p>{html.escape(line1)}</p>"
                f"<p>{html.escape(line2)}</p>"
                "</article>"
                for title, line1, line2 in cards
            )

        plan_actions = plan.get("action_sequence") if isinstance(plan.get("action_sequence"), list) else []
        action_text = " -> ".join(str(item) for item in plan_actions) if plan_actions else "任务拆解 -> 授权协作"

        query_resource = str(query_request.get("requested_resource", "")).strip() or str(plan.get("dataset_resource", "")).strip() or "待分配"
        query_filter = str(query_request.get("query_filter", "")).strip() or "按任务目标筛选"
        report_name = str(payload.get("report_output_name", "")).strip() or str(report_result.get("title", "")).strip() or "待生成"
        report_summary = str(report_result.get("executive_summary", "")).strip() or "等待生成报表摘要"
        mail_target = str(mail_request.get("requested_target", "")).strip() or str(plan.get("recipient", "")).strip() or "待确认"
        mail_subject = str(mail_result.get("subject", "")).strip() or "待生成"

        assistant_latency = self._latency_label(payload.get("assistant_latency"))
        query_latency = self._latency_label(payload.get("query_latency"))
        report_latency = self._latency_label(payload.get("report_latency"))
        mail_latency = self._latency_label(payload.get("mail_latency"))

        cards = [
            (
                "个人助理智能体",
                f"当前动作：已完成任务拆解，协作路径为 {action_text}",
                f"阶段结果：查询 {str(plan.get('dataset_resource', '待分配'))}，发送至 {str(plan.get('recipient', '待确认'))}；时延 {assistant_latency if assistant_latency != '-' else '待记录'}",
            ),
            (
                "数据查询智能体",
                f"当前动作：处理授权查询，资源 {query_resource}，筛选 {query_filter}",
                (
                    f"阶段结果：已生成查询摘要；时延 {query_latency if query_latency != '-' else '待记录'}"
                    if query_result
                    else f"阶段结果：查询请求已就绪；时延 {query_latency if query_latency != '-' else '待记录'}"
                ),
            ),
            (
                "报表生成智能体",
                f"当前动作：生成报表产物，文件 {report_name}",
                f"阶段结果：{shorten(report_summary, width=86, placeholder='...')}；时延 {report_latency if report_latency != '-' else '待记录'}",
            ),
            (
                "邮件发送智能体",
                (
                    "当前动作：发送请求已被拦截"
                    if failure_stage.startswith("mail")
                    else f"当前动作：准备向 {mail_target} 发送，主题 {mail_subject}"
                ),
                (
                    f"阶段结果：{failure_reason or '安全控制已生效'}；时延 {mail_latency if mail_latency != '-' else '待记录'}"
                    if failure_stage.startswith("mail")
                    else (
                        f"阶段结果：已完成发送；时延 {mail_latency if mail_latency != '-' else '待记录'}"
                        if mail_result.get("delivery_record")
                        else f"阶段结果：等待最终发送请求；时延 {mail_latency if mail_latency != '-' else '待记录'}"
                    )
                ),
            ),
        ]

        return "".join(
            "<article class='stack-card'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<p>{html.escape(line1)}</p>"
            f"<p>{html.escape(line2)}</p>"
            "</article>"
            for title, line1, line2 in cards
        )

    def _assistant_plan_summary(self, payload: dict[str, object]) -> str:
        plan = payload.get("assistant_plan") if isinstance(payload.get("assistant_plan"), dict) else {}
        if not plan:
            return self._detail_list(
                [
                    ("任务状态", "等待发起办公任务"),
                    ("计划路径", "等待生成协作路径"),
                    ("查询资源", "等待分配查询范围"),
                    ("发送目标", "等待确认发送目标"),
                    ("审批要求", "待任务生成后确定"),
                ]
            )

        actions = plan.get("action_sequence") if isinstance(plan.get("action_sequence"), list) else []
        approval_required = plan.get("approval_required")
        if isinstance(approval_required, bool):
            approval_text = "需要审批" if approval_required else "按策略判断"
        else:
            approval_text = "待任务生成后确定"

        return self._detail_list(
            [
                ("任务状态", "协作计划已生成"),
                ("计划路径", " -> ".join(str(item) for item in actions) if actions else "等待生成协作路径"),
                ("查询资源", str(plan.get("dataset_resource", "")).strip() or "等待分配查询范围"),
                ("发送目标", str(plan.get("recipient", "")).strip() or "等待确认发送目标"),
                ("审批要求", approval_text),
            ]
        )

    def _query_result_summary(self, payload: dict[str, object]) -> str:
        result = payload.get("query_result") if isinstance(payload.get("query_result"), dict) else {}
        if not result:
            return self._detail_list(
                [
                    ("当前状态", "等待查询执行"),
                    ("结果摘要", "尚未返回结构化查询结果"),
                    ("核心指标", "待生成"),
                    ("关键发现", "待生成"),
                ]
            )

        metrics = result.get("metrics") if isinstance(result.get("metrics"), list) else []
        metric_lines = []
        for item in metrics:
            if not isinstance(item, dict):
                continue
            metric = str(item.get("name", "")).strip()
            value = str(item.get("value", "")).strip()
            if metric and value:
                metric_lines.append(f"{metric}: {value}")
        return (
            self._detail_list([("结果摘要", str(result.get("summary", "")).strip() or "尚未返回结构化查询结果")])
            + self._bullet_group("核心指标", metric_lines, empty_text="待生成")
            + self._bullet_group(
                "关键发现",
                [str(item) for item in result.get("highlights", [])] if isinstance(result.get("highlights"), list) else [],
                empty_text="待生成",
            )
        )

    def _report_result_summary(self, payload: dict[str, object]) -> str:
        result = payload.get("report_result") if isinstance(payload.get("report_result"), dict) else {}
        if not result:
            return self._detail_list(
                [
                    ("报表状态", "待生成"),
                    ("输出文件", "待生成"),
                    ("执行摘要", "等待报表生成智能体输出结果"),
                    ("关键结论", "待生成"),
                    ("风险提示", "待生成"),
                ]
            )

        output_name = str(payload.get("report_output_name", "")).strip() or "待生成"
        return (
            self._detail_list(
                [
                    ("报表标题", str(result.get("title", "")).strip() or "待生成"),
                    ("输出文件", output_name),
                    ("执行摘要", str(result.get("executive_summary", "")).strip() or "等待报表生成智能体输出结果"),
                ]
            )
            + self._bullet_group(
                "关键结论",
                [str(item) for item in result.get("key_findings", [])] if isinstance(result.get("key_findings"), list) else [],
                empty_text="待生成",
            )
            + self._bullet_group(
                "风险提示",
                [str(item) for item in result.get("risk_flags", [])] if isinstance(result.get("risk_flags"), list) else [],
                empty_text="待生成",
            )
        )

    def _mail_result_summary(self, payload: dict[str, object]) -> str:
        result = payload.get("mail_result") if isinstance(payload.get("mail_result"), dict) else {}
        request = payload.get("mail_request") if isinstance(payload.get("mail_request"), dict) else {}
        failure_stage = str(payload.get("failure_stage", "")).strip()
        failure_reason = str(payload.get("failure_reason", "")).strip()
        if failure_stage.startswith("mail"):
            return self._detail_list(
                [
                    ("发送状态", "发送请求已被拦截"),
                    ("目标邮箱", str(request.get("requested_target", "")).strip() or "待确认"),
                    ("风险说明", failure_reason or "发送请求未通过安全控制"),
                ]
            )

        if not result:
            return self._detail_list(
                [
                    ("发送状态", "等待最终发送请求"),
                    ("目标邮箱", "待确认"),
                    ("邮件主题", "待生成"),
                    ("风险说明", "待发送阶段输出"),
                    ("邮件要点", "待生成"),
                ]
            )

        delivery = result.get("delivery_record") if isinstance(result.get("delivery_record"), dict) else {}
        return (
            self._detail_list(
                [
                    ("发送状态", "发送成功" if delivery else "等待最终发送请求"),
                    ("目标邮箱", str(request.get("requested_target", "")).strip() or "待确认"),
                    ("邮件主题", str(result.get("subject", "")).strip() or "待生成"),
                    ("风险说明", str(result.get("risk_note", "")).strip() or "待发送阶段输出"),
                ]
            )
            + self._bullet_group(
                "邮件要点",
                [str(item) for item in result.get("bullets", [])] if isinstance(result.get("bullets"), list) else [],
                empty_text="待生成",
            )
        )

    def _decision_request_summary(self, payload: dict[str, object]) -> str:
        subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        return self._detail_list(
            [
                ("执行主体", self._principal_label(str(subject.get("id", "-")))),
                ("申请动作", str(action.get("name", "-")) or "-"),
                ("目标资源", str(resource.get("id", "-")) or "-"),
                ("任务编号", str(context.get("task_id", "-")) or "-"),
                ("是否消耗委托", "是" if bool(context.get("consume")) else "否"),
                ("审计级别", str(context.get("audit_mode", "-")) or "-"),
            ]
        )

    def _decision_response_summary(self, payload: dict[str, object]) -> str:
        return self._detail_list(
            [
                ("处理结果", self._decision_label(str(payload.get("decision", "-")))),
                ("业务说明", str(payload.get("reason_text", "-")) or "-"),
                ("控制原因", self._reason_label(str(payload.get("reason", payload.get("reason_code", "-"))))),
                ("是否写入审计", "是" if bool(payload.get("audited", True)) else "否"),
            ]
        )

    def _failure_panel(self, payload: dict[str, object]) -> str:
        stage = str(payload.get("failure_stage", "")).strip()
        reason = str(payload.get("failure_reason", "")).strip()
        if not stage and not reason:
            return ""
        return (
            "<article class='stack-card'>"
            "<strong>异常结果</strong>"
            f"<p>阶段：{html.escape(self._failure_stage_label(stage or '-'))}</p>"
            f"<p>原因：{html.escape(reason or '-')}</p>"
            "</article>"
        )

    def _security_validation_cards(self) -> str:
        latest_by_scenario: dict[str, dict[str, str]] = {}
        for row in self.run_history:
            scenario = str(row.get("scenario", ""))
            if scenario and scenario not in latest_by_scenario:
                latest_by_scenario[scenario] = row

        targets = ["unauthorized_query", "wrong_recipient", "revoked_access", "replay_attack", "tampered_token", "approval_missing"]
        cards: list[str] = []
        for scenario in targets:
            row = latest_by_scenario.get(scenario)
            status = "未运行" if row is None else self._status_label(str(row.get("status", "")))
            cards.append(
                "<article class='stack-card'>"
                f"<strong>{html.escape(self._scenario_label(scenario))}</strong>"
                f"<p>最近状态：{html.escape(status)}</p>"
                "</article>"
            )
        return "".join(cards)

    def _overview_capability_cards(self) -> str:
        cards = [
            ("智能体独立身份", "每个智能体以独立工作负载身份执行任务，身份与能力分离管理。"),
            ("最小权限授权", "不同智能体仅拥有完成当前职责所需的最小权限。"),
            ("一次性委托令牌", "任务级能力令牌默认单次消费，用后失效，阻断重放攻击。"),
            ("全链路审计追踪", "从任务发起到委托签发、访问校验、发送结果全程可追溯。"),
        ]
        return "".join(
            "<article class='capability-card'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<p>{html.escape(detail)}</p>"
            "</article>"
            for title, detail in cards
        )

    def _task_focus_summary(self, *, payload: dict[str, object], result) -> str:
        plan = payload.get("assistant_plan") if isinstance(payload.get("assistant_plan"), dict) else {}
        task_id = str(payload.get("task_id", "")).strip() or (str(result.task_id) if result else "")
        has_task = bool(task_id or result)

        if has_task:
            task_id_text = task_id or "尚未生成"
            status_text = self._status_label(str(result.status)) if result else "待运行"
            plan_goal = str(payload.get("user_goal", "")).strip() or "等待补充任务目标"
            query_resource = str(plan.get("dataset_resource", "")).strip() or "等待任务分配查询范围"
            target_text = str(plan.get("recipient", "")).strip() or "等待确认发送目标"
            final_result = str(result.detail).strip() if result else "暂无结果"
            final_result_text = shorten(final_result, width=120, placeholder="...") if final_result else "暂无结果"
        else:
            task_id_text = "尚未生成"
            status_text = "待运行"
            plan_goal = "等待发起办公任务"
            query_resource = "等待任务分配查询范围"
            target_text = "等待确认发送目标"
            final_result_text = "暂无结果"

        return self._detail_list(
            [
                ("当前任务编号", task_id_text),
                ("当前任务状态", status_text),
                ("计划目标", plan_goal),
                ("查询资源", query_resource),
                ("目标收件人", target_text),
                ("最终结果", final_result_text),
            ]
        )

    def _agent_scope_cards(self) -> str:
        profiles = [
            {
                "name": "个人助理智能体",
                "role": "负责拆解任务并签发下游委托",
                "allow": "任务拆解、签发 query / generate_report / send_mail 委托",
                "deny": "直接读取业务数据、直接生成报表内容、直接发送邮件",
                "scope": "仅可处理任务计划与委托流转，不直接访问业务资源",
            },
            {
                "name": "数据查询智能体",
                "role": "负责执行授权数据查询",
                "allow": "消费 query 委托并查询授权数据集",
                "deny": "生成报表、发送邮件、扩展查询资源范围",
                "scope": "默认仅访问 assistant_plan 指定的数据集",
            },
            {
                "name": "报表生成智能体",
                "role": "负责消费查询结果并生成报表",
                "allow": "消费 generate_report 委托，写入周报工件",
                "deny": "回查数据库、修改查询范围、直接发送邮件",
                "scope": "仅可处理查询结果与目标报表工件",
            },
            {
                "name": "邮件发送智能体",
                "role": "负责发送最终报表",
                "allow": "消费 send_mail 委托向授权目标发送邮件",
                "deny": "改写收件目标、改写查询条件、回溯读取业务数据",
                "scope": "仅可访问授权收件目标与最终报表内容",
            },
        ]

        return "".join(
            "<article class='scope-card'>"
            f"<h3>{html.escape(profile['name'])}</h3>"
            f"<p><strong>角色职责：</strong>{html.escape(profile['role'])}</p>"
            f"<p><strong>允许动作：</strong>{html.escape(profile['allow'])}</p>"
            f"<p><strong>禁止动作：</strong>{html.escape(profile['deny'])}</p>"
            f"<p><strong>默认访问范围：</strong>{html.escape(profile['scope'])}</p>"
            "</article>"
            for profile in profiles
        )

    def _token_summary_cards(self, rows: list[dict[str, object]]) -> str:
        issued = len(rows)
        revoked = sum(1 for row in rows if bool(row.get("revoked")))
        exhausted = sum(
            1
            for row in rows
            if (not bool(row.get("revoked"))) and int(row.get("uses", 0)) >= int(row.get("max_uses", 0))
        )
        active = sum(
            1
            for row in rows
            if (not bool(row.get("revoked"))) and int(row.get("uses", 0)) < int(row.get("max_uses", 0))
        )
        return self._metric_cards(
            [
                ("已签发委托", str(issued)),
                ("已耗尽委托", str(exhausted)),
                ("当前有效委托", str(active)),
                ("已撤销委托", str(revoked)),
            ]
        )

    def _agent_identity_cards(self) -> str:
        identities = sorted(self.identities, key=lambda item: item.principal)
        if not identities:
            return "<article class='scope-card'><h3>暂无身份信息</h3><p>运行任务后展示智能体身份摘要。</p></article>"

        return "".join(
            "<article class='scope-card'>"
            f"<h3>{html.escape(self._principal_label(identity.principal))}</h3>"
            f"<p><strong>主体 ID：</strong>{html.escape(identity.principal)}</p>"
            "<p><strong>身份类型：</strong>工作负载身份</p>"
            f"<p><strong>认证凭证摘要：</strong>{html.escape(self._mask_token(identity.auth_token) if identity.auth_token else '-')}</p>"
            f"<p><strong>信任范围：</strong>{html.escape(f'企业办公系统信任域 / {identity.owner_user}')}</p>"
            f"<p><strong>默认能力：</strong>{html.escape(self._identity_default_capability(identity.principal))}</p>"
            "</article>"
            for identity in identities
        )

    def _identity_default_capability(self, principal: str) -> str:
        return {
            "agent:assistant": "拆解任务并签发下游委托，不直接触达业务资源",
            "agent:data_query": "在授权范围内查询业务数据，不生成报表和邮件",
            "agent:report": "消费查询结果并生成报表，不回查数据库",
            "agent:mail": "向授权目标发送最终报表，不改写查询范围",
        }.get(principal, "按策略控制执行最小动作")

    def _benchmark_objective_label(self, text: str) -> str:
        return (
            text.replace("Agent", "智能体")
            .replace("capability token", "能力令牌")
            .replace("capability", "能力")
        )

    def _resource_display_name(self, resource_id: str) -> str:
        return {
            "dataset:sales_week15": "销售部第 15 周业务数据",
            "dataset:finance_sensitive": "财务敏感数据集",
            "doc:project_a": "项目 A 周报",
            "doc:release_notes": "发布说明文档",
            "doc:finance_b": "财务 B 敏感文档",
            "doc:risk_review": "风险评审纪要",
            "sheet:project_a": "项目 A 指标表",
            "artifact:weekly_sales_report": "周报输出文件",
            "chat:group_a": "项目 A 工作群",
            "chat:group_b": "错误收件群组",
            "mail:manager_zhang": "张经理邮箱",
            "mail:finance_group": "财务群邮箱",
            "tool:report_writer": "报表生成工具",
            "tool:mail_sender": "邮件发送工具",
        }.get(resource_id, resource_id or "-")

    def _resource_type_label(self, resource_type: str) -> str:
        return {
            "dataset": "数据集",
            "document": "文档",
            "sheet": "表格",
            "chat": "群组",
            "mailbox": "邮箱",
            "tool": "工具",
            "artifact": "产物",
        }.get(resource_type, resource_type or "-")

    def _project_label(self, project: str) -> str:
        return {
            "sales_ops": "销售运营",
            "finance_ops": "财务运营",
            "project_a": "项目 A",
            "ops_bridge": "运营桥接",
            "platform": "平台能力",
        }.get(project, project or "-")

    def _sensitivity_label(self, sensitivity: str) -> str:
        return {
            "internal": "内部",
            "restricted": "受限",
            "secret": "高敏",
        }.get(sensitivity, sensitivity or "-")

    def _action_label(self, action: str) -> str:
        return {
            "read": "读取",
            "query": "查询",
            "summarize": "生成摘要",
            "send": "发送消息",
            "send_mail": "发送邮件",
            "generate_report": "生成报表",
            "delegate": "签发委托",
            "export": "导出",
        }.get(action, action or "-")

    def _actions_html(self, raw_actions: str) -> str:
        actions = [item.strip() for item in raw_actions.split(",") if item.strip()]
        if not actions:
            return "-"
        return "".join(
            f"<span class='cell-tag'>{html.escape(self._action_label(action))}</span>"
            for action in actions
        )

    def _audit_action_text(self, action: str) -> str:
        return {
            "task_start": "发起任务",
            "task_finalize": "结束任务",
        }.get(action, self._action_label(action))

    def _resource_description(self, resource_id: str, description: str) -> str:
        normalized = (
            description.replace("target mismatch", "目标不匹配")
            .replace("Agent", "智能体")
            .replace("capability token", "能力令牌")
            .replace("capability", "能力")
        )
        return {
            "dataset:sales_week15": "销售任务可查询的数据集，仅允许在销售范围内使用。",
            "dataset:finance_sensitive": "财务高敏数据集，用于验证跨部门越权查询拦截。",
            "doc:project_a": "项目周报文档，包含任务进展、权限模型与发布协同信息。",
            "doc:release_notes": "版本发布说明文档，用于生成摘要和发送结果。",
            "doc:finance_b": "财务敏感文档，默认不在项目 A 授权范围内。",
            "doc:risk_review": "风险评审纪要，记录主要风险与控制项。",
            "sheet:project_a": "项目指标表，用于发布阶段的数据核对。",
            "artifact:weekly_sales_report": "报表产物文件，仅允许写入本次任务生成结果。",
            "chat:group_a": "项目 A 工作群，用于发送任务摘要。",
            "chat:group_b": "错误收件群组，用于验证目标边界拦截。",
            "mail:manager_zhang": "授权收件邮箱，用于正常发送场景。",
            "mail:finance_group": "未授权收件邮箱，用于验证目标边界拦截。",
            "tool:report_writer": "报表生成工具入口。",
            "tool:mail_sender": "邮件发送工具入口。",
        }.get(resource_id, normalized or "-")

    def _resource_identity_html(self, resource_id: str) -> str:
        return (
            f"<div><strong>{html.escape(self._resource_display_name(resource_id))}</strong>"
            f"<div class='table-note'>资源 ID：{html.escape(resource_id or '-')}</div></div>"
        )

    def _principal_display_html(self, principal: str) -> str:
        return (
            f"<div><strong>{html.escape(self._principal_label(principal))}</strong>"
            f"<div class='table-note'>主体 ID：{html.escape(principal or '-')}</div></div>"
        )

    def _benchmark_summary_cards(self, report: dict[str, object]) -> str:
        cards = [
            ("用例总数", str(report.get("total", 0))),
            ("符合预期", str(report.get("passed_count", 0))),
            ("通过率", str(report.get("pass_rate", "0 / 0"))),
            ("拦截率", str(report.get("blocked_rate", "0 / 0"))),
        ]
        return self._metric_cards(cards)

    def _benchmark_rows(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>尚未执行批量评测。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{html.escape(str(row.get('title', '-')))}</td>"
            f"<td>{html.escape(str(row.get('category', '-')))}</td>"
            f"<td>{html.escape(self._benchmark_objective_label(str(row.get('expected_outcome', '-'))))}</td>"
            f"<td>{html.escape(self._status_label(str(row.get('actual_status', '-'))))}</td>"
            f"<td>{html.escape(self._reason_label(str(row.get('actual_reason_code', '-'))))}</td>"
            f"<td>{html.escape(str(row.get('task_id', '-')))}</td>"
            f"<td>{'符合预期' if bool(row.get('passed')) else '不符合预期'}</td>"
            f"<td>{html.escape(self._benchmark_objective_label(str(row.get('objective', '-'))))}</td>"
            "</tr>"
            for row in rows
        )

    def _resource_rows(self, resources: list[dict[str, str]]) -> str:
        if not resources:
            return "<tr><td colspan='6'>暂无资源记录。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{self._resource_identity_html(str(row.get('resource_id', '-')))}</td>"
            f"<td><span class='cell-tag'>{html.escape(self._resource_type_label(str(row.get('resource_type', '-'))))}</span></td>"
            f"<td>{html.escape(self._project_label(str(row.get('project', '-'))))}</td>"
            f"<td><span class='cell-tag'>{html.escape(self._sensitivity_label(str(row.get('sensitivity', '-'))))}</span></td>"
            f"<td><div class='pill-row'>{self._actions_html(str(row.get('allowed_actions', '-')))}</div></td>"
            f"<td>{html.escape(self._resource_description(str(row.get('resource_id', '-')), str(row.get('description', '-'))))}</td>"
            "</tr>"
            for row in resources
        )

    def _policy_rows(self, rows: list[dict[str, str]]) -> str:
        if not rows:
            return "<tr><td colspan='6'>暂无策略记录。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{self._principal_display_html(str(row.get('principal', '-')))}</td>"
            f"<td><span class='cell-tag'>{html.escape(self._action_label(str(row.get('action', '-'))))}</span></td>"
            f"<td>{self._resource_identity_html(str(row.get('resource', '-')))}</td>"
            f"<td><span class='cell-tag'>{html.escape(self._resource_type_label(str(row.get('resource_type', '-'))))}</span></td>"
            f"<td><span class='cell-tag'>{html.escape(self._sensitivity_label(str(row.get('sensitivity', '-'))))}</span></td>"
            f"<td><span class='cell-tag'>{html.escape(self._decision_label(str(row.get('effect', '-'))))}</span></td>"
            "</tr>"
            for row in rows
        )

    def _relationship_graph(self, resources: list[dict[str, str]]) -> str:
        return (
            "<div class='stack-list'>"
            "<article class='stack-card'><strong>个人助理智能体</strong><p>负责拆解办公任务并签发下游任务级委托。</p></article>"
            "<article class='stack-card'><strong>数据查询智能体</strong><p>只能查询授权数据集，不能直接发送结果。</p></article>"
            "<article class='stack-card'><strong>报表生成智能体</strong><p>只能把查询结果生成报表工件，不能回查数据库。</p></article>"
            "<article class='stack-card'><strong>邮件发送智能体</strong><p>只能向授权收件目标发送带审批的最终报表。</p></article>"
            f"<article class='stack-card'><strong>资源范围</strong><p>当前有 {len(resources)} 个受控资源纳入策略控制。</p></article>"
            "</div>"
        )

    def _delegation_rows(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return "<tr><td colspan='10'>暂无委托记录。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{html.escape(str(row.get('delegation_id', '-')))}</td>"
            f"<td>{html.escape(str(row.get('capability_token_preview', '-')))}</td>"
            f"<td>{html.escape(str(row.get('task_id', '-')))}</td>"
            f"<td>{html.escape(str(row.get('to_principal', '-')))}</td>"
            f"<td>{html.escape(str(row.get('action', '-')))}</td>"
            f"<td>{html.escape(str(row.get('resource', '-')))}</td>"
            f"<td>{html.escape(self._approval_text(row))}</td>"
            f"<td>{html.escape(self._token_usage_text(row))}</td>"
            f"<td>{html.escape(self._token_remaining_text(row))}</td>"
            f"<td>{html.escape(self._token_state_label(row))}</td>"
            "</tr>"
            for row in rows
        )

    def _token_usage_text(self, row: dict[str, object]) -> str:
        uses = max(0, int(row.get("uses", 0)))
        max_uses = max(1, int(row.get("max_uses", 0)))
        return f"已使用 {uses} / {max_uses}"

    def _token_remaining_text(self, row: dict[str, object]) -> str:
        if bool(row.get("revoked")):
            return "-"
        uses = max(0, int(row.get("uses", 0)))
        max_uses = max(1, int(row.get("max_uses", 0)))
        remaining = max(max_uses - uses, 0)
        return f"剩余 {remaining} 次"

    def _message_rows(self, rows: list[dict[str, str]] | None = None) -> str:
        rows = self.data_store.sent_messages if rows is None else rows
        if not rows:
            return "<tr><td colspan='3'>暂无已发送消息。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{html.escape(self._format_display_time(row.get('created_at', '')))}</td>"
            f"<td>{html.escape(str(row.get('target', '-')))}</td>"
            f"<td>{html.escape(str(row.get('content', '-')))}</td>"
            "</tr>"
            for row in rows
        )

    def _audit_rows(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return "<tr><td colspan='6'>当前筛选条件下暂无审计事件。</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{html.escape(self._format_display_time(row.get('timestamp', '')))}</td>"
            f"<td>{html.escape(str(row.get('task_id', '-')))}</td>"
            f"<td>{html.escape(self._event_label(str(row.get('event_type', '-'))))}</td>"
            f"<td>{html.escape(self._decision_label(str(row.get('decision', '-'))))}</td>"
            f"<td>{html.escape(self._timeline_summary(row))}</td>"
            f"<td>{html.escape(self._reason_label(str(row.get('reason_code', '-'))))}</td>"
            "</tr>"
            for row in rows
        )

    def _delegation_task_cards(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return "<article class='task-audit-card'><strong>暂无委托记录</strong><p>运行任务后会按任务展示委托链。</p></article>"

        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            task_id = str(row.get("task_id", "") or "-")
            grouped.setdefault(task_id, []).append(row)

        def sort_key(item: tuple[str, list[dict[str, object]]]) -> tuple[str, str]:
            task_id, items = item
            latest = ""
            for entry in items:
                latest = max(latest, str(entry.get("created_at", entry.get("timestamp", ""))))
            return (latest, task_id)

        cards: list[str] = []
        for task_id, items in sorted(grouped.items(), key=sort_key, reverse=True):
            cards.append(self._delegation_task_card(task_id, items))
        return "".join(cards)

    def _delegation_task_card(self, task_id: str, rows: list[dict[str, object]]) -> str:
        task_name = self._audit_task_name(task_id, [])
        active_count = sum(1 for row in rows if self._token_state_label(row) == "可用中")
        used_count = sum(1 for row in rows if self._token_state_label(row) == "已耗尽")
        revoked_count = sum(1 for row in rows if self._token_state_label(row) == "已撤销")
        lines = "".join(
            "<li class='task-audit-event'>"
            f"<span class='task-audit-time'>{html.escape(self._delegation_kind_label(str(row.get('action', ''))))}</span>"
            f"<span class='task-audit-type'>{html.escape(self._principal_label(str(row.get('to_principal', '-'))))}</span>"
            f"<span class='task-audit-decision'>{html.escape(self._token_state_label(row))}</span>"
            f"<span class='task-audit-summary'>{html.escape(self._delegation_summary(row))}</span>"
            "</li>"
            for row in rows
        )
        latest_status = self._delegation_task_status(rows)
        return (
            "<article class='task-audit-card'>"
            "<div class='task-audit-head'>"
            f"<div><strong>{html.escape(task_name)}</strong><div class='table-note'>任务编号：{html.escape(task_id)} | 委托 {len(rows)} 条，已使用 {used_count} 条，可用 {active_count} 条，已撤销 {revoked_count} 条</div></div>"
            f"<span class='badge {self._status_class(latest_status[1])}'>{html.escape(latest_status[0])}</span>"
            "</div>"
            f"<div class='task-audit-reason'>委托链覆盖查询、报表生成和邮件发送三个执行阶段。</div>"
            f"<ul class='task-audit-events'>{lines}</ul>"
            "</article>"
        )

    def _delegation_kind_label(self, action: str) -> str:
        return {
            "query": "查询委托",
            "generate_report": "报表委托",
            "send_mail": "发送委托",
        }.get(action, f"{self._action_label(action)}委托")

    def _delegation_summary(self, row: dict[str, object]) -> str:
        action = self._action_label(str(row.get("action", "")))
        resource = self._resource_display_name(str(row.get("resource", "")))
        approval = self._approval_text(row)
        return f"允许{action}：{resource}；审批要求：{approval}"

    def _delegation_task_status(self, rows: list[dict[str, object]]) -> tuple[str, str]:
        if any(self._token_state_label(row) == "可用中" for row in rows):
            return ("存在待执行委托", "success")
        if any(self._token_state_label(row) == "已撤销" for row in rows):
            return ("包含已撤销委托", "denied")
        return ("委托已完成消费", "success")

    def _audit_task_cards(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return "<article class='task-audit-card'><strong>暂无审计记录</strong><p>请先运行一个任务或调整筛选条件。</p></article>"

        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            task_id = str(row.get("task_id", "") or "-")
            grouped.setdefault(task_id, []).append(row)

        cards: list[str] = []
        for task_id, events in grouped.items():
            cards.append(self._audit_task_card(task_id, events))
        return "".join(cards)

    def _audit_task_card(self, task_id: str, rows: list[dict[str, object]]) -> str:
        latest = rows[-1]
        allow_count = sum(1 for row in rows if str(row.get("decision", "")) == "allow")
        deny_count = sum(1 for row in rows if str(row.get("decision", "")) == "deny")
        status_label, status_class = self._audit_task_status(rows)
        reason_label = self._reason_label(str(latest.get("reason_code", "")))
        task_name = self._audit_task_name(task_id, rows)
        event_lines = "".join(
            "<li class='task-audit-event'>"
            f"<span class='task-audit-time'>{html.escape(self._format_display_time(row.get('timestamp', '')))}</span>"
            f"<span class='task-audit-type'>{html.escape(self._event_label(str(row.get('event_type', '-'))))}</span>"
            f"<span class='task-audit-decision'>{html.escape(self._decision_label(str(row.get('decision', '-'))))}</span>"
            f"<span class='task-audit-summary'>{html.escape(self._timeline_summary(row))}</span>"
            "</li>"
            for row in rows
        )
        return (
            "<article class='task-audit-card'>"
            "<div class='task-audit-head'>"
            f"<div><strong>{html.escape(task_name)}</strong><div class='table-note'>任务编号：{html.escape(task_id)} | 共 {len(rows)} 条审计事件，允许 {allow_count} 条，拦截 {deny_count} 条</div></div>"
            f"<span class='badge {status_class}'>{html.escape(status_label)}</span>"
            "</div>"
            f"<div class='task-audit-reason'>最新控制结论：{html.escape(reason_label)}</div>"
            f"<ul class='task-audit-events'>{event_lines}</ul>"
            "</article>"
        )

    def _audit_task_status(self, rows: list[dict[str, object]]) -> tuple[str, str]:
        latest = rows[-1] if rows else {}
        latest_decision = str(latest.get("decision", ""))
        latest_event = str(latest.get("event_type", ""))
        latest_action = str(latest.get("action", ""))
        if latest_event == "task_lifecycle" and latest_action == "task_finalize":
            if latest_decision == "allow":
                return "任务完成", "success"
            if latest_decision == "deny":
                return "任务已拦截", "denied"
        if latest_decision == "deny":
            return "执行被拦截", "denied"
        return "继续执行", "success"

    def _audit_task_name(self, task_id: str, rows: list[dict[str, object]]) -> str:
        for row in self.run_history:
            if str(row.get("task_id", "")) == task_id:
                scenario = str(row.get("scenario", "")).strip()
                if scenario:
                    return self._scenario_label(scenario)

        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            summary = str(metadata.get("summary", "")).strip()
            if summary:
                if "销售部业绩报表" in summary:
                    return "销售周报生成与发送"
                if "财务" in summary:
                    return "财务越权访问验证"
                return summary[:24]

        return "未命名任务"

    def _audit_summary_cards(self, rows: list[dict[str, object]]) -> str:
        allow_count = sum(1 for row in rows if str(row.get("decision", "")) == "allow")
        deny_count = sum(1 for row in rows if str(row.get("decision", "")) == "deny")
        lifecycle_count = sum(1 for row in rows if str(row.get("event_type", "")) == "task_lifecycle")
        delegation_count = sum(1 for row in rows if str(row.get("event_type", "")) == "delegation_issued")
        access_count = sum(1 for row in rows if str(row.get("event_type", "")) == "access_check")
        policy_change_count = sum(1 for row in rows if str(row.get("event_type", "")) == "policy_change")
        return self._metric_cards(
            [
                ("允许事件", str(allow_count)),
                ("拦截事件", str(deny_count)),
                ("任务流转", str(lifecycle_count)),
                ("委托签发", str(delegation_count)),
                ("访问校验", str(access_count)),
                ("策略变更", str(policy_change_count)),
            ]
        )

    def _run_history_cards(self) -> str:
        if not self.run_history:
            return "<article class='stack-card'><strong>暂无运行记录</strong><p>请先运行一个场景以生成历史。</p></article>"
        return "".join(
            "<article class='run-card'>"
            f"<div class='run-card-head'><strong>{html.escape(self._scenario_label(str(row.get('scenario', '-'))))}</strong>"
            f"<span class='badge {self._status_class(str(row.get('status', 'idle')))}'>{html.escape(self._status_label(str(row.get('status', 'idle'))))}</span></div>"
            f"<div class='run-card-meta'>任务编号：{html.escape(str(row.get('task_id', '-')))}</div>"
            f"<div class='run-card-meta'>{html.escape(self._format_display_time(row.get('finished_at', '')))}</div>"
            "</article>"
            for row in self.run_history[:8]
        )

    def _timeline_items(self, rows: list[dict[str, object]], *, limit: int | None = None) -> str:
        items = rows[-limit:] if limit is not None else rows
        if not items:
            return "<div class='timeline-empty'><strong>暂无审计事件</strong></div>"
        return "".join(
            "<article class='timeline-item'>"
            f"<div class='timeline-head'><span class='timeline-type'>{html.escape(self._event_label(str(row.get('event_type', '-'))))}</span>"
            f"<span class='badge {self._status_class('success' if str(row.get('decision', 'deny')) == 'allow' else 'denied')}'>{html.escape(self._decision_label(str(row.get('decision', '-'))))}</span></div>"
            f"<div class='timeline-main'>{html.escape(self._timeline_summary(row))}</div>"
            f"<div class='timeline-meta'>任务编号：{html.escape(str(row.get('task_id', '-')))} | {html.escape(self._format_display_time(row.get('timestamp', '')))}</div>"
            "</article>"
            for row in items
        )

    def _timeline_summary(self, row: dict[str, object]) -> str:
        event_type = str(row.get("event_type", ""))
        principal = str(row.get("principal", ""))
        action = str(row.get("action", ""))
        resource = str(row.get("resource_id", row.get("resource", "")))
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        action_text = self._audit_action_text(action)
        resource_text = self._resource_display_name(resource) if resource else "-"

        if event_type == "task_lifecycle":
            if action == "task_start":
                task_goal = str(metadata.get("summary", "")).strip()
                if task_goal:
                    return f"{self._principal_label(principal)}发起任务：{task_goal}"
                return f"{self._principal_label(principal)}发起任务：{resource_text}"

            if action == "task_finalize":
                final_state = "已完成" if str(row.get("decision", "")) == "allow" else "已拦截"
                reason = self._reason_label(str(row.get("reason_code", "")))
                return f"{self._principal_label(principal)}结束任务，结果{final_state}（{reason}）"

            return f"{self._principal_label(principal)}更新任务状态：{action_text or '-'}"

        if event_type == "delegation_issued":
            to_principal = str(metadata.get("to_principal", "")).strip()
            if to_principal:
                to_label = self._principal_label(to_principal)
                return f"{self._principal_label(principal)}向{to_label}签发委托：{action_text} {resource_text}"
            return f"{self._principal_label(principal)}签发委托：{action_text} {resource_text}"

        if event_type == "access_check":
            return f"{self._principal_label(principal)}申请执行：{action_text} {resource_text}"

        if event_type == "policy_change":
            return f"{self._principal_label(principal)}调整策略：{action_text} {resource_text}"

        return f"{self._principal_label(principal)}执行：{action_text} {resource_text}"

    def _audit_filter_links(self, filter_state: dict[str, str]) -> str:
        links = [
            ("全部事件", {"task": "all"}),
            ("仅看拒绝", {"decision": "deny"}),
            ("当前任务", {"task": "current"}),
            ("查询智能体", {"agent": "agent:data_query"}),
            ("邮件智能体", {"agent": "agent:mail"}),
        ]
        base_params = {
            "view": "details",
            "keyword": filter_state.get("keyword", ""),
            "time_range": filter_state.get("time_range", "all"),
        }
        return "".join(
            f"<a class='filter-link{' filter-link-active' if self._is_active_filter(filter_state, params) else ''}' href='/?{html.escape(urlencode({**base_params, **params}))}'>{html.escape(label)}</a>"
            for label, params in links
        )

    def _is_active_filter(self, filter_state: dict[str, str], params: dict[str, str]) -> bool:
        expected_task = params.get("task", "")
        if expected_task == "all":
            expected_task = ""
        if expected_task == "current":
            current_task = self._current_display_task_id()
            if not current_task:
                return False
            expected_task = current_task
        expected = {
            "task_id": expected_task,
            "principal": params.get("agent", ""),
            "decision": params.get("decision", ""),
        }
        return all(filter_state.get(key, "") == value for key, value in expected.items())

    def _current_filter_hint(self, filter_state: dict[str, str]) -> str:
        labels: list[str] = []
        if filter_state.get("task_id"):
            labels.append(f"任务编号 {filter_state['task_id']}")
        if filter_state.get("principal"):
            labels.append(f"执行主体 {self._principal_label(filter_state['principal'])}")
        if filter_state.get("decision"):
            labels.append(f"处理结果 {self._decision_label(filter_state['decision'])}")
        if filter_state.get("keyword"):
            labels.append(f"关键字 {filter_state['keyword']}")
        if filter_state.get("time_range"):
            labels.append(f"时间范围 {self._time_range_label(filter_state['time_range'])}")
        return " | ".join(labels) if labels else "当前展示全部审计事件"

    def _time_range_label(self, value: str) -> str:
        return {
            "1h": "最近 1 小时",
            "24h": "最近 24 小时",
            "all": "全部",
        }.get(value, "全部")

    def _audit_time_range_options(self, current: str) -> str:
        options = [
            ("1h", "最近 1 小时"),
            ("24h", "最近 24 小时"),
            ("all", "全部"),
        ]
        return "".join(
            f"<option value='{html.escape(value)}'{' selected' if current == value else ''}>{html.escape(label)}</option>"
            for value, label in options
        )

    def _approval_text(self, row: dict[str, object]) -> str:
        if not bool(row.get("approval_required")):
            return "无需审批"
        ticket = row.get("approval_ticket")
        return f"审批票据 {ticket}" if ticket else "缺少审批票据"

    def _token_state_label(self, row: dict[str, object]) -> str:
        if bool(row.get("revoked")):
            return "已撤销"
        if int(row.get("uses", 0)) >= int(row.get("max_uses", 0)):
            return "已耗尽"
        return "可用中"

    def _latency_label(self, value: object) -> str:
        try:
            latency = int(value)
        except (TypeError, ValueError):
            latency = 0
        return "-" if latency <= 0 else f"{latency} ms"

    def _failure_stage_label(self, stage: str) -> str:
        return {
            "assistant": "个人助理阶段",
            "query_request": "查询请求阶段",
            "query_delegation": "查询委托签发",
            "query_gateway": "查询授权校验",
            "query_result": "查询结果生成",
            "report_request": "报表请求阶段",
            "report_delegation": "报表委托签发",
            "report_gateway": "报表授权校验",
            "report_result": "报表生成阶段",
            "mail_request": "邮件请求阶段",
            "mail_delegation": "邮件委托签发",
            "mail_gateway": "邮件授权校验",
            "mail_compose": "邮件内容生成",
            "security": "安全控制阶段",
        }.get(stage, stage)

    def _format_display_time(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "-"
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return raw
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(self.display_timezone).strftime("%Y-%m-%d %H:%M:%S")

    def _json_pretty(self, value: object) -> str:
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))
