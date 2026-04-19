from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Any


CAPABILITY_TYPE = "CAP"
CAPABILITY_VERSION = 1
CAPABILITY_AUDIENCE = "agent-gateway"
REQUIRED_CLAIMS: tuple[str, ...] = (
    "jti",
    "iss",
    "sub",
    "aud",
    "iat",
    "nbf",
    "exp",
    "task_id",
    "action",
    "resource",
    "to_principal",
    "ver",
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class CapabilityTokenService:
    def __init__(
        self,
        secret: str,
        *,
        audience: str = CAPABILITY_AUDIENCE,
        version: int = CAPABILITY_VERSION,
        max_iat_age_seconds: int = 86400,
        iat_future_tolerance_seconds: int = 300,
    ) -> None:
        self.secret = secret.encode("utf-8")
        self.audience = audience
        self.version = version
        self.max_iat_age_seconds = max_iat_age_seconds
        self.iat_future_tolerance_seconds = iat_future_tolerance_seconds

    def issue(self, claims: dict[str, Any]) -> str:
        payload = dict(claims)
        payload.setdefault("aud", self.audience)
        payload.setdefault("ver", self.version)
        header = {"alg": "HS256", "typ": CAPABILITY_TYPE, "ver": self.version}
        encoded_header = _b64url_encode(
            json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        encoded_payload = _b64url_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = self._sign(f"{encoded_header}.{encoded_payload}")
        return f"{encoded_header}.{encoded_payload}.{signature}"

    def verify(self, token: str) -> tuple[bool, dict[str, Any] | None, str, str]:
        parts = token.split(".")
        if len(parts) != 3:
            return False, None, "capability_malformed", "capability token malformed"

        encoded_header, encoded_payload, encoded_signature = parts
        expected_signature = self._sign(f"{encoded_header}.{encoded_payload}")
        if not hmac.compare_digest(encoded_signature, expected_signature):
            return False, None, "capability_invalid_signature", "capability signature invalid"

        try:
            header = json.loads(_b64url_decode(encoded_header).decode("utf-8"))
            claims = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return False, None, "capability_malformed", "capability token malformed"

        if not isinstance(header, dict) or not isinstance(claims, dict):
            return False, None, "capability_malformed", "capability token malformed"

        if header.get("typ") != CAPABILITY_TYPE:
            return False, None, "capability_malformed", "capability token type invalid"
        if header.get("ver") != self.version:
            return False, None, "capability_invalid_version", "capability version invalid"

        ok, reason_code, reason_text = self._validate_claims(claims)
        if not ok:
            return False, None, reason_code, reason_text

        return True, claims, "allow", "capability signature and claims valid"

    def _validate_claims(self, claims: dict[str, Any]) -> tuple[bool, str, str]:
        for claim in REQUIRED_CLAIMS:
            if claim not in claims or claims[claim] in (None, ""):
                return (
                    False,
                    "capability_missing_claim",
                    f"capability missing claim: {claim}",
                )

        if claims.get("ver") != self.version:
            return False, "capability_invalid_version", "capability version invalid"
        if str(claims.get("aud", "")) != self.audience:
            return False, "capability_invalid_audience", "capability audience invalid"

        exp = self._parse_claim_time(claims.get("exp"))
        nbf = self._parse_claim_time(claims.get("nbf"))
        iat = self._parse_claim_time(claims.get("iat"))
        if exp is None or nbf is None or iat is None:
            return False, "capability_malformed", "capability timestamp claim invalid"
        if nbf > exp:
            return False, "capability_malformed", "capability time range invalid"
        if nbf < iat:
            return False, "capability_iat_out_of_range", "capability nbf before iat"
        if iat > exp:
            return False, "capability_iat_out_of_range", "capability iat after exp"

        now = datetime.now(tz=timezone.utc)
        if exp <= now:
            return False, "capability_expired", "capability expired"
        if nbf > now:
            return False, "capability_not_yet_valid", "capability not yet valid"

        if iat > now + timedelta(seconds=self.iat_future_tolerance_seconds):
            return False, "capability_iat_out_of_range", "capability iat too far in future"
        if iat < now - timedelta(seconds=self.max_iat_age_seconds):
            return False, "capability_iat_out_of_range", "capability iat too old"

        return True, "allow", "capability claims valid"

    def _parse_claim_time(self, value: Any) -> datetime | None:
        try:
            if isinstance(value, (int, float)):
                parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
            elif isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                return None
        except (ValueError, OSError, OverflowError):
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _sign(self, signing_input: str) -> str:
        digest = hmac.new(
            self.secret,
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return _b64url_encode(digest)


def mask_capability_token(token: str) -> str:
    if len(token) <= 18:
        return token
    return f"{token[:10]}...{token[-10:]}"
