"""Policy Decision Point (locked decision #7).

In-process Python engine behind a stable interface so an OPA / Cedar sidecar
can replace it later without touching call sites. Call sites depend only on
the `PolicyDecisionPoint` Protocol and the `AccessRequest` / `Decision`
dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from eden.security.principal import AuthContext


@dataclass(frozen=True, slots=True)
class AccessRequest:
    auth: AuthContext
    permission: str  # e.g. 'candidates:review'
    resource_type: str
    resource_id: str | None = None
    context: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str
    obligations: tuple[str, ...] = ()

    @classmethod
    def allow(cls, reason: str = "permitted") -> "Decision":
        return cls(True, reason)

    @classmethod
    def deny(cls, reason: str) -> "Decision":
        return cls(False, reason)


@runtime_checkable
class PolicyDecisionPoint(Protocol):
    async def evaluate(self, request: AccessRequest) -> Decision: ...


class InProcessPolicyEngine:
    """P0 engine. Token scope/role check + scoped grant lookup.

    The richer DB-backed effective-access evaluation (RoleAssignment scopes,
    clearance ceilings, deny-overrides, SoD) lands in P1; the interface here
    does not change when it does, nor when this is swapped for OPA/Cedar.
    """

    # Coarse Keycloak realm/client roles that imply a fine permission in P0.
    _ROLE_GRANTS: dict[str, frozenset[str]] = {
        "consultancy_recruiter": frozenset(
            {"candidates:review", "candidates:read", "referrals:read"}
        ),
        "consultancy_owner": frozenset(
            {"candidates:review", "candidates:read", "referrals:read", "tenants:provision"}
        ),
        "partner": frozenset({"referrals:create", "referrals:read", "recruitment:read"}),
        "platform_admin": frozenset({"tenants:provision", "tenants:read"}),
    }

    async def evaluate(self, request: AccessRequest) -> Decision:
        auth = request.auth
        perm = request.permission

        if perm in auth.scopes:
            return Decision.allow(f"token scope grants {perm!r}")

        for role in auth.roles:
            if perm in self._ROLE_GRANTS.get(role, frozenset()):
                return Decision.allow(f"role {role!r} grants {perm!r}")

        return Decision.deny(
            f"principal {auth.keycloak_sub} lacks {perm!r} "
            f"(roles={sorted(auth.roles)}, scopes={sorted(auth.scopes)})"
        )


# Single process-wide PDP instance. Swap this binding to change engines.
_pdp: PolicyDecisionPoint = InProcessPolicyEngine()


def get_pdp() -> PolicyDecisionPoint:
    return _pdp
