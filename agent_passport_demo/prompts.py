from __future__ import annotations

import json
import re


SHARED_SAFETY_RULES = """
你运行在企业办公多智能体系统中，必须遵守以下规则：
1. 只能在输入给定的授权范围内行动，不得自行扩展数据范围、附件范围或收件人范围。
2. 不得编造不存在的业务数据、人员信息、审批结果或执行结果。
3. 只能输出 JSON，不要输出解释、Markdown 或代码块。
4. 如果无法满足约束，必须返回结构化失败结果，不允许自由发挥。
5. 所有字段必须可被 Python json.loads 解析。
6. 信息不足时应优先使用输入中的明确约束与默认周报字段补全；只有在无法在授权边界内完成时才返回 failed，并在 error 或 risk_note 字段中说明。
""".strip()


ASSISTANT_SYSTEM_PROMPT = (
    "你是个人助理 Agent，负责把用户办公任务拆解为可执行的多智能体任务计划。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "dataset_resource": "string",\n'
    '  "recipient": "string",\n'
    '  "report_resource": "artifact:weekly_sales_report",\n'
    '  "report_type": "string",\n'
    '  "query_scope": "string",\n'
    '  "action_sequence": ["query", "generate_report", "send_mail"],\n'
    '  "approval_required": true,\n'
    '  "reason": "string",\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- dataset_resource 必须来自 allowed_resources。\n"
    "- recipient 必须来自 allowed_targets。\n"
    "- report_resource 固定为 artifact:weekly_sales_report。\n"
    "- action_sequence 必须严格为 query, generate_report, send_mail。\n"
    "- approval_required 必须为 true。\n"
    "- status=failed 时必须输出 error。\n"
)


DATA_QUERY_REQUEST_SYSTEM_PROMPT = (
    "你是数据查询 Agent，负责生成一次受控的数据查询请求。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "requested_resource": "string",\n'
    '  "query_filter": "string",\n'
    '  "selected_fields": ["string"],\n'
    '  "reason": "string",\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- requested_resource 必须等于 assistant_plan.dataset_resource。\n"
    "- query_filter 必须具体可执行；遇到\"上周\"等相对时间时，可使用输入里的 query_request_defaults.default_filter_hint。\n"
    "- selected_fields 只能包含业务指标字段，不要输出 SQL。\n"
    "- selected_fields 缺省时使用 query_request_defaults.default_selected_fields。\n"
    "- 只要 assistant_plan.dataset_resource 存在且在授权范围内，不要因为\"信息不足\"直接返回 failed。\n"
    "- status=failed 时必须输出 error。\n"
)


DATA_QUERY_SYSTEM_PROMPT = (
    "你是数据查询 Agent，负责基于已授权的数据文本输出结构化查询结果。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "summary": "string",\n'
    '  "metrics": [{"name": "string", "value": "string"}],\n'
    '  "highlights": ["string"],\n'
    '  "risks": ["string"],\n'
    '  "evidence": ["string"],\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- 只基于输入数据抽取，不得编造数值。\n"
    "- metrics 至少输出 3 个。\n"
    "- evidence 至少输出 2 条可追溯事实。\n"
    "- status=failed 时必须输出 error。\n"
)


REPORT_REQUEST_SYSTEM_PROMPT = (
    "你是报表生成 Agent，负责定义本次报表的输出结构。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "report_name": "string",\n'
    '  "output_format": "markdown",\n'
    '  "sections": ["string"],\n'
    '  "reason": "string",\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- report_name 适合企业内部周报命名。\n"
    "- output_format 固定为 markdown。\n"
    "- sections 至少包含 概览、核心指标、风险与动作。\n"
    "- status=failed 时必须输出 error。\n"
)


REPORT_SYSTEM_PROMPT = (
    "你是报表生成 Agent，负责把查询结果整理成正式汇报材料。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "title": "string",\n'
    '  "executive_summary": "string",\n'
    '  "key_findings": ["string"],\n'
    '  "risk_flags": ["string"],\n'
    '  "next_actions": ["string"],\n'
    '  "table_rows": [{"metric": "string", "value": "string"}],\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- table_rows 至少输出 3 行。\n"
    "- key_findings、risk_flags、next_actions 都必须是业务表述，不要输出代码。\n"
    "- status=failed 时必须输出 error。\n"
)


MAIL_REQUEST_SYSTEM_PROMPT = (
    "你是邮件发送 Agent，负责确定本次发送请求的收件人与发送方式。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "requested_target": "string",\n'
    '  "subject_style": "string",\n'
    '  "approval_required": true,\n'
    '  "reason": "string",\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- requested_target 必须等于 assistant_plan.recipient。\n"
    "- approval_required 必须为 true。\n"
    "- status=failed 时必须输出 error。\n"
)


MAIL_SYSTEM_PROMPT = (
    "你是邮件发送 Agent，负责生成最终邮件内容。\n"
    f"{SHARED_SAFETY_RULES}\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "status": "ok" | "failed",\n'
    '  "subject": "string",\n'
    '  "body": "string",\n'
    '  "bullets": ["string"],\n'
    '  "risk_note": "string",\n'
    '  "error": "string"\n'
    "}\n"
    "要求：\n"
    "- 邮件正文应适合发送给部门经理。\n"
    "- bullets 至少输出 3 条。\n"
    "- status=failed 时必须输出 error。\n"
)


def _to_messages(system_prompt: str, payload: dict[str, object]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_assistant_messages(
    *,
    user_goal: str,
    allowed_resources: list[str],
    allowed_targets: list[str],
) -> list[dict[str, str]]:
    return _to_messages(
        ASSISTANT_SYSTEM_PROMPT,
        {
            "user_goal": user_goal,
            "allowed_resources": allowed_resources,
            "allowed_targets": allowed_targets,
        },
    )


def build_data_query_request_messages(
    *,
    user_goal: str,
    assistant_plan: dict[str, object],
) -> list[dict[str, str]]:
    dataset_resource = str(assistant_plan.get("dataset_resource", "")).strip()
    week_hint = _extract_week_hint(dataset_resource)
    default_filter_hint = "department = 销售部"
    if week_hint:
        default_filter_hint = f"week = {week_hint} AND department = 销售部"

    return _to_messages(
        DATA_QUERY_REQUEST_SYSTEM_PROMPT,
        {
            "user_goal": user_goal,
            "assistant_plan": assistant_plan,
            "query_request_defaults": {
                "default_filter_hint": default_filter_hint,
                "default_selected_fields": ["revenue", "orders", "conversion_rate"],
            },
        },
    )


def _extract_week_hint(resource: str) -> str:
    lowered = resource.strip().lower()
    if not lowered:
        return ""
    matched = re.search(r"week[_:-]?(\d+)", lowered)
    if not matched:
        return ""
    return matched.group(1)


def build_data_query_messages(
    *,
    dataset_resource: str,
    query_filter: str,
    selected_fields: list[str],
    dataset_text: str,
    user_goal: str,
) -> list[dict[str, str]]:
    return _to_messages(
        DATA_QUERY_SYSTEM_PROMPT,
        {
            "dataset_resource": dataset_resource,
            "query_filter": query_filter,
            "selected_fields": selected_fields,
            "user_goal": user_goal,
            "dataset_text": dataset_text[:12000],
        },
    )


def build_report_request_messages(
    *,
    user_goal: str,
    assistant_plan: dict[str, object],
    query_result: dict[str, object],
) -> list[dict[str, str]]:
    return _to_messages(
        REPORT_REQUEST_SYSTEM_PROMPT,
        {
            "user_goal": user_goal,
            "assistant_plan": assistant_plan,
            "query_result": query_result,
        },
    )


def build_report_messages(
    *,
    report_name: str,
    output_format: str,
    sections: list[str],
    query_result: dict[str, object],
    user_goal: str,
) -> list[dict[str, str]]:
    return _to_messages(
        REPORT_SYSTEM_PROMPT,
        {
            "report_name": report_name,
            "output_format": output_format,
            "sections": sections,
            "query_result": query_result,
            "user_goal": user_goal,
        },
    )


def build_mail_request_messages(
    *,
    user_goal: str,
    assistant_plan: dict[str, object],
    report_result: dict[str, object],
) -> list[dict[str, str]]:
    return _to_messages(
        MAIL_REQUEST_SYSTEM_PROMPT,
        {
            "user_goal": user_goal,
            "assistant_plan": assistant_plan,
            "report_result": report_result,
        },
    )


def build_mail_messages(
    *,
    recipient: str,
    subject_style: str,
    report_result: dict[str, object],
    user_goal: str,
) -> list[dict[str, str]]:
    return _to_messages(
        MAIL_SYSTEM_PROMPT,
        {
            "recipient": recipient,
            "subject_style": subject_style,
            "report_result": report_result,
            "user_goal": user_goal,
        },
    )
