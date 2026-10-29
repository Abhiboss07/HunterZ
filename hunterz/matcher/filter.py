"""Job role and experience level filtering logic."""
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple
from hunterz.db.models import JobModel
from hunterz.config import HunterZConfig


def is_job_eligible(job: JobModel, config: HunterZConfig) -> Tuple[bool, str]:
    """
    Check if a job matches target engineering roles and doesn't violate exclusion rules.
    Returns: (is_eligible, reason)
    """
    title_lower = job.title.lower()

    # 1. Exclude senior / executive / internship roles if present
    for keyword in config.search.exclude_keywords:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, title_lower):
            return False, f"Excluded keyword '{keyword}' found in title"

    # 2. Check target engineering roles
    matched_role = None
    for role in config.search.target_roles:
        pattern = r"\b" + re.escape(role.lower()) + r"\b"
        if re.search(pattern, title_lower):
            matched_role = role
            break

    if not matched_role:
        return False, "Title does not match target roles (SDE, Backend, Full Stack, FDE)"

    # 3. Location filtering (if specified)
    if config.search.locations:
        loc_lower = (job.location or "").lower()
        cfg_locs = [l.lower() for l in config.search.locations]

        # If 'anywhere' or 'all' is in locations or candidate is willing to relocate
        if "anywhere" in cfg_locs or "all" in cfg_locs or getattr(config.profile, "willing_to_relocate", True):
            loc_matched = True
        elif not loc_lower or "remote" in loc_lower:
            loc_matched = True
        else:
            loc_matched = False
            for loc in cfg_locs:
                if loc in loc_lower:
                    loc_matched = True
                    break
            # Also match common US & Global tech hubs if US or India is configured
            if not loc_matched and ("united states" in cfg_locs or "us" in cfg_locs):
                us_hubs = ["ca", "ny", "sf", "san francisco", "new york", "seattle", "wa", "austin", "tx", "boston", "ma", "palo alto"]
                if any(re.search(r"\b" + re.escape(hub) + r"\b", loc_lower) for hub in us_hubs):
                    loc_matched = True

        if not loc_matched:
            return False, f"Location '{job.location}' outside target regions"

    # 4. Language Barrier Filtering (English & Hindi prioritized, foreign mandatory languages excluded)
    full_text = f"{job.title} {job.description}".lower()
    mandatory_foreign_langs = [
        "fluent in japanese", "japanese n1", "japanese n2", "jlpt", "japanese required", "business japanese",
        "fluent in german", "deutsch c1", "deutsch b2", "fließend deutsch", "deutschkenntnisse", "german required",
        "fluent in french", "french required", "parler français", "french c1",
        "fluent in mandarin", "chinese fluent", "mandarin required", "chinese required",
        "fluent in spanish", "spanish required", "español requerido",
        "fluent in russian", "russian required", "fluent in korean", "korean required"
    ]
    for barrier in mandatory_foreign_langs:
        if barrier in full_text:
            return False, f"Foreign language barrier detected ('{barrier}') - English/Hindi required"

    # 5. Strict 48-Hour Hard Cutoff Rule: Discard any job older than max_age_hours (default 48h)
    cutoff = config.search.max_age_hours if config.search.max_age_hours else 48
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    posted = job.posted_at.replace(tzinfo=None) if job.posted_at.tzinfo else job.posted_at
    age = now - posted
    if age > timedelta(hours=cutoff):
        return False, f"Job age ({age.total_seconds() / 3600:.1f}h) exceeds strict limit ({cutoff}h)"

    return True, f"Matched role '{matched_role}'"
