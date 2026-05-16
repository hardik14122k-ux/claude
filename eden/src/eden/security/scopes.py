"""Keycloak RBAC embedded in FastAPI dependencies (spec #4).

Usage:

    @router.post("/referrals/{rid}/review")
    async def review(rid: str, auth: AuthContext = Depends(RequiresScope("candidates:review"))):
        ...

`RequiresScope` resolves the verified `AuthContext`, asks the PDP for a
decision, and raises 403 on deny. The PDP indirection means the same call
sites work when the engine is swapped (locked decision #7).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from eden.policy.pdp import AccessRequest, PolicyDecisionPoint, get_pdp
from eden.security.principal import AuthContext, get_auth


class RequiresScope:
    """Dependency factory binding one endpoint to one fine-grained permission."""

    def __init__(self, permission: str, *, resource_type: str | None = None) -> None:
        self.permission = permission
        self.resource_type = resource_type or permission.split(":", 1)[0]

    async def __call__(
        self,
        request: Request,
        auth: AuthContext = Depends(get_auth),
        pdp: PolicyDecisionPoint = Depends(get_pdp),
    ) -> AuthContext:
        decision = await pdp.evaluate(
            AccessRequest(
                auth=auth,
                permission=self.permission,
                resource_type=self.resource_type,
                resource_id=request.path_params.get("id")
                or request.path_params.get("rid"),
            )
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "permission": self.permission,
                        "reason": decision.reason},
            )
        return auth
