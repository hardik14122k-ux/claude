"""Payroll engine — Indian labour law compliant.

Components:
  Earnings:    Basic, HRA, Special Allowance, Conveyance, Medical, LTA, Bonus.
  Deductions:  EPF (12% of basic, capped at ₹15k basic),
               ESI (0.75% of gross when gross ≤ ₹21k),
               Professional Tax (per state slab),
               Labour Welfare Fund (per state),
               TDS (old/new regime, FY 2024-25 slabs).
  Employer:    EPF (12% of capped basic), ESI (3.25%),
               LWF (employer share), Gratuity accrual (4.81% of basic).

All location-dependent rates (HRA %, PT slabs, LWF, min wages) live on the
PayrollLocation row, so adding a new state is a data change — never a code
change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# ---- Statutory constants (FY 2024-25) ----

EPF_RATE = 0.12                      # 12% on basic (employee + employer each)
EPF_BASIC_CEILING = 15_000           # Basic ceiling for EPF computation
EPS_RATE = 0.0833                    # 8.33% (subset of employer 12%)
EPS_CEILING = 1_250                  # Cap on EPS portion
ESI_EMPLOYEE_RATE = 0.0075           # 0.75% of gross
ESI_EMPLOYER_RATE = 0.0325           # 3.25% of gross
ESI_GROSS_CEILING = 21_000           # Above this, ESI not applicable
GRATUITY_RATE = 0.0481               # 4.81% of basic accrued annually

STD_DEDUCTION_OLD = 50_000           # Standard deduction, old regime
STD_DEDUCTION_NEW = 75_000           # FY 2024-25 onwards, new regime
HEALTH_EDU_CESS = 0.04               # 4% on tax + surcharge

# New regime slabs (FY 2024-25)
TDS_SLABS_NEW = [
    (300_000,  0.00),
    (700_000,  0.05),
    (1_000_000, 0.10),
    (1_200_000, 0.15),
    (1_500_000, 0.20),
    (None,      0.30),
]

# Old regime slabs (without exemptions logic; user-supplied taxable income)
TDS_SLABS_OLD = [
    (250_000,   0.00),
    (500_000,   0.05),
    (1_000_000, 0.20),
    (None,      0.30),
]


@dataclass
class Location:
    """Slim DTO over the payroll_locations row."""
    state: str
    city: str
    is_metro: bool = False
    hra_basic_pct: float = 40.0          # 40 non-metro, 50 metro
    pt_slabs: list[dict] = field(default_factory=list)  # see _compute_pt
    lwf_employee_monthly: float = 0.0
    lwf_employer_monthly: float = 0.0
    min_wage_unskilled: float = 0.0
    min_wage_semi_skilled: float = 0.0
    min_wage_skilled: float = 0.0


@dataclass
class Structure:
    """Annualised salary structure derived from CTC + location."""
    ctc_annual: float
    basic_annual: float
    hra_annual: float
    special_allowance_annual: float
    conveyance_annual: float
    medical_annual: float
    lta_annual: float
    bonus_annual: float
    employer_pf_annual: float
    employer_eps_annual: float
    employer_esi_annual: float
    gratuity_annual: float

    @property
    def basic_monthly(self) -> float:        return round(self.basic_annual / 12, 2)
    @property
    def hra_monthly(self) -> float:          return round(self.hra_annual / 12, 2)
    @property
    def special_monthly(self) -> float:      return round(self.special_allowance_annual / 12, 2)
    @property
    def conveyance_monthly(self) -> float:   return round(self.conveyance_annual / 12, 2)
    @property
    def medical_monthly(self) -> float:      return round(self.medical_annual / 12, 2)
    @property
    def lta_monthly(self) -> float:          return round(self.lta_annual / 12, 2)
    @property
    def gross_monthly(self) -> float:
        return round(
            self.basic_monthly + self.hra_monthly + self.special_monthly
            + self.conveyance_monthly + self.medical_monthly + self.lta_monthly,
            2,
        )


def build_structure(
    ctc_annual: float,
    location: Location,
    basic_pct: float = 40.0,
    conveyance_monthly: float = 0.0,
    medical_monthly: float = 0.0,
    lta_annual: float = 0.0,
    bonus_annual: float = 0.0,
) -> Structure:
    """Decompose annual CTC into the standard Indian payroll components.

    Strategy: Basic is a % of CTC (default 40%, customisable per employee).
    HRA is a % of basic (40% non-metro, 50% metro — set on location). The
    employer EPF + EPS, Gratuity, and any fixed allowances are subtracted
    from CTC; the remainder becomes Special Allowance so totals reconcile
    exactly.
    """
    basic_annual = round(ctc_annual * basic_pct / 100, 2)
    hra_annual = round(basic_annual * location.hra_basic_pct / 100, 2)

    epf_basic_capped = min(basic_annual / 12, EPF_BASIC_CEILING)
    employer_pf_monthly = epf_basic_capped * EPF_RATE
    employer_eps_monthly = min(epf_basic_capped * EPS_RATE, EPS_CEILING)
    employer_pf_annual = round(employer_pf_monthly * 12, 2)
    employer_eps_annual = round(employer_eps_monthly * 12, 2)
    gratuity_annual = round(basic_annual * GRATUITY_RATE, 2)

    fixed_outflows = (
        basic_annual + hra_annual
        + employer_pf_annual + gratuity_annual
        + (conveyance_monthly + medical_monthly) * 12
        + lta_annual + bonus_annual
    )
    special = max(0.0, ctc_annual - fixed_outflows)

    # ESI is applied only when monthly gross ≤ ₹21k; we provision but
    # the monthly engine zeroes it out otherwise.
    monthly_gross_estimate = (
        basic_annual / 12 + hra_annual / 12 + special / 12
        + conveyance_monthly + medical_monthly + lta_annual / 12
    )
    employer_esi_annual = (
        round(monthly_gross_estimate * ESI_EMPLOYER_RATE * 12, 2)
        if monthly_gross_estimate <= ESI_GROSS_CEILING else 0.0
    )

    return Structure(
        ctc_annual=ctc_annual,
        basic_annual=basic_annual,
        hra_annual=hra_annual,
        special_allowance_annual=round(special, 2),
        conveyance_annual=round(conveyance_monthly * 12, 2),
        medical_annual=round(medical_monthly * 12, 2),
        lta_annual=round(lta_annual, 2),
        bonus_annual=round(bonus_annual, 2),
        employer_pf_annual=employer_pf_annual,
        employer_eps_annual=employer_eps_annual,
        employer_esi_annual=employer_esi_annual,
        gratuity_annual=gratuity_annual,
    )


# ---- Statutory deduction calculators ----

def compute_epf_employee(basic_monthly: float) -> float:
    return round(min(basic_monthly, EPF_BASIC_CEILING) * EPF_RATE, 2)


def compute_employer_pf_split(basic_monthly: float) -> tuple[float, float]:
    """Return (EPF_3.67%, EPS_8.33%) capped at the EPS ceiling."""
    capped = min(basic_monthly, EPF_BASIC_CEILING)
    eps = min(capped * EPS_RATE, EPS_CEILING)
    epf = capped * EPF_RATE - eps
    return round(epf, 2), round(eps, 2)


def compute_esi(gross_monthly: float, side: str = "employee") -> float:
    if gross_monthly > ESI_GROSS_CEILING:
        return 0.0
    rate = ESI_EMPLOYEE_RATE if side == "employee" else ESI_EMPLOYER_RATE
    return round(gross_monthly * rate, 2)


def compute_pt(gross_monthly: float, slabs: Iterable[dict], month: int = 1) -> float:
    """Professional Tax from a list of slabs.

    Each slab is `{"max_gross": float|None, "amount": float, "feb_amount": float?}`.
    Slabs must be ordered ascending by max_gross. The first slab whose max_gross
    is ≥ gross_monthly applies; max_gross=None matches anything (i.e. the top slab).
    feb_amount handles Maharashtra's ₹300 February surcharge.
    """
    for slab in slabs:
        cap = slab.get("max_gross")
        if cap is None or gross_monthly <= cap:
            if month == 2 and slab.get("feb_amount") is not None:
                return float(slab["feb_amount"])
            return float(slab.get("amount", 0))
    return 0.0


def compute_lwf(location: Location, side: str = "employee") -> float:
    return location.lwf_employee_monthly if side == "employee" else location.lwf_employer_monthly


def compute_tds_annual(taxable_income: float, regime: str = "new") -> float:
    """Annual income tax under chosen regime, including 4% cess. No surcharge."""
    slabs = TDS_SLABS_NEW if regime == "new" else TDS_SLABS_OLD
    tax = 0.0
    prev_cap = 0.0
    for cap, rate in slabs:
        upper = cap if cap is not None else taxable_income
        if taxable_income > prev_cap:
            taxable_in_slab = min(taxable_income, upper) - prev_cap
            if taxable_in_slab > 0:
                tax += taxable_in_slab * rate
        prev_cap = upper if cap is not None else prev_cap
        if cap is not None and taxable_income <= cap:
            break

    # Section 87A rebate — full waiver up to ₹7L (new) / ₹5L (old)
    rebate_cap = 700_000 if regime == "new" else 500_000
    if taxable_income <= rebate_cap:
        tax = 0.0

    tax_with_cess = tax * (1 + HEALTH_EDU_CESS)
    return round(tax_with_cess, 2)


def compute_tds_monthly(
    annual_gross: float,
    annual_other_income: float = 0.0,
    annual_exemptions: float = 0.0,    # HRA exemption, 80C, etc. (old regime)
    regime: str = "new",
) -> float:
    std_deduction = STD_DEDUCTION_NEW if regime == "new" else STD_DEDUCTION_OLD
    taxable = max(0.0, annual_gross + annual_other_income - std_deduction - annual_exemptions)
    return round(compute_tds_annual(taxable, regime) / 12, 2)


# ---- Monthly payslip generator ----

def generate_payslip(
    *,
    employee: dict,
    structure: Structure,
    location: Location,
    month: int,
    year: int,
    working_days: int,
    paid_days: float,
    tds_override: float | None = None,
    other_earnings: dict | None = None,
    other_deductions: dict | None = None,
) -> dict:
    """Compute a monthly payslip dict with full earnings/deductions/employer breakdown."""
    factor = (paid_days / working_days) if working_days else 0.0

    earnings = {
        "basic":             round(structure.basic_monthly * factor, 2),
        "hra":               round(structure.hra_monthly * factor, 2),
        "special_allowance": round(structure.special_monthly * factor, 2),
        "conveyance":        round(structure.conveyance_monthly * factor, 2),
        "medical":           round(structure.medical_monthly * factor, 2),
        "lta":               round(structure.lta_monthly * factor, 2),
    }
    if other_earnings:
        for k, v in other_earnings.items():
            earnings[k] = round(float(v), 2)
    gross = round(sum(earnings.values()), 2)

    epf_emp = compute_epf_employee(earnings["basic"])
    esi_emp = compute_esi(gross, side="employee")
    pt = compute_pt(gross, location.pt_slabs, month=month)
    lwf_emp = compute_lwf(location, side="employee")

    if tds_override is not None:
        tds = round(float(tds_override), 2)
    else:
        annual_gross = structure.gross_monthly * 12  # uncalibrated for LOP
        tds = compute_tds_monthly(annual_gross, regime=employee.get("tax_regime", "new"))

    deductions = {
        "epf":              epf_emp,
        "esi":              esi_emp,
        "professional_tax": pt,
        "lwf":              lwf_emp,
        "tds":              tds,
    }
    if other_deductions:
        for k, v in other_deductions.items():
            deductions[k] = round(float(v), 2)
    total_deductions = round(sum(deductions.values()), 2)

    employer_pf, employer_eps = compute_employer_pf_split(earnings["basic"])
    employer = {
        "epf":      employer_pf,
        "eps":      employer_eps,
        "esi":      compute_esi(gross, side="employer"),
        "lwf":      compute_lwf(location, side="employer"),
        "gratuity": round(earnings["basic"] * GRATUITY_RATE, 2),
    }

    net = round(gross - total_deductions, 2)
    ctc_total = round(gross + sum(employer.values()), 2)

    return {
        "month": month,
        "year": year,
        "working_days": working_days,
        "paid_days": paid_days,
        "earnings": earnings,
        "deductions": deductions,
        "employer_contributions": employer,
        "gross_earnings": gross,
        "total_deductions": total_deductions,
        "net_pay": net,
        "ctc_total": ctc_total,
    }
