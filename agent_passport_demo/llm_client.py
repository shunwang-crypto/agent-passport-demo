from __future__ import annotations

import json
import os
import time
from urllib import error, request

from .prompts import (
    build_assistant_messages,
    build_data_query_messages,
    build_data_query_request_messages,
    build_mail_messages,
    build_mail_request_messages,
    build_report_messages,
    build_report_request_messages,
)


MODEL_ALIASES: dict[str, str] = {
    "deepseek-chat": "deepseek-chat",
    "chat": "deepseek-chat",
    "deepseek-v3": "deepseek-chat",
    "v3": "deepseek-chat",
    "deepseek-reasoner": "deepseek-reasoner",
    "reasoner": "deepseek-reasoner",
    "deepseek-r1": "deepseek-reasoner",
    "r1": "deepseek-reasoner",
}


THINKING_TOGGLE_MODELS: set[str] = {
    "deepseek-chat",
    "deepseek-reasoner",
}


HARDCODED_DEEPSEEK_API_KEY = "sk-317dad29b20848b6a37b3921d4d87d50"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default


def _env_optional_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return None


def _first_non_empty_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        text = value.strip()
        if text:
            return text
    return None


def _supports_thinking_toggle(model_name: str) -> bool:
    return model_name.strip().lower() in THINKING_TOGGLE_MODELS


def _resolve_model_name(value: str) -> str:
    text = value.strip()
    if not text:
        return "deepseek-chat"
    return MODEL_ALIASES.get(text.lower(), text)


def _default_timeout_for_model(model_name: str) -> float:
    lowered = model_name.lower()
    if "reasoner" in lowered or ("deepseek" in lowered and "r1" in lowered):
        return 180.0
    if "deepseek" in lowered and "v3" in lowered:
        return 60.0
    if "deepseek" in lowered:
        return 60.0
    return 20.0


def _extract_first_json_object(text: str) -> str:
    start = -1
    depth = 0
    in_string = False
    escaped = False
    for idx, ch in enumerate(text):
        if start < 0:
            if ch == "{":
                start = idx
                depth = 1
                in_string = False
                escaped = False
            continue
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return ""


def _parse_json_object(text: str) -> dict[str, object] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        parts = candidate.split("```")
        if len(parts) >= 3:
            candidate = parts[1].strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        extracted = _extract_first_json_object(candidate)
        if not extracted:
            return None
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


class AgentLLMClient:
    def __init__(self) -> None:
        self.provider = "deepseek"
        self.base_url = (_first_non_empty_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
        self.model = _resolve_model_name(_first_non_empty_env("DEEPSEEK_MODEL") or "deepseek-chat")
        self.enabled = _env_bool("DEEPSEEK_ENABLED", default=True)
        self.api_key = (_first_non_empty_env("DEEPSEEK_API_KEY") or HARDCODED_DEEPSEEK_API_KEY).strip()
        self.timeout_seconds = _env_float("DEEPSEEK_TIMEOUT_SECONDS", default=_default_timeout_for_model(self.model))
        self.supports_thinking_toggle = _supports_thinking_toggle(self.model)

        env_enable_thinking = _env_optional_bool("DEEPSEEK_ENABLE_THINKING")
        if env_enable_thinking is not None:
            self.enable_thinking = env_enable_thinking
        elif self.supports_thinking_toggle:
            # Speed-first default for supported models.
            self.enable_thinking = False
        else:
            self.enable_thinking = None

        self.thinking_budget = _env_int("DEEPSEEK_THINKING_BUDGET", default=4096, minimum=0)

    def assistant(
        self,
        *,
        user_goal: str,
        allowed_resources: list[str],
        allowed_targets: list[str],
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_assistant_messages(
                user_goal=user_goal,
                allowed_resources=allowed_resources,
                allowed_targets=allowed_targets,
            ),
            temperature=0.1,
            max_tokens=700,
        )

    def data_query_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_data_query_request_messages(
                user_goal=user_goal,
                assistant_plan=assistant_plan,
            ),
            temperature=0.1,
            max_tokens=500,
        )

    def data_query(
        self,
        *,
        dataset_resource: str,
        query_filter: str,
        selected_fields: list[str],
        dataset_text: str,
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_data_query_messages(
                dataset_resource=dataset_resource,
                query_filter=query_filter,
                selected_fields=selected_fields,
                dataset_text=dataset_text,
                user_goal=user_goal,
            ),
            temperature=0.1,
            max_tokens=900,
        )

    def report_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
        query_result: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_report_request_messages(
                user_goal=user_goal,
                assistant_plan=assistant_plan,
                query_result=query_result,
            ),
            temperature=0.1,
            max_tokens=500,
        )

    def report(
        self,
        *,
        report_name: str,
        output_format: str,
        sections: list[str],
        query_result: dict[str, object],
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_report_messages(
                report_name=report_name,
                output_format=output_format,
                sections=sections,
                query_result=query_result,
                user_goal=user_goal,
            ),
            temperature=0.2,
            max_tokens=1000,
        )

    def mail_request(
        self,
        *,
        user_goal: str,
        assistant_plan: dict[str, object],
        report_result: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_mail_request_messages(
                user_goal=user_goal,
                assistant_plan=assistant_plan,
                report_result=report_result,
            ),
            temperature=0.1,
            max_tokens=500,
        )

    def mail(
        self,
        *,
        recipient: str,
        subject_style: str,
        report_result: dict[str, object],
        user_goal: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return self._request_json(
            messages=build_mail_messages(
                recipient=recipient,
                subject_style=subject_style,
                report_result=report_result,
                user_goal=user_goal,
            ),
            temperature=0.2,
            max_tokens=900,
        )

    def _request_json(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> tuple[dict[str, object], dict[str, object]]:
        response = self._chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
        parsed = _parse_json_object(str(response.get("content", "")))
        if parsed is None and not response.get("error"):
            response["error"] = "invalid_json_response"
            response["mode"] = "error"
            return {}, response
        return parsed or {}, response

    def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, object]:
        if not self.enabled:
            return self._error_response("", None, 0, "llm_disabled", mode="disabled")
        if not self.api_key:
            return self._error_response("", None, 0, "missing_api_key", mode="error")

        started = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.supports_thinking_toggle and self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
            if self.enable_thinking:
                payload["thinking_budget"] = self.thinking_budget
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            content = exc.read().decode("utf-8", errors="replace")
            return self._error_response("", exc.code, started, f"http_{exc.code}", body=content, mode="error")
        except Exception as exc:
            return self._error_response("", None, started, str(exc), mode="error")

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return self._error_response("", None, started, "invalid_api_response", body=body, mode="error")

        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._error_response("", None, started, "empty_choices", body=body, mode="error")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = ""
        if isinstance(message, dict):
            content = str(message.get("content", ""))
        return {
            "provider": self.provider,
            "model": self.model,
            "mode": "live",
            "content": content,
            "latency_ms": latency_ms,
        }

    def _error_response(
        self,
        content: str,
        status_code: int | None,
        started_at: float | int,
        error_code: str,
        *,
        body: str = "",
        mode: str,
    ) -> dict[str, object]:
        latency_ms = 0
        if started_at:
            latency_ms = int((time.perf_counter() - float(started_at)) * 1000)
        payload = {
            "provider": self.provider,
            "model": self.model,
            "mode": mode,
            "content": content,
            "latency_ms": latency_ms,
            "error": error_code,
        }
        if status_code is not None:
            payload["status_code"] = status_code
        if body:
            payload["body"] = body[:1000]
        return payload
