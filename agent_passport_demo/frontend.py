from __future__ import annotations

import html
from pathlib import Path
from string import Template


class _TemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "-"


class DashboardFrontend:
    VIEW_TABS: tuple[tuple[str, str], ...] = (
        ("overview", "首页"),
        ("graph", "资源边界"),
        ("token", "委托与令牌"),
        ("benchmark", "安全评测"),
        ("details", "审计追踪"),
    )
    HIDDEN_VIEWS: tuple[str, ...] = ("decision",)

    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir

    def sanitize_view(self, view: str | None) -> str:
        allowed = {key for key, _ in self.VIEW_TABS} | set(self.HIDDEN_VIEWS)
        return view if view in allowed else "overview"

    def render_page(self, *, current_view: str, context: dict[str, str]) -> str:
        shell_template = Template(self._read("shell.html"))
        view_template = Template(self._read(f"views/{current_view}.html"))
        resolved_context = _TemplateContext(context)

        main_view_content = view_template.substitute(resolved_context)
        return shell_template.substitute(
            resolved_context,
            current_view=html.escape(current_view),
            view_tabs=self._view_tabs(current_view),
            main_view_content=main_view_content,
        )

    def _view_tabs(self, current_view: str) -> str:
        return "".join(
            f"<a class='view-tab{' view-tab-active' if key == current_view else ''}' href='/?view={key}'>{html.escape(label)}</a>"
            for key, label in self.VIEW_TABS
        )

    def _read(self, relative_path: str) -> str:
        return (self.templates_dir / relative_path).read_text(encoding="utf-8")
