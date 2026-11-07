"""Semantic and keyword matching score generator with Remote & Ultra-Fresh Priority."""
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Set, Dict, Any
from hunterz.db.models import JobModel
from hunterz.config import ProfileConfig

CORE_TECH_STACK = {
    "java": 12,
    "python": 12,
    "fastapi": 10,
    "spring boot": 10,
    "rest api": 8,
    "microservices": 8,
    "sql": 7,
    "mysql": 7,
    "redis": 8,
    "mongodb": 7,
    "docker": 8,
    "ci/cd": 6,
    "github actions": 6,
    "distributed systems": 10,
    "concurrency": 7,
    "data pipelines": 8,
    "web scraping": 8,
    "react": 6,
    "typescript": 6
}


SENIOR_OR_MID_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b", r"\barchitect\b",
    r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bmanager\b", r"\bhead of\b",
    r"\bsde[- ]?2\b", r"\bsde[- ]?ii\b", r"\bsde2\b",
    r"\bsde[- ]?3\b", r"\bsde[- ]?iii\b", r"\bsde3\b",
    r"\bsoftware engineer[- ]?(?:2|ii|3|iii|iv|v)\b",
    r"\bsoftware development engineer[- ]?(?:2|ii|3|iii)\b",
    r"\bengineer[- ]?(?:2|ii|3|iii|iv)\b",
    r"\bdeveloper[- ]?(?:2|ii|3|iii)\b",
    r"\bse[- ]?(?:2|ii|3|iii)\b",
    r"\bl[2-6]\b", r"\blevel[- ]?[2-6]\b", r"\bic[2-6]\b", r"\be[2-6]\b",
    r"\bmid[- ]?level\b", r"\bintermediate\b", r"\bexperienced\b"
]

SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "staff", "principal", "architect",
    "director", "vp", "vice president", "manager", "head of", "sde-2", "sde 2", "sde ii",
    "software engineer ii", "software engineer 2", "engineer ii", "engineer 2"
]

FRESHER_KEYWORDS = [
    "fresher", "entry level", "entry-level", "junior", "jr.", "jr ", "graduate",
    "associate", "sde-1", "sde 1", "sde i", "se-1", "se 1", "new grad",
    "early career", "trainee", "0-1", "0-2", "intern", "internship", "campus"
]


def is_remote_job(job: JobModel) -> bool:
    """Detect if job is remote-friendly."""
    text = f"{job.title} {job.location} {job.description}".lower()
    return any(k in text for k in ["remote", "anywhere", "work from home", "wfh", "distributed team"])


def is_fresher_job(job: JobModel) -> bool:
    """
    Detect if job is strictly suitable for freshers / entry-level (0-1 years experience).
    Excludes any senior, lead, staff, or SDE-2 / Level-2+ / 2+ YOE roles.
    """
    title_lower = job.title.lower()
    desc_lower = (job.description or "").lower()

    # 1. Strict rejection if title has any senior or mid-level pattern (SDE-2, SE II, Level 3, etc.)
    for pattern in SENIOR_OR_MID_PATTERNS:
        if re.search(pattern, title_lower):
            return False

    # 2. Strict rejection if description requires 2+ or more years of experience
    if re.search(r"\b([2-9]|1\d)\+?\s*(?:to\s*\d+\s*)?(?:years?|yrs?)\s*(?:of)?\s*(?:relevant|hands-on|industry|software)?\s*experience\b", desc_lower):
        return False
    if re.search(r"\b([2-9]|1\d)\+?\s*(?:years?|yrs?)\b", desc_lower):
        return False

    # 3. Positive match for fresher / entry-level keywords in title
    if any(k in title_lower for k in FRESHER_KEYWORDS):
        return True

    # 4. Positive match for fresher keywords in description
    fresher_desc_phrases = [
        "0-1 year", "0 to 1 year", "0-2 year", "0 to 2 year", "entry level",
        "entry-level", "fresh graduate", "recent graduate", "early career",
        "fresher", "no prior experience", "little to no experience", "b.tech", "college graduate"
    ]
    if any(phrase in desc_lower for phrase in fresher_desc_phrases):
        return True

    # If title is a generic junior/entry title without senior keywords
    is_generic_sde = any(k in title_lower for k in ["software engineer", "sde", "backend engineer", "developer"])
    return is_generic_sde and not re.search(r"\b[2-9]\s*years\b", desc_lower)


def compute_match_score(job: JobModel, profile: ProfileConfig) -> Tuple[int, List[str], List[str]]:
    """
    Computes a 0-100 match score with bonuses for Remote & Ultra-Fresh recency,
    and strict penalties for Senior/SDE-2/High-YOE requirements when candidate is Fresher/Junior.
    Returns: (score, list_of_matched_skills, list_of_missing_skills)
    """
    text = f"{job.title} {job.description}".lower()
    title_lower = job.title.lower()
    score = 35  # Base baseline
    matched_skills: Set[str] = set()
    missing_skills: Set[str] = set()

    for tech, weight in CORE_TECH_STACK.items():
        pattern = r"\b" + re.escape(tech) + r"\b"
        if re.search(pattern, text):
            score += weight
            matched_skills.add(tech)
        else:
            missing_skills.add(tech)

    # 1. Experience & Seniority Calibration (Crucial for Freshers / 0-1 YOE)
    is_candidate_fresher = getattr(profile, "years_experience", 1) <= 1

    is_senior_or_mid = any(re.search(p, title_lower) for p in SENIOR_OR_MID_PATTERNS)
    requires_high_yoe = bool(re.search(r"\b([2-9]|1\d)\+?\s*(?:to\s*\d+\s*)?(?:years?|yrs?)\s*(?:of)?\s*(?:relevant|hands-on|industry|software)?\s*experience\b", text))

    if is_candidate_fresher:
        if is_senior_or_mid:
            score -= 60  # Disqualify SDE-2, SDE-3, Senior, Staff, Lead roles
        elif requires_high_yoe:
            score -= 45  # Disqualify roles requiring 2+ to 10+ years experience

        # Fresher / Entry-Level Priority Bonus (+30)
        if is_fresher_job(job):
            score += 30

    # 2. Remote Job Priority (+15 bonus)
    if is_remote_job(job):
        score += 15

    # 3. Recency Priority (Extra boost for jobs posted within minutes or <1 hour)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    posted = job.posted_at.replace(tzinfo=None) if job.posted_at.tzinfo else job.posted_at
    age = now - posted
    if age <= timedelta(minutes=15):
        score += 20  # Ultra-fresh (<15m)
    elif age <= timedelta(hours=1):
        score += 15  # Fresh (<1h)
    elif age <= timedelta(hours=3):
        score += 8

    # 4. Role Title Alignment (+10)
    if "sde" in title_lower or "software development engineer" in title_lower or "software engineer" in title_lower:
        score += 10
    if "backend" in title_lower:
        score += 10
    if "forward deployed" in title_lower or "fde" in title_lower:
        score += 10

    # Cap score between 0 and 100
    final_score = min(100, max(0, score))
    return final_score, sorted(list(matched_skills)), sorted(list(missing_skills))[:5]
