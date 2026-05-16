"""Pluggable Indian HR compliance rules engine.

Each rule is a callable that takes a context dict and returns a list of
findings (warnings/errors). Rules are pure: no DB writes. Adding a new
state-specific rule is a one-liner registration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import payroll as engine


@dataclass
class Finding:
    severity: str          # info | warn | error
    code: str
    message: str
    detail: dict | None = None


Rule = Callable[[dict], list[Finding]]
_REGISTRY: dict[str, Rule] = {}


def register(code: str) -> Callable[[Rule], Rule]:
    def deco(fn: Rule) -> Rule:
        _REGISTRY[code] = fn
        return fn
    return deco


def evaluate(context: dict, *, only: list[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for code, rule in _REGISTRY.items():
        if only and code not in only:
            continue
        try:
            findings.extend(rule(context) or [])
        except Exception as exc:
            findings.append(Finding("error", f"{code}.crash", f"Rule {code} crashed: {exc}"))
    return findings


# ===== Built-in rules =====

@register("pf.eligibility")
def _pf_eligibility(ctx: dict) -> list[Finding]:
    """EPF is mandatory if employer has ≥20 employees AND basic ≤ ₹15k.
    Higher-basic employees can opt out only at first joining."""
    out = []
    basic = float(ctx.get("basic_monthly") or 0)
    if basic > engine.EPF_BASIC_CEILING and not ctx.get("epf_voluntary"):
        out.append(Finding("info", "pf.above_ceiling",
            f"Basic ₹{basic:,.0f} > EPF ceiling ₹{engine.EPF_BASIC_CEILING:,.0f}; "
            "PF will be capped at the statutory ceiling unless voluntary contribution is chosen."))
    return out


@register("esi.eligibility")
def _esi_eligibility(ctx: dict) -> list[Finding]:
    """ESI applies when monthly gross ≤ ₹21k (₹25k for persons with disability)."""
    out = []
    gross = float(ctx.get("gross_monthly") or 0)
    pwd = bool(ctx.get("person_with_disability"))
    ceiling = 25_000 if pwd else engine.ESI_GROSS_CEILING
    if gross <= ceiling:
        out.append(Finding("info", "esi.applicable",
            f"Gross ₹{gross:,.0f} ≤ ESI ceiling ₹{ceiling:,.0f}; ESI applicable."))
    else:
        out.append(Finding("info", "esi.not_applicable",
            f"Gross ₹{gross:,.0f} > ESI ceiling ₹{ceiling:,.0f}; ESI not applicable."))
    return out


@register("pt.state_required")
def _pt_required(ctx: dict) -> list[Finding]:
    """Professional Tax is state-administered. States with PT include Maharashtra,
    Karnataka, Gujarat, West Bengal, Telangana, Tamil Nadu, etc."""
    out = []
    state = (ctx.get("state") or "").lower()
    pt_states = {"maharashtra", "karnataka", "gujarat", "west bengal", "telangana",
                 "tamil nadu", "andhra pradesh", "kerala", "madhya pradesh", "assam",
                 "odisha", "tripura", "meghalaya", "sikkim", "puducherry"}
    if state in pt_states and not ctx.get("pt_slabs"):
        out.append(Finding("warn", "pt.slabs_missing",
            f"State '{state.title()}' levies PT but no slabs configured for the location."))
    return out


@register("gratuity.eligibility")
def _gratuity_eligibility(ctx: dict) -> list[Finding]:
    """Gratuity payable on exit after ≥5 years (4 yrs 240 days in some HCs)."""
    out = []
    months = int(ctx.get("tenure_months") or 0)
    if months >= 60:
        basic = float(ctx.get("basic_monthly") or 0)
        years = months // 12
        amount = (basic * 15 / 26) * years
        out.append(Finding("info", "gratuity.payable",
            f"Eligible for gratuity (~₹{amount:,.0f}) after {years} year(s).",
            {"years": years, "estimated_amount": round(amount, 2)}))
    elif months >= 56:  # 4 yrs 8 months ≈ 56
        out.append(Finding("info", "gratuity.near_eligible",
            f"Approaching gratuity eligibility ({months} months / 60)."))
    return out


@register("tds.regime_compare")
def _tds_compare(ctx: dict) -> list[Finding]:
    """Recommend the regime that produces lower tax."""
    out = []
    gross = float(ctx.get("annual_gross") or 0)
    if gross <= 0:
        return out
    chapter_via_old = float(ctx.get("chapter_via") or 0)
    new_taxable = max(0, gross - engine.STD_DEDUCTION_NEW)
    old_taxable = max(0, gross - engine.STD_DEDUCTION_OLD - chapter_via_old)
    new_tax = engine.compute_tds_annual(new_taxable, regime="new")
    old_tax = engine.compute_tds_annual(old_taxable, regime="old")
    better = "new" if new_tax <= old_tax else "old"
    diff = abs(new_tax - old_tax)
    out.append(Finding("info", "tds.regime_recommend",
        f"Recommended regime: {better} (saves ~₹{diff:,.0f})",
        {"new_tax": new_tax, "old_tax": old_tax, "recommended": better}))
    return out


@register("min_wage.check")
def _min_wage(ctx: dict) -> list[Finding]:
    out = []
    basic = float(ctx.get("basic_monthly") or 0)
    skill_class = ctx.get("skill_class") or "skilled"
    floor = float(ctx.get(f"min_wage_{skill_class}") or 0)
    if floor and basic < floor:
        out.append(Finding("error", "min_wage.below_floor",
            f"Basic ₹{basic:,.0f} below {skill_class} minimum wage ₹{floor:,.0f}."))
    return out


@register("leave.encashment_cap")
def _leave_cap(ctx: dict) -> list[Finding]:
    """Statutory leave encashment exemption is ₹25 lakh (FY 2023-24+)."""
    out = []
    encashed = float(ctx.get("leave_encashment_amount") or 0)
    cap = 2_500_000
    if encashed > cap:
        out.append(Finding("warn", "leave.encashment_taxable",
            f"Leave encashment ₹{encashed:,.0f} exceeds exempt cap ₹{cap:,.0f}; "
            "excess is taxable."))
    return out
