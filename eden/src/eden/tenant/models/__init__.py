"""Per-tenant ORM template. These tables are created inside every
`client_<uuid>` schema by the provisioner from the SQL template; the ORM
models resolve to the active schema via the request search_path."""

from eden.tenant.models.employment import EmploymentTerm, PayrollBand
from eden.tenant.models.recruitment import (
    Candidate,
    CandidateReferral,
    CandidateSource,
    ReferralState,
)

__all__ = [
    "Candidate",
    "CandidateReferral",
    "CandidateSource",
    "EmploymentTerm",
    "PayrollBand",
    "ReferralState",
]
