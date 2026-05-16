"""Pure unit tests for the referral state machine (spec #4). No DB needed."""

import pytest

from eden.recruitment.state_machine import (
    IllegalTransition,
    apply_transition,
    is_terminal,
    permission_for,
)
from eden.tenant.models.recruitment import ReferralState as S


def test_happy_path_draft_to_approved():
    state = S.DRAFT
    state = apply_transition(state, "submit")
    assert state is S.PARTNER_SUBMITTED
    state = apply_transition(state, "pick_up")
    assert state is S.CONSULTANCY_REVIEWING
    state = apply_transition(state, "approve")
    assert state is S.APPROVED
    assert is_terminal(state)


def test_reject_is_terminal():
    state = apply_transition(S.CONSULTANCY_REVIEWING, "reject")
    assert state is S.REJECTED
    with pytest.raises(IllegalTransition):
        apply_transition(state, "approve")


def test_illegal_jump_draft_to_approved_blocked():
    with pytest.raises(IllegalTransition):
        apply_transition(S.DRAFT, "approve")


def test_unknown_event_blocked():
    with pytest.raises(IllegalTransition):
        apply_transition(S.DRAFT, "teleport")


def test_each_transition_declares_permission():
    assert permission_for(S.DRAFT, "submit") == "referrals:create"
    assert permission_for(S.CONSULTANCY_REVIEWING, "approve") == "candidates:review"
