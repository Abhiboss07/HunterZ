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


def is_remote_job(job: JobModel) -> bool:
    """Detect if job is remote-friendly."""
    text = f"{job.title} {job.location} {job.description}".lower()
    return any(k in text for k in ["remote", "anywhere", "work from home", "wfh", "distributed team"])


def compute_match_score(job: JobModel, profile: ProfileConfig) -> Tuple[int, List[str], List[str]]:
    """
    Computes a 0-100 match score with bonuses for Remote & Ultra-Fresh recency.
    Returns: (score, list_of_matched_skills, list_of_missing_skills)
    """
    text = f"{job.title} {job.description}".lower()
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

    # 1. Remote Job Priority (+15 bonus)
    if is_remote_job(job):
        score += 15

    # 2. Recency Priority (Extra boost for jobs posted within minutes or <1 hour)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    posted = job.posted_at.replace(tzinfo=None) if job.posted_at.tzinfo else job.posted_at
    age = now - posted
    if age <= timedelta(minutes=15):
        score += 20  # Ultra-fresh (<15m)
    elif age <= timedelta(hours=1):
        score += 15  # Fresh (<1h)
    elif age <= timedelta(hours=3):
        score += 8

    # 3. Role Title Alignment (+10)
    title_lower = job.title.lower()
    if "sde" in title_lower or "software development engineer" in title_lower:
        score += 10
    if "backend" in title_lower:
        score += 10
    if "forward deployed" in title_lower or "fde" in title_lower:
        score += 10

    # Cap score between 0 and 100
    final_score = min(100, max(0, score))
    return final_score, sorted(list(matched_skills)), sorted(list(missing_skills))[:5]
