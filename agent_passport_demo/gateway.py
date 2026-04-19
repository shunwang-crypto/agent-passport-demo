from __future__ import annotations

from .audit import AuditLedger
from .capability import mask_capability_token
from .delegation import DelegationManager
from .policy import PolicyStore
from .registry import AgentRegistry


class AuthorizationError(RuntimeError):
    """Raised when an action is denied by the gateway."""


class AuthorizationGateway:
    def __init__(
        self,
        *,
        policy_store: PolicyStore,
        delegation_manager: DelegationManager,
        audit_ledger: AuditLedger,
        agent_registry: AgentRegistry,
    ) -> None:
        self.policy_store = policy_store
        self.delegation_manager = delegation_manager
        self.audit_ledger = audit_ledger
        self.agent_registry = agent_registry

    def check(
        self,
        *,
        principal: str,
        auth_token: str | None,
        task_id: str,
        action: str,
        resource: str,
        capability_token: str | None,
    ) -> None:
        decision = self.authorize(
            principal=principal,
            auth_token=auth_token,
            task_id=task_id,
            action=action,
            resource=resource,
            capability_token=capability_token,
            consume=True,
            record_audit=True,
        )
        if decision["decision"] != "allow":
            raise AuthorizationError(str(decision["reason_text"]))

    def authorize(
        self,
        *,
        principal: str,
        auth_token: str | None,
        task_id: str,
        action: str,
        resource: str,
        capability_token: str | None,
        consume: bool = False,
        record_audit: bool = False,
    ) -> dict[str, object]:
        if not self.agent_registry.authenticate(principal, auth_token):
            return self._finalize_decision(
                decision="deny",
                task_id=task_id,
                principal=principal,
                action=action,
                resource=resource,
                reason_code="identity_auth_failed",
                reason_text="agent authentication failed",
                record=None,
                capability_token=capability_token,
                policy_rule="agent workload authentication",
                record_audit=record_audit,
            )

        valid, reason_code, reason, record = self.delegation_manager.validate(
            capability_token=capability_token,
            principal=principal,
            task_id=task_id,
            action=action,
            resource=resource,
        )
        if not valid:
            return self._finalize_decision(
                decision="deny",
                task_id=task_id,
                principal=principal,
                action=action,
                resource=resource,
                reason_code=reason_code,
                reason_text=reason,
                record=record,
                capability_token=capability_token,
                policy_rule="root grant + signed task-scoped capability token",
                record_audit=record_audit,
            )

        assert record is not None
        if not self.policy_store.has_permission(
            record.root_principal,
            action,
            resource,
        ):
            return self._finalize_decision(
                decision="deny",
                task_id=task_id,
                principal=principal,
                action=action,
                resource=resource,
                reason_code="root_permission_revoked",
                reason_text="root principal permission revoked",
                record=record,
                capability_token=capability_token,
                policy_rule="root grant + signed task-scoped capability token",
                record_audit=record_audit,
            )

        if record.approval_required and not record.approval_ticket:
            return self._finalize_decision(
                decision="deny",
                task_id=task_id,
                principal=principal,
                action=action,
                resource=resource,
                reason_code="approval_missing",
                reason_text="high risk action requires approval",
                record=record,
                capability_token=capability_token,
                policy_rule="root grant + signed task-scoped capability token",
                record_audit=record_audit,
            )

        if consume:
            self.delegation_manager.consume(record.delegation_id)
        return self._finalize_decision(
            decision="allow",
            task_id=task_id,
            principal=principal,
            action=action,
            resource=resource,
            reason_code="delegation_valid",
            reason_text="delegation valid",
            record=record,
            capability_token=capability_token,
            policy_rule="root grant + signed task-scoped capability token",
            record_audit=record_audit,
        )

    def _metadata(
        self,
        record,
        capability_token: str | None,
        reason: str,
        reason_code: str,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "delegation_id": None if record is None else record.delegation_id,
            "capability_token_preview": self._token_preview(capability_token),
            "control_reason": reason,
            "reason_code": reason_code,
            "policy_rule": "root grant + signed task-scoped capability token",
        }
        if record is None:
            return metadata
        metadata.update(
            {
                "root_principal": record.root_principal,
                "from_principal": record.from_principal,
                "to_principal": record.to_principal,
                "risk_level": record.risk_level,
                "approval_required": record.approval_required,
                "approval_ticket": record.approval_ticket,
                "expires_at": record.expires_at.isoformat(timespec="seconds"),
                "max_uses": record.max_uses,
                "uses": record.uses,
                "status": record.status,
                "terminal_reason": record.terminal_reason,
            }
        )
        return metadata

    def _finalize_decision(
        self,
        *,
        decision: str,
        task_id: str,
        principal: str,
        action: str,
        resource: str,
        reason_code: str,
        reason_text: str,
        record,
        capability_token: str | None,
        policy_rule: str,
        record_audit: bool,
    ) -> dict[str, object]:
        metadata = self._metadata(record, capability_token, reason_text, reason_code)
        metadata["policy_rule"] = policy_rule
        if record_audit:
            self.audit_ledger.record(
                event_type="access_check",
                task_id=task_id,
                principal=principal,
                action=action,
                resource=resource,
                decision=decision,
                reason=reason_text,
                metadata=metadata,
            )
        return {
            "decision": decision,
            "task_id": task_id,
            "principal": principal,
            "action": action,
            "resource": resource,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "policy_rule": policy_rule,
            "delegation_id": None if record is None else record.delegation_id,
            "root_principal": None if record is None else record.root_principal,
            "capability_token_preview": self._token_preview(capability_token),
        }

    def _token_preview(self, capability_token: str | None) -> str | None:
        if not capability_token:
            return None
        return mask_capability_token(capability_token)
