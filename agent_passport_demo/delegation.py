from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from .capability import CapabilityTokenService, mask_capability_token
from .models import DelegationRecord, now_utc, ttl_from_seconds
from .storage import DemoDatabase


class DelegationManager:
    def __init__(self, database: DemoDatabase, signing_key: str) -> None:
        self.database = database
        self.token_service = CapabilityTokenService(signing_key)

    def issue(
        self,
        *,
        root_principal: str,
        from_principal: str,
        to_principal: str,
        task_id: str,
        action: str,
        resource: str,
        risk_level: str = "medium",
        approval_required: bool = False,
        approval_ticket: str | None = None,
        ttl_seconds: int = 300,
        max_uses: int = 1,
    ) -> DelegationRecord:
        record = DelegationRecord(
            delegation_id=f"delg_{uuid4().hex[:8]}",
            root_principal=root_principal,
            from_principal=from_principal,
            to_principal=to_principal,
            task_id=task_id,
            action=action,
            resource=resource,
            expires_at=ttl_from_seconds(ttl_seconds),
            risk_level=risk_level,
            approval_required=approval_required,
            approval_ticket=approval_ticket,
            ttl_seconds=ttl_seconds,
            max_uses=max_uses,
        )
        issued_at = now_utc().isoformat(timespec="seconds")
        record.capability_token = self.token_service.issue(
            {
                "jti": record.delegation_id,
                "iss": record.from_principal,
                "sub": record.to_principal,
                "aud": self.token_service.audience,
                "iat": issued_at,
                "nbf": issued_at,
                "ver": self.token_service.version,
                "root_principal": record.root_principal,
                "from_principal": record.from_principal,
                "to_principal": record.to_principal,
                "task_id": record.task_id,
                "action": record.action,
                "resource": record.resource,
                "risk_level": record.risk_level,
                "approval_required": record.approval_required,
                "approval_ticket": record.approval_ticket,
                "ttl_seconds": record.ttl_seconds,
                "exp": record.expires_at.isoformat(timespec="seconds"),
                "max_uses": record.max_uses,
            }
        )
        self.database.execute(
            """
            INSERT INTO delegations (
                delegation_id,
                root_principal,
                from_principal,
                to_principal,
                task_id,
                action,
                resource_id,
                expires_at,
                risk_level,
                approval_required,
                approval_ticket,
                ttl_seconds,
                max_uses,
                uses,
                revoked,
                status,
                terminal_reason,
                capability_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.delegation_id,
                record.root_principal,
                record.from_principal,
                record.to_principal,
                record.task_id,
                record.action,
                record.resource,
                record.expires_at.isoformat(timespec="seconds"),
                record.risk_level,
                1 if record.approval_required else 0,
                record.approval_ticket,
                record.ttl_seconds,
                record.max_uses,
                record.uses,
                1 if record.revoked else 0,
                record.status,
                record.terminal_reason,
                record.capability_token,
            ),
        )
        return record

    def validate(
        self,
        *,
        capability_token: str | None,
        principal: str,
        task_id: str,
        action: str,
        resource: str,
    ) -> tuple[bool, str, str, DelegationRecord | None]:
        if not capability_token:
            return False, "delegation_missing", "missing delegation", None

        valid_token, claims, reason_code, reason = self.token_service.verify(capability_token)
        if not valid_token:
            return False, reason_code, reason, None
        assert claims is not None

        delegation_id = str(claims.get("jti", ""))
        if not delegation_id:
            return False, "capability_malformed", "capability token missing jti", None

        record = self._get(delegation_id)
        if not record:
            return False, "delegation_missing", "delegation not found", None
        if record.capability_token != capability_token:
            return False, "capability_claim_mismatch", "capability token not recognized", record

        if str(claims.get("iss", "")) != record.from_principal:
            return False, "capability_claim_mismatch", "delegation issuer mismatch", record
        if str(claims.get("sub", "")) != record.to_principal:
            return False, "capability_claim_mismatch", "delegation subject mismatch", record
        if str(claims.get("to_principal", "")) != record.to_principal:
            return False, "capability_claim_mismatch", "delegation target mismatch", record
        if str(claims.get("task_id", "")) != record.task_id:
            return False, "task_mismatch", "task mismatch", record
        if str(claims.get("action", "")) != record.action:
            return False, "action_not_allowed", "action mismatch", record
        if str(claims.get("resource", "")) != record.resource:
            return False, "resource_not_in_scope", "unauthorized resource", record

        if record.revoked:
            return False, "delegation_revoked", "delegation revoked", record
        if record.to_principal != principal:
            return False, "target_mismatch", "delegation principal mismatch", record
        if record.task_id != task_id:
            return False, "task_mismatch", "task mismatch", record
        if record.action != action:
            return False, "action_not_allowed", "action mismatch", record
        if record.resource != resource:
            return False, "resource_not_in_scope", "unauthorized resource", record
        if record.is_expired():
            return False, "delegation_expired", "delegation expired", record
        if record.is_exhausted():
            return False, "delegation_exhausted", "delegation already used", record
        return True, "allow", "delegation valid", record

    def consume(self, delegation_id: str) -> DelegationRecord | None:
        record = self._get(delegation_id)
        if record is None:
            return None
        record.consume()
        self.database.execute(
            """
            UPDATE delegations
            SET uses = uses + 1,
                status = ?,
                terminal_reason = ?,
                revoked = 0
            WHERE delegation_id = ?
            """,
            (record.status, record.terminal_reason, delegation_id),
        )
        return record

    def revoke_for_root_resource(
        self,
        *,
        root_principal: str,
        action: str,
        resource: str,
        reason: str = "root_permission_revoked",
    ) -> int:
        cursor = self.database.execute(
            """
            UPDATE delegations
            SET revoked = 1,
                status = 'revoked',
                terminal_reason = ?
            WHERE root_principal = ?
              AND action = ?
              AND resource_id = ?
              AND revoked = 0
            """,
            (reason, root_principal, action, resource),
        )
        return int(cursor.rowcount)

    def revoke_for_task(self, task_id: str, *, reason: str = "task_terminated") -> int:
        cursor = self.database.execute(
            """
            UPDATE delegations
            SET revoked = 1,
                status = 'revoked',
                terminal_reason = ?
            WHERE task_id = ?
              AND revoked = 0
              AND uses < max_uses
              AND expires_at > ?
            """,
            (reason, task_id, now_utc().isoformat(timespec="seconds")),
        )
        return int(cursor.rowcount)

    def expire_now(self, delegation_id: str) -> DelegationRecord | None:
        record = self._get(delegation_id)
        if record is None:
            return None

        expired_at = now_utc()
        record.expire("timeout")
        record.expires_at = expired_at
        record.capability_token = self.token_service.issue(
            {
                "jti": record.delegation_id,
                "iss": record.from_principal,
                "sub": record.to_principal,
                "aud": self.token_service.audience,
                "iat": expired_at.isoformat(timespec="seconds"),
                "nbf": expired_at.isoformat(timespec="seconds"),
                "ver": self.token_service.version,
                "root_principal": record.root_principal,
                "from_principal": record.from_principal,
                "to_principal": record.to_principal,
                "task_id": record.task_id,
                "action": record.action,
                "resource": record.resource,
                "risk_level": record.risk_level,
                "approval_required": record.approval_required,
                "approval_ticket": record.approval_ticket,
                "ttl_seconds": record.ttl_seconds,
                "exp": expired_at.isoformat(timespec="seconds"),
                "max_uses": record.max_uses,
            }
        )

        self.database.execute(
            """
            UPDATE delegations
            SET expires_at = ?,
                capability_token = ?,
                status = ?,
                terminal_reason = ?,
                revoked = 0
            WHERE delegation_id = ?
            """,
            (
                record.expires_at.isoformat(timespec="seconds"),
                record.capability_token,
                record.status,
                record.terminal_reason,
                delegation_id,
            ),
        )
        return record

    def export(self, *, include_sensitive: bool = False) -> list[dict[str, object]]:
        rows = self.database.fetch_all(
            """
            SELECT
                d.delegation_id,
                d.root_principal,
                d.from_principal,
                d.to_principal,
                d.task_id,
                d.action,
                d.resource_id,
                d.expires_at,
                d.risk_level,
                d.approval_required,
                d.approval_ticket,
                d.ttl_seconds,
                d.max_uses,
                d.uses,
                d.revoked,
                d.status,
                d.terminal_reason,
                d.capability_token,
                r.resource_type,
                r.sensitivity
            FROM delegations d
            LEFT JOIN resources r
              ON d.resource_id = r.resource_id
            ORDER BY d.delegation_id DESC
            """
        )
        return [
            {
                "delegation_id": str(row["delegation_id"]),
                "root_principal": str(row["root_principal"]),
                "from_principal": str(row["from_principal"]),
                "to_principal": str(row["to_principal"]),
                "task_id": str(row["task_id"]),
                "action": str(row["action"]),
                "resource": str(row["resource_id"]),
                "expires_at": str(row["expires_at"]),
                "risk_level": str(row["risk_level"]),
                "approval_required": bool(row["approval_required"]),
                "approval_ticket": row["approval_ticket"],
                "ttl_seconds": int(row["ttl_seconds"]),
                "max_uses": int(row["max_uses"]),
                "uses": int(row["uses"]),
                "revoked": bool(row["revoked"]),
                "status": str(row["status"] or "active"),
                "terminal_reason": str(row["terminal_reason"] or ""),
                "capability_token_preview": mask_capability_token(str(row["capability_token"] or "")),
                "resource_type": str(row["resource_type"] or "unknown"),
                "sensitivity": str(row["sensitivity"] or "-"),
                **(
                    {"capability_token": str(row["capability_token"] or "")}
                    if include_sensitive
                    else {}
                ),
            }
            for row in rows
        ]

    def _get(self, delegation_id: str) -> DelegationRecord | None:
        row = self.database.fetch_one(
            """
            SELECT *
            FROM delegations
            WHERE delegation_id = ?
            """,
            (delegation_id,),
        )
        if row is None:
            return None
        return DelegationRecord(
            delegation_id=str(row["delegation_id"]),
            root_principal=str(row["root_principal"]),
            from_principal=str(row["from_principal"]),
            to_principal=str(row["to_principal"]),
            task_id=str(row["task_id"]),
            action=str(row["action"]),
            resource=str(row["resource_id"]),
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
            risk_level=str(row["risk_level"]),
            approval_required=bool(row["approval_required"]),
            approval_ticket=row["approval_ticket"],
            ttl_seconds=int(row["ttl_seconds"]),
            max_uses=int(row["max_uses"]),
            uses=int(row["uses"]),
            revoked=bool(row["revoked"]),
            status=str(row["status"] or "active"),
            terminal_reason=str(row["terminal_reason"] or ""),
            capability_token=str(row["capability_token"] or ""),
        )
