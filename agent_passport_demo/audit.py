from __future__ import annotations

import json
from typing import Any

from .models import AuditEvent, now_utc
from .storage import DemoDatabase


DEFAULT_REASON_CODES: dict[str, str] = {
    "task started": "task_started",
    "real collaboration completed": "task_completed",
    "task denied": "task_denied",
    "task failed": "task_failed",
    "delegation issued": "delegation_issued",
    "delegation valid": "delegation_valid",
    "unauthorized resource": "resource_not_in_scope",
    "root principal lacks permission": "root_permission_revoked",
    "root permission revoked": "root_permission_revoked",
    "agent authentication failed": "identity_auth_failed",
    "high risk action requires approval": "approval_missing",
    "delegation revoked": "delegation_revoked",
    "task mismatch": "task_mismatch",
    "action mismatch": "action_not_allowed",
    "delegation expired": "delegation_expired",
    "delegation already used": "delegation_exhausted",
    "delegation principal mismatch": "target_mismatch",
    "delegation not found": "delegation_missing",
    "missing delegation": "delegation_missing",
    "capability signature invalid": "capability_invalid_signature",
    "capability missing claim": "capability_missing_claim",
    "capability audience invalid": "capability_invalid_audience",
    "capability version invalid": "capability_invalid_version",
    "capability expired": "capability_expired",
    "capability not yet valid": "capability_not_yet_valid",
    "capability nbf before iat": "capability_iat_out_of_range",
    "capability iat too far in future": "capability_iat_out_of_range",
    "capability iat too old": "capability_iat_out_of_range",
    "capability iat after exp": "capability_iat_out_of_range",
    "capability time range invalid": "capability_malformed",
    "capability token missing jti": "capability_malformed",
    "capability token not recognized": "capability_claim_mismatch",
    "security control failed": "security_control_failed",
    "planner llm metadata": "planner_llm_metadata",
}


class AuditLedger:
    def __init__(self, database: DemoDatabase) -> None:
        self.database = database

    def record(
        self,
        *,
        event_type: str,
        task_id: str,
        principal: str,
        action: str,
        resource: str,
        decision: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        payload = dict(metadata or {})
        reason_code = str(payload.pop("reason_code", DEFAULT_REASON_CODES.get(reason, reason)))
        reason_text = str(payload.pop("reason_text", reason))
        root_principal = payload.get("root_principal")
        delegation_id = payload.get("delegation_id")
        policy_rule = str(payload.get("policy_rule", ""))
        event = AuditEvent(
            event_id=None,
            timestamp=now_utc().isoformat(timespec="seconds"),
            event_type=event_type,
            task_id=task_id,
            principal=principal,
            root_principal=None if root_principal is None else str(root_principal),
            action=action,
            resource=resource,
            resource_type=self.database.resource_type(resource),
            decision=decision,
            reason_code=reason_code,
            reason_text=reason_text,
            delegation_id=None if delegation_id is None else str(delegation_id),
            policy_rule=policy_rule,
            metadata=payload,
        )
        cursor = self.database.execute(
            """
            INSERT INTO audit_logs (
                timestamp,
                task_id,
                principal,
                root_principal,
                event_type,
                action,
                resource_id,
                resource_type,
                decision,
                reason_code,
                reason_text,
                delegation_id,
                policy_rule,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp,
                event.task_id,
                event.principal,
                event.root_principal,
                event.event_type,
                event.action,
                event.resource,
                event.resource_type,
                event.decision,
                event.reason_code,
                event.reason_text,
                event.delegation_id,
                event.policy_rule,
                json.dumps(event.metadata, ensure_ascii=False),
            ),
        )
        event.event_id = int(cursor.lastrowid)
        return event

    def events(
        self,
        task_id: str | None = None,
        principal: str | None = None,
        decision: str | None = None,
        include_internal: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_internal:
            clauses.append("event_type != ?")
            params.append("api_probe")
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if principal:
            clauses.append("principal = ?")
            params.append(principal)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.database.fetch_all(
            f"""
            SELECT
                event_id,
                timestamp,
                task_id,
                principal,
                root_principal,
                event_type,
                action,
                resource_id,
                resource_type,
                decision,
                reason_code,
                reason_text,
                delegation_id,
                policy_rule,
                metadata_json
            FROM audit_logs
            {where}
            ORDER BY event_id ASC
            """,
            params,
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            event = AuditEvent(
                event_id=int(row["event_id"]),
                timestamp=str(row["timestamp"]),
                event_type=str(row["event_type"]),
                task_id=str(row["task_id"]),
                principal=str(row["principal"]),
                root_principal=None
                if row["root_principal"] is None
                else str(row["root_principal"]),
                action=str(row["action"]),
                resource=str(row["resource_id"]),
                resource_type=str(row["resource_type"]),
                decision=str(row["decision"]),
                reason_code=str(row["reason_code"]),
                reason_text=str(row["reason_text"]),
                delegation_id=None
                if row["delegation_id"] is None
                else str(row["delegation_id"]),
                policy_rule=str(row["policy_rule"] or ""),
                metadata=json.loads(str(row["metadata_json"] or "{}")),
            )
            events.append(event.to_dict())
        return events
