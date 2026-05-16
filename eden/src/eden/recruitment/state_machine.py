"""Explicit referral state machine (spec #4).

Draft -> Partner_Submitted -> Consultancy_Reviewing -> Approved | Rejected

Transitions are data, not scattered `if` checks. Every transition declares
the permission the actor must hold; the router enforces it via
`RequiresScope`, and `apply_transition` re-checks legality so an illegal
jump (e.g. Draft -> Approved) is impossible even if a caller crafts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from eden.tenant.models.recruitment import ReferralState

S = ReferralState


@dataclass(frozen=True, slots=True)
class Transition:
    src: ReferralState
    dst: ReferralState
    event: str
    required_permission: str


_TRANSITIONS: tuple[Transition, ...] = (
    Transition(S.DRAFT, S.PARTNER_SUBMITTED, "submit", "referrals:create"),
    Transition(S.PARTNER_SUBMITTED, S.CONSULTANCY_REVIEWING, "pick_up", "candidates:review"),
    Transition(S.CONSULTANCY_REVIEWING, S.APPROVED, "approve", "candidates:review"),
    Transition(S.CONSULTANCY_REVIEWING, S.REJECTED, "reject", "candidates:review"),
    # Recruiter can bounce an incomplete referral back to the partner.
    Transition(S.CONSULTANCY_REVIEWING, S.PARTNER_SUBMITTED, "return", "candidates:review"),
)

_BY_EVENT: dict[tuple[ReferralState, str], Transition] = {
    (t.src, t.event): t for t in _TRANSITIONS
}
_TERMINAL: frozenset[ReferralState] = frozenset({S.APPROVED, S.REJECTED})


class IllegalTransition(Exception):
    pass


def is_terminal(state: ReferralState) -> bool:
    return state in _TERMINAL


def permission_for(current: ReferralState, event: str) -> str:
    return resolve(current, event).required_permission


def resolve(current: ReferralState, event: str) -> Transition:
    transition = _BY_EVENT.get((current, event))
    if transition is None:
        raise IllegalTransition(
            f"event {event!r} is not legal from state {current.value!r}"
        )
    return transition


def apply_transition(current: ReferralState, event: str) -> ReferralState:
    """Return the next state, or raise IllegalTransition. Pure function —
    persistence is the caller's responsibility."""
    if is_terminal(current):
        raise IllegalTransition(f"{current.value!r} is terminal; no transitions allowed")
    return resolve(current, event).dst
