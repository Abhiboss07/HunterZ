"""Comprehensive Audit & Performance Test Suite for HunterZ."""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from hunterz.config import HunterZConfig, load_config, ProfileConfig
from hunterz.db.models import JobModel, ApplicationModel
from hunterz.db.session import init_db, save_job, get_jobs, save_application, get_applications
from hunterz.matcher.filter import is_job_eligible
from hunterz.matcher.scorer import compute_match_score
from hunterz.resume.tailor import ResumeTailor
from hunterz.tracker.status_tracker import analyze_rejection_reason


@pytest.fixture
def sample_config():
    return load_config()


@pytest.fixture
def test_db_path(tmp_path):
    return tmp_path / "test_hunterz.db"


def test_config_loading():
    """Verify that configuration loads with valid defaults and structure."""
    cfg = load_config()
    assert cfg.profile.full_name == "Abhishek Yadav"
    assert "SDE-1" in cfg.search.target_roles
    assert "Senior" in cfg.search.exclude_keywords
    assert cfg.apply.mode in ["hybrid", "copilot", "autopilot"]


def test_filter_edge_cases(sample_config):
    """Audit role filtering against false positives and false negatives."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Valid SDE-1
    job1 = JobModel(
        external_id="test_1",
        title="Software Engineer I - Backend",
        company="Stripe",
        location="Remote",
        url="https://stripe.com",
        source="greenhouse",
        posted_at=now - timedelta(hours=2)
    )
    eligible, reason = is_job_eligible(job1, sample_config)
    assert eligible is True

    # 2. Senior role (must be rejected)
    job2 = JobModel(
        external_id="test_2",
        title="Senior Software Engineer",
        company="Uber",
        location="Remote",
        url="https://uber.com",
        source="greenhouse",
        posted_at=now - timedelta(hours=1)
    )
    eligible, reason = is_job_eligible(job2, sample_config)
    assert eligible is False
    assert "Senior" in reason

    # 3. Staff / Principal / Lead (must be rejected)
    for title in ["Staff Engineer", "Principal SDE", "Lead Full Stack Developer", "Engineering Manager"]:
        j = JobModel(
            external_id=f"test_{title}",
            title=title,
            company="Tech Corp",
            location="Remote",
            url="https://tech.com",
            source="lever",
            posted_at=now - timedelta(hours=1)
        )
        eligible, _ = is_job_eligible(j, sample_config)
        assert eligible is False, f"Failed: {title} should be rejected"

    # 4. Forward Deployed Engineer (must be accepted)
    job4 = JobModel(
        external_id="test_4",
        title="Forward Deployed Engineer (FDE)",
        company="Palantir",
        location="Remote",
        url="https://palantir.com",
        source="lever",
        posted_at=now - timedelta(hours=5)
    )
    eligible, _ = is_job_eligible(job4, sample_config)
    assert eligible is True

    # 5. Expired job (> cutoff limit) (must be rejected)
    sample_config.search.strict_max_age = True
    sample_config.search.max_age_hours = 24
    job5 = JobModel(
        external_id="test_5",
        title="SDE-1",
        company="Amazon",
        location="Remote",
        url="https://amazon.com",
        source="greenhouse",
        posted_at=now - timedelta(hours=28)
    )
    eligible, reason = is_job_eligible(job5, sample_config)
    assert eligible is False
    assert "exceeds strict limit" in reason


def test_scorer_accuracy():
    """Verify semantic match scoring reflects Abhishek's core backend tech stack."""
    profile = ProfileConfig()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Job mentioning Java, Spring Boot, Redis, Microservices, REST APIs
    high_match_job = JobModel(
        external_id="test_high",
        title="Backend Software Engineer",
        company="Fintech Inc",
        location="Remote",
        url="https://fintech.com",
        source="greenhouse",
        posted_at=now,
        description="Looking for an engineer with Java, Spring Boot, REST API, Redis, and Microservices experience."
    )
    score, matched, missing = compute_match_score(high_match_job, profile)
    assert score >= 75
    assert "java" in matched
    assert "spring boot" in matched
    assert "redis" in matched


def test_latex_special_char_escaping():
    """Verify that LaTeX characters like &, %, $, #, _, {, } don't break resume tailoring."""
    profile = ProfileConfig()
    tailor = ResumeTailor(profile)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Job description loaded with LaTeX special characters
    tricky_job = JobModel(
        external_id="test_tricky",
        title="Backend Engineer (C# & Python / 50% Microservices)",
        company="R&D Labs #1",
        location="Remote",
        url="https://rd.com",
        source="greenhouse",
        posted_at=now,
        description="Must know R&D workflows, 100% test coverage, $100M throughput, and C# & Java!"
    )
    tex_path, pdf_path = tailor.tailor(tricky_job)
    assert tex_path.exists()
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_db_concurrency_and_integrity(test_db_path):
    """Audit database concurrency and race condition resilience under parallel writes."""
    await init_db(test_db_path)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    jobs = [
        JobModel(
            external_id=f"bulk_job_{i}",
            title=f"Software Engineer {i}",
            company=f"Company {i}",
            location="Remote",
            url=f"https://company{i}.com",
            source="greenhouse",
            posted_at=now,
            match_score=70 + (i % 30)
        )
        for i in range(50)
    ]

    # Write 50 jobs concurrently
    tasks = [save_job(j, test_db_path) for j in jobs]
    results = await asyncio.gather(*tasks)
    assert all(r is not None for r in results)

    # Read back and verify count
    saved = await get_jobs(db_path=test_db_path, limit=100)
    assert len(saved) == 50


def test_rejection_reason_analyzer():
    """Verify parsing of rejection emails into actionable categories."""
    email_1 = "Thank you for your interest. Unfortunately, we have decided to move forward with another candidate who has more years of experience in distributed systems."
    reason_1 = analyze_rejection_reason(email_1)
    assert reason_1 == "Experience / Seniority Mismatch"

    email_2 = "Due to overwhelming number of applicants, the position has been filled. We wish you the best in your search."
    reason_2 = analyze_rejection_reason(email_2)
    assert reason_2 == "Position Filled / High Volume"

    email_3 = "At this time, we are unable to provide visa sponsorship or authorization for this role."
    reason_3 = analyze_rejection_reason(email_3)
    assert reason_3 == "Visa / Work Authorization"
