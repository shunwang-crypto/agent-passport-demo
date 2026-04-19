from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class AgentIdentity:
    principal: str
    role: str
    description: str
    auth_token: str = ""
    trust_level: str = "verified-workload"
    owner_user: str = "user:xiaoming"


@dataclass
class DelegationRecord:
    delegation_id: str
    root_principal: str
    from_principal: str
    to_principal: str
    task_id: str
    action: str
    resource: str
    expires_at: datetime
    risk_level: str = "medium"
    approval_required: bool = False
    approval_ticket: str | None = None
    max_uses: int = 1
    uses: int = 0
    revoked: bool = False
    capability_token: str = ""

    def is_expired(self, at: datetime | None = None) -> bool:
        reference = at or now_utc()
        return reference >= self.expires_at

    def consume(self) -> None:
        self.uses += 1

    def is_exhausted(self) -> bool:
        return self.uses >= self.max_uses

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "root_principal": self.root_principal,
            "from_principal": self.from_principal,
            "to_principal": self.to_principal,
            "task_id": self.task_id,
            "action": self.action,
            "resource": self.resource,
            "expires_at": self.expires_at.isoformat(),
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "approval_ticket": self.approval_ticket,
            "max_uses": self.max_uses,
            "uses": self.uses,
            "revoked": self.revoked,
            "capability_token": self.capability_token,
        }


@dataclass
class AuditEvent:
    event_id: int | None
    timestamp: str
    event_type: str
    task_id: str
    principal: str
    root_principal: str | None
    action: str
    resource: str
    resource_type: str
    decision: str
    reason_code: str
    reason_text: str
    delegation_id: str | None = None
    policy_rule: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "principal": self.principal,
            "root_principal": self.root_principal,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource,
            "resource_type": self.resource_type,
            "decision": self.decision,
            "reason": self.reason_text,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "delegation_id": self.delegation_id,
            "policy_rule": self.policy_rule,
            "metadata": self.metadata,
        }


def ttl_from_seconds(seconds: int) -> datetime:
    return now_utc() + timedelta(seconds=seconds)
