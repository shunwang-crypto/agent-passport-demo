from __future__ import annotations

from .storage import DemoDatabase


class PolicyStore:
    def __init__(self, database: DemoDatabase) -> None:
        self.database = database

    def has_permission(self, principal: str, action: str, resource: str) -> bool:
        row = self.database.fetch_one(
            """
            SELECT 1
            FROM root_permissions
            WHERE principal = ?
              AND action = ?
              AND resource_id = ?
              AND effect = 'allow'
            """,
            (principal, action, resource),
        )
        return row is not None

    def grant_permission(self, principal: str, action: str, resource: str) -> None:
        self.database.execute(
            """
            INSERT INTO root_permissions (principal, action, resource_id, effect)
            VALUES (?, ?, ?, 'allow')
            ON CONFLICT(principal, action, resource_id) DO UPDATE SET
                effect = 'allow'
            """,
            (principal, action, resource),
        )

    def revoke_permission(self, principal: str, action: str, resource: str) -> bool:
        cursor = self.database.execute(
            """
            DELETE FROM root_permissions
            WHERE principal = ? AND action = ? AND resource_id = ?
            """,
            (principal, action, resource),
        )
        return int(cursor.rowcount) > 0

    def export(self) -> list[dict[str, str]]:
        rows = self.database.fetch_all(
            """
            SELECT
                rp.principal,
                rp.action,
                rp.resource_id,
                rp.effect,
                r.resource_type,
                r.project,
                r.sensitivity
            FROM root_permissions rp
            LEFT JOIN resources r
              ON rp.resource_id = r.resource_id
            ORDER BY rp.principal, rp.action, rp.resource_id
            """
        )
        return [
            {
                "principal": str(row["principal"]),
                "action": str(row["action"]),
                "resource": str(row["resource_id"]),
                "effect": str(row["effect"]),
                "resource_type": str(row["resource_type"] or "unknown"),
                "project": str(row["project"] or "-"),
                "sensitivity": str(row["sensitivity"] or "-"),
            }
            for row in rows
        ]
