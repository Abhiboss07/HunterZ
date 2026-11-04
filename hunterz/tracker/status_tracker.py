"""Application status tracker and rejection reason analyzer."""
import re
from typing import Optional, Dict


REJECTION_PATTERNS = {
    "Position Filled / High Volume": [
        r"filled the position",
        r"moved forward with another candidate",
        r"overwhelming number of applicants",
        r"high volume of applications",
        r"pursuing other candidates",
        r"decided to close this role"
    ],
    "Experience / Seniority Mismatch": [
        r"years of experience",
        r"more senior",
        r"looking for someone with more",
        r"level of experience",
        r"seeking candidates whose background"
    ],
    "Visa / Work Authorization": [
        r"sponsorship",
        r"authorized to work",
        r"visa requirements",
        r"cannot sponsor",
        r"right to work"
    ],
    "Location / Relocation": [
        r"relocate",
        r"specific location",
        r"outside our hiring zones",
        r"remote only in"
    ]
}


def analyze_rejection_reason(email_text: str) -> str:
    """
    Parses rejection email content and extracts the actionable root cause.
    """
    text_lower = email_text.lower()

    for reason, patterns in REJECTION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                return reason

    return "General ATS Screening / Experience Alignment"
