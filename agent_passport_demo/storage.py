from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "workdir" / "docs"


def _docs_content(filename: str, default_text: str) -> str:
    file_path = DOCS_DIR / filename
    try:
        content = file_path.read_text(encoding="utf-8").strip()
    except OSError:
        return default_text
    return content if content else default_text


DEFAULT_RESOURCES: tuple[dict[str, str], ...] = (
    {
        "resource_id": "dataset:sales_week15",
        "resource_type": "dataset",
        "project": "sales_ops",
        "sensitivity": "internal",
        "owner": "dept:sales",
        "description": "销售部第 15 周业务数据，只允许在销售任务范围内查询。",
        "content": _docs_content("sales_week15.csv", "week,department,revenue,orders,conversion_rate,owner\n15,销售部,0,0,0,待补充"),
        "allowed_actions": "query",
    },
    {
        "resource_id": "dataset:finance_sensitive",
        "resource_type": "dataset",
        "project": "finance_ops",
        "sensitivity": "secret",
        "owner": "dept:finance",
        "description": "财务敏感数据，用于演示跨部门越权读取拦截。",
        "content": _docs_content("finance_sensitive.csv", "week,department,budget,margin,owner\n15,财务部,0,0,待补充"),
        "allowed_actions": "query",
    },
    {
        "resource_id": "artifact:weekly_sales_report",
        "resource_type": "artifact",
        "project": "sales_ops",
        "sensitivity": "internal",
        "owner": "dept:sales",
        "description": "周报输出文件，报表生成 Agent 只能写入该类工件。",
        "content": "",
        "allowed_actions": "generate_report",
    },
    {
        "resource_id": "mail:manager_zhang",
        "resource_type": "mailbox",
        "project": "sales_ops",
        "sensitivity": "internal",
        "owner": "dept:sales",
        "description": "销售部张经理邮箱，用于正常发送场景。",
        "content": "",
        "allowed_actions": "send_mail",
    },
    {
        "resource_id": "mail:finance_group",
        "resource_type": "mailbox",
        "project": "finance_ops",
        "sensitivity": "restricted",
        "owner": "dept:finance",
        "description": "错误收件目标，用于演示目标错发拦截。",
        "content": "",
        "allowed_actions": "send_mail",
    },
    {
        "resource_id": "tool:report_writer",
        "resource_type": "tool",
        "project": "platform",
        "sensitivity": "restricted",
        "owner": "team:platform",
        "description": "报表工件生成工具入口。",
        "content": "",
        "allowed_actions": "generate_report,delegate",
    },
    {
        "resource_id": "tool:mail_sender",
        "resource_type": "tool",
        "project": "platform",
        "sensitivity": "restricted",
        "owner": "team:platform",
        "description": "企业邮件发送工具入口。",
        "content": "",
        "allowed_actions": "send_mail,delegate",
    },
)


DEFAULT_ROOT_PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("user:xiaoming", "query", "dataset:sales_week15", "allow"),
    ("user:xiaoming", "generate_report", "artifact:weekly_sales_report", "allow"),
    ("user:xiaoming", "send_mail", "mail:manager_zhang", "allow"),
)


class DemoDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=MEMORY")
        self.conn.execute("PRAGMA synchronous=OFF")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self._initialize()
        self._seed_static_data()

    def _initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                project TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                owner TEXT NOT NULL,
                description TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                allowed_actions TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS root_permissions (
                principal TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                effect TEXT NOT NULL DEFAULT 'allow',
                PRIMARY KEY (principal, action, resource_id)
            );

            CREATE TABLE IF NOT EXISTS delegations (
                delegation_id TEXT PRIMARY KEY,
                root_principal TEXT NOT NULL,
                from_principal TEXT NOT NULL,
                to_principal TEXT NOT NULL,
                task_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                approval_required INTEGER NOT NULL DEFAULT 0,
                approval_ticket TEXT,
                ttl_seconds INTEGER NOT NULL DEFAULT 300,
                max_uses INTEGER NOT NULL DEFAULT 1,
                uses INTEGER NOT NULL DEFAULT 0,
                revoked INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                terminal_reason TEXT NOT NULL DEFAULT '',
                capability_token TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_id TEXT NOT NULL,
                principal TEXT NOT NULL,
                root_principal TEXT,
                event_type TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                reason_text TEXT NOT NULL,
                delegation_id TEXT,
                policy_rule TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS outbound_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                task_id TEXT NOT NULL DEFAULT '',
                target TEXT NOT NULL,
                content TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scenario_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_name TEXT NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL
            );
            """
        )
        self._ensure_column("delegations", "capability_token", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("delegations", "ttl_seconds", "INTEGER NOT NULL DEFAULT 300")
        self._ensure_column("delegations", "status", "TEXT NOT NULL DEFAULT 'active'")
        self._ensure_column("delegations", "terminal_reason", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("outbound_messages", "task_id", "TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    def _ensure_column(self, table_name: str, column_name: str, column_sql: str) -> None:
        columns = self.fetch_all(f"PRAGMA table_info({table_name})")
        existing = {str(row['name']) for row in columns}
        if column_name in existing:
            return
        self.conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _seed_static_data(self) -> None:
        with self.conn:
            for resource in DEFAULT_RESOURCES:
                self.conn.execute(
                    """
                    INSERT INTO resources (
                        resource_id,
                        resource_type,
                        project,
                        sensitivity,
                        owner,
                        description,
                        content,
                        allowed_actions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_id) DO UPDATE SET
                        resource_type = excluded.resource_type,
                        project = excluded.project,
                        sensitivity = excluded.sensitivity,
                        owner = excluded.owner,
                        description = excluded.description,
                        content = excluded.content,
                        allowed_actions = excluded.allowed_actions
                    """,
                    (
                        resource["resource_id"],
                        resource["resource_type"],
                        resource["project"],
                        resource["sensitivity"],
                        resource["owner"],
                        resource["description"],
                        resource["content"],
                        resource["allowed_actions"],
                    ),
                )
        self.reset_runtime(clear_history=True)

    def reset_runtime(self, *, clear_history: bool) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM root_permissions")
            if clear_history:
                self.conn.execute("DELETE FROM delegations")
                self.conn.execute("DELETE FROM audit_logs")
                self.conn.execute("DELETE FROM outbound_messages")
                self.conn.execute("DELETE FROM scenario_runs")
            self.conn.executemany(
                """
                INSERT INTO root_permissions (principal, action, resource_id, effect)
                VALUES (?, ?, ?, ?)
                """,
                DEFAULT_ROOT_PERMISSIONS,
            )

    def execute(self, query: str, params: Iterable[object] = ()) -> sqlite3.Cursor:
        with self.conn:
            return self.conn.execute(query, tuple(params))

    def executemany(self, query: str, rows: Iterable[Iterable[object]]) -> None:
        with self.conn:
            self.conn.executemany(query, [tuple(row) for row in rows])

    def fetch_all(self, query: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        cursor = self.conn.execute(query, tuple(params))
        return list(cursor.fetchall())

    def fetch_one(self, query: str, params: Iterable[object] = ()) -> sqlite3.Row | None:
        cursor = self.conn.execute(query, tuple(params))
        return cursor.fetchone()

    def resource_type(self, resource_id: str) -> str:
        row = self.fetch_one("SELECT resource_type FROM resources WHERE resource_id = ?", (resource_id,))
        return str(row["resource_type"]) if row else "unknown"

    def record_scenario_run(
        self,
        *,
        scenario_name: str,
        task_id: str,
        status: str,
        started_at: str,
        finished_at: str,
    ) -> None:
        self.execute(
            """
            INSERT INTO scenario_runs (
                scenario_name,
                task_id,
                status,
                started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (scenario_name, task_id, status, started_at, finished_at),
        )

    def list_scenario_runs(self) -> list[dict[str, str]]:
        rows = self.fetch_all(
            """
            SELECT run_id, scenario_name, task_id, status, started_at, finished_at
            FROM scenario_runs
            ORDER BY run_id DESC
            """
        )
        return [
            {
                "run_id": str(row["run_id"]),
                "scenario": str(row["scenario_name"]),
                "task_id": str(row["task_id"]),
                "status": str(row["status"]),
                "started_at": str(row["started_at"]),
                "finished_at": str(row["finished_at"]),
            }
            for row in rows
        ]
