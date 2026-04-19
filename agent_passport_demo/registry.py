from __future__ import annotations

from .models import AgentIdentity


class AgentRegistry:
    def __init__(self, identities: list[AgentIdentity]) -> None:
        self._identities = {identity.principal: identity for identity in identities}

    def authenticate(self, principal: str, auth_token: str | None) -> bool:
        identity = self._identities.get(principal)
        if identity is None:
            return False
        return bool(auth_token) and identity.auth_token == auth_token

    def get(self, principal: str) -> AgentIdentity | None:
        return self._identities.get(principal)

    def export(self) -> list[dict[str, str]]:
        return [
            {
                "principal": identity.principal,
                "role": identity.role,
                "auth_token_preview": self._mask(identity.auth_token),
            }
            for identity in self._identities.values()
        ]

    def _mask(self, token: str) -> str:
        if len(token) <= 8:
            return token
        return f"{token[:4]}...{token[-4:]}"
