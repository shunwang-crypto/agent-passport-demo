from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from .service import DemoService


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False

def build_wsgi_app(service: DemoService):
    def app(environ, start_response):
        method = environ["REQUEST_METHOD"].upper()
        path = environ.get("PATH_INFO", "/")
        query = parse_qs(environ.get("QUERY_STRING", ""))
        current_view = service.frontend.sanitize_view(query.get("view", ["overview"])[0])
        filters = {
            "task": query.get("task", [""])[0],
            "agent": query.get("agent", [""])[0],
            "decision": query.get("decision", [""])[0],
            "keyword": query.get("keyword", [""])[0],
            "time_range": query.get("time_range", [""])[0],
        }

        if method == "GET" and path.startswith("/static/"):
            relative_path = path.removeprefix("/static/")
            file_path = (service.static_dir / relative_path).resolve()
            static_root = service.static_dir.resolve()
            if not _is_within(static_root, file_path) or not file_path.is_file():
                body = b"Not Found"
                start_response(
                    "404 Not Found",
                    [("Content-Type", "text/plain; charset=utf-8")],
                )
                return [body]
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            body = file_path.read_bytes()
            start_response("200 OK", [("Content-Type", content_type)])
            return [body]

        if method == "GET" and path.startswith("/artifacts/"):
            relative_path = path.removeprefix("/artifacts/")
            file_path = (service.artifacts_dir / relative_path).resolve()
            artifacts_root = service.artifacts_dir.resolve()
            if not _is_within(artifacts_root, file_path) or not file_path.is_file():
                body = b"Not Found"
                start_response(
                    "404 Not Found",
                    [("Content-Type", "text/plain; charset=utf-8")],
                )
                return [body]
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            headers = [("Content-Type", content_type)]
            if file_path.suffix == ".zip":
                headers.append(
                    ("Content-Disposition", f"attachment; filename={quote(file_path.name)}")
                )
            body = file_path.read_bytes()
            start_response("200 OK", headers)
            return [body]

        if method == "GET" and path == "/":
            body = service.render_dashboard(view=current_view, filters=filters).encode("utf-8")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [body]

        if method == "GET" and path == "/api/state":
            debug_param = query.get("debug", [""])[0].strip().lower()
            debug_requested = debug_param in {"1", "true", "yes", "on"}
            include_debug = service.debug_state and debug_requested
            body = json.dumps(
                service.state_payload(debug=include_debug),
                ensure_ascii=False,
                indent=2,
            ).encode(
                "utf-8"
            )
            start_response(
                "200 OK",
                [("Content-Type", "application/json; charset=utf-8")],
            )
            return [body]

        if method == "POST":
            if path == "/api/authorize":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                raw_body = environ["wsgi.input"].read(size).decode("utf-8")
                try:
                    payload = json.loads(raw_body or "{}")
                except json.JSONDecodeError:
                    body = json.dumps(
                        {
                            "decision": "deny",
                            "reason_code": "invalid_json",
                            "reason_text": "request body must be valid JSON",
                            "policy_rule": "request validation",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8")
                    start_response(
                        "400 Bad Request",
                        [("Content-Type", "application/json; charset=utf-8")],
                    )
                    return [body]

                audit_mode_override = query.get("audit_mode", [""])[0] or None
                status_code, response = service.authorize_request(
                    payload,
                    audit_mode_override=audit_mode_override,
                )
                body = json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8")
                status_line = "200 OK" if status_code == 200 else "400 Bad Request"
                start_response(
                    status_line,
                    [("Content-Type", "application/json; charset=utf-8")],
                )
                return [body]

            size = int(environ.get("CONTENT_LENGTH") or 0)
            raw_body = environ["wsgi.input"].read(size).decode("utf-8")
            form = parse_qs(raw_body)
            action = form.get("action", [""])[0]
            current_view = service.frontend.sanitize_view(form.get("view", ["overview"])[0])

            if path == "/run" and action in service._scenario_handlers():
                service.run_scenario(action)
                body = service.render_dashboard(view=current_view, filters={}).encode("utf-8")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body]

            if path == "/benchmark":
                service.run_benchmark()
                body = service.render_dashboard(view=current_view, filters={}).encode("utf-8")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body]

            if path == "/reset":
                service.reset(clear_history=True)
                body = service.render_dashboard(view=current_view, filters={}).encode("utf-8")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body]

        body = b"Not Found"
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [body]

    return app



def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    service = DemoService()
    with make_server(host, port, build_wsgi_app(service)) as server:
        print(f"Agent Passport demo running at http://{host}:{port}")
        server.serve_forever()

