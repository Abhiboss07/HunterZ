"""FastAPI Backend for HunterZ Web CRM Dashboard."""
import os
import re
import json
import glob
import asyncio
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

from hunterz.config import load_config, HunterZConfig, ProfileConfig
from hunterz.db.session import (
    init_db,
    get_jobs,
    get_job_by_id,
    get_applications,
    save_job,
    save_application,
    update_application_status,
    save_outreach,
    get_outreach_list,
    update_outreach_status,
    delete_outreach
)
from hunterz.db.models import JobModel, ApplicationModel, DirectOutreachModel
from hunterz.scrapers import scrape_all_sources
from hunterz.matcher.filter import is_job_eligible
from hunterz.matcher.scorer import compute_match_score, is_remote_job, is_fresher_job, SENIOR_TITLE_KEYWORDS
from hunterz.resume.tailor import ResumeTailor
from hunterz.applier.direct_ats import DirectATSApplier
from hunterz.applier.browser_applier import BrowserApplier
from hunterz.tracker.notifier import JobNotifier
from hunterz.tracker.recruiter_finder import RecruiterFinder

app = FastAPI(title="HunterZ Web CRM", version="0.2.0")

# Robust absolute path resolution
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output" / "resumes"
SCREENSHOTS_DIR = PROJECT_ROOT / "output" / "screenshots"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/resumes", StaticFiles(directory=str(OUTPUT_DIR)), name="resumes")
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")

# Global scanning state
scan_in_progress = False


class ProfileUpdateRequest(BaseModel):
    full_name: str
    dob: str
    age: int
    email: str
    phone: str
    address_line1: Optional[str] = "Jaunpur"
    address_line2: Optional[str] = "Uttar Pradesh"
    city: Optional[str] = "Jaunpur"
    state: Optional[str] = "Uttar Pradesh"
    postal_code: Optional[str] = "222001"
    country: Optional[str] = "India"
    location: str
    nationality: str
    languages: Optional[str] = "English, Hindi"
    work_authorization: str
    notice_period: str
    willing_to_relocate: bool
    work_mode: Optional[str] = "Remote Priority / WFH"
    salary_expectation: Optional[str] = "Competitive / Negotiable"
    core_skills: Optional[str] = "Java, Python, FastAPI, Spring Boot, Microservices, REST APIs, Distributed Systems, SQL, Redis"
    secondary_skills: Optional[str] = "React, TypeScript, Docker, CI/CD, Git, Linux"
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    bio: Optional[str] = "Backend & Software Development Engineer specializing in high-throughput data automation, microservices, and distributed systems."
    linkedin: str
    github: str
    portfolio: str
    current_role: str
    years_experience: int


class StatusUpdateRequest(BaseModel):
    status: str
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


class OutreachSendRequest(BaseModel):
    job_id: int
    company: str
    title: str
    recruiter_email: str
    email_subject: str
    email_body: str
    resume_pdf_path: Optional[str] = ""
    status: Optional[str] = "DRAFTED"
    notes: Optional[str] = None


class OutreachStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def get_crm_page():
    html_file = TEMPLATES_DIR / "crm.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="CRM template not found")
    with open(html_file, "r", encoding="utf-8") as f:
        return f.read()


def get_age_seconds(dt: datetime, now: datetime) -> float:
    """Safe offset-naive difference in seconds."""
    p = dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
    n = now.replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
    return max(0.0, (n - p).total_seconds())


@app.get("/api/stats")
async def get_stats():
    config = load_config()
    jobs = await get_jobs(limit=1000)
    apps = await get_applications()
    outreach = await get_outreach_list()
    now = datetime.now(timezone.utc)

    # Apply strict 48-hour cutoff to stats so only active fresh jobs are counted
    active_jobs = [j for j in jobs if get_age_seconds(j.posted_at, now) <= 48 * 3600]

    fresh_count = len([j for j in active_jobs if get_age_seconds(j.posted_at, now) <= 3600])
    remote_count = len([j for j in active_jobs if is_remote_job(j)])
    match_count = len([j for j in active_jobs if j.match_score >= 80])
    interviews = len([a for a in apps if a.status == "INTERVIEW"])
    total_boards = len(config.boards.greenhouse) + len(config.boards.lever) + len(config.boards.ashby)

    return {
        "total_jobs": len(active_jobs),
        "fresh_jobs": fresh_count,
        "remote_jobs": remote_count,
        "high_match_jobs": match_count,
        "applied_count": len(apps),
        "outreach_count": len(outreach),
        "interviews_count": interviews,
        "monitored_boards": total_boards,
        "is_scanning": scan_in_progress
    }


@app.get("/api/jobs")
async def get_jobs_list(
    q: Optional[str] = None,
    filter_type: Optional[str] = "all",
    sort_by: Optional[str] = "latest",
    limit: int = 1000
):
    config = load_config()
    jobs = await get_jobs(limit=limit)
    now = datetime.now(timezone.utc)

    res = []
    for j in jobs:
        age_seconds = get_age_seconds(j.posted_at, now)

        # Strict 48-Hour Hard Cutoff Rule: Never show or process jobs older than 48 hours!
        if age_seconds > 48 * 3600:
            continue

        # Search query match
        if q:
            query = q.lower()
            if query not in j.title.lower() and query not in j.company.lower() and query not in (j.location or "").lower() and query not in (j.description or "").lower():
                continue

        # Filter categories
        is_rem = is_remote_job(j)

        is_fresher = is_fresher_job(j)
        is_senior = any(k in j.title.lower() for k in SENIOR_TITLE_KEYWORDS)
        exp_level = "Fresher / Entry-Level (0-1 YOE)" if is_fresher else ("Senior / Lead (3+ YOE)" if is_senior else "Mid-Level (1-3 YOE)")

        if filter_type == "fresh" and age_seconds > 3600:
            continue
        elif filter_type == "fresher" and not is_fresher:
            continue
        elif filter_type == "remote" and not is_rem:
            continue
        elif filter_type == "match" and j.match_score < 75:
            continue
        elif filter_type in ["greenhouse", "lever", "ashby", "linkedin", "remoteok", "weworkremotely", "jobicy", "hackernews", "ycombinator", "wellfound", "arbeitnow"] and j.source.lower() != filter_type.lower():
            continue

        score, matched_skills, missing_skills = compute_match_score(j, config.profile)

        # Human-readable recency badge
        minutes = int(age_seconds / 60)
        hours = int(age_seconds / 3600)
        if minutes <= 15:
            recency_badge = f"🔥 {minutes}m ago"
        elif minutes < 60:
            recency_badge = f"⚡ {minutes}m ago"
        elif hours < 24:
            recency_badge = f"🟢 {hours}h ago"
        else:
            recency_badge = f"🟡 {hours}h ago"

        # Extract direct hiring/recruiter email if present in description
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", j.description or "")
        contact_email = email_match.group(0) if email_match and not any(ext in email_match.group(0).lower() for ext in [".png", ".jpg", ".jpeg", ".webp"]) else None

        # Direct LinkedIn & Google Recruiter Search URLs (guaranteed reliable)
        safe_company_q = urllib.parse.quote(j.company)
        recruiter_search_url = f"https://www.linkedin.com/search/results/people/?keywords=technical%20recruiter%20{safe_company_q}"
        google_recruiter_url = f"https://www.google.com/search?q=site:linkedin.com/in+%28%22technical+recruiter%22+OR+%22talent+acquisition%22+OR+%22engineering+recruiter%22%29+at+%22{safe_company_q}%22"
        manager_search_url = f"https://www.linkedin.com/search/results/people/?keywords=Engineering%20Manager%20{safe_company_q}"

        res.append({
            "id": j.id,
            "external_id": j.external_id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "is_remote": is_rem,
            "is_fresher": is_fresher,
            "experience_level": exp_level,
            "url": j.url,
            "source": j.source,
            "posted_at": j.posted_at.strftime("%Y-%m-%d %H:%M"),
            "age_seconds": age_seconds,
            "recency_badge": recency_badge,
            "match_score": score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "is_remote": is_rem,
            "url": j.url,
            "source": j.source,
            "posted_at": j.posted_at.strftime("%Y-%m-%d %H:%M"),
            "age_seconds": age_seconds,
            "recency_badge": recency_badge,
            "match_score": j.match_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "contact_email": contact_email,
            "recruiter_search_url": recruiter_search_url,
            "google_recruiter_url": google_recruiter_url,
            "manager_search_url": manager_search_url,
            "description": j.description,
            "status": j.status
        })

    # Sort options:
    if sort_by == "latest":
        res.sort(key=lambda x: x["age_seconds"])
    elif sort_by == "match":
        res.sort(key=lambda x: (x["match_score"], -x["age_seconds"]), reverse=True)
    elif sort_by == "remote":
        res.sort(key=lambda x: (x["is_remote"], -x["age_seconds"]), reverse=True)
    elif sort_by == "company":
        res.sort(key=lambda x: x["company"].lower())

    return res


@app.get("/api/applications")
async def get_applications_list():
    apps = await get_applications()
    now = datetime.now(timezone.utc)
    res = []
    for a in apps:
        applied_dt = a.applied_at.replace(tzinfo=timezone.utc) if not a.applied_at.tzinfo else a.applied_at
        days_elapsed = max(0, (now - applied_dt).days)

        if a.status in ["INTERVIEW", "OFFER"]:
            follow_up_advice = f"Active Stage: Prepare interview questions for {a.company}"
        elif a.status == "REJECTED":
            follow_up_advice = "Archived application"
        elif days_elapsed < 4:
            follow_up_advice = f"Day {days_elapsed}: Awaiting initial recruiter review (No action needed yet)"
        elif days_elapsed < 7:
            follow_up_advice = f"Day {days_elapsed}: 🔔 Send polite LinkedIn connection request to {a.company} recruiter"
        else:
            follow_up_advice = f"Day {days_elapsed}: ⚠️ Send follow-up check-in note to hiring manager"

        safe_c = urllib.parse.quote(a.company)
        google_recruiter_url = f"https://www.google.com/search?q=site:linkedin.com/in+%28%22technical+recruiter%22+OR+%22talent+acquisition%22+OR+%22engineering+recruiter%22%29+at+%22{safe_c}%22"
        linkedin_recruiter_url = f"https://www.linkedin.com/search/results/people/?keywords=technical%20recruiter%20{safe_c}"

        # Parse provided details JSON safely
        details = {}
        if a.provided_details:
            try:
                details = json.loads(a.provided_details)
            except Exception:
                details = {}

        # Read LaTeX snippet if available
        tex_snippet = ""
        if a.resume_tex_path and Path(a.resume_tex_path).exists():
            try:
                with open(a.resume_tex_path, "r", encoding="utf-8") as f:
                    tex_snippet = f.read()[:2000]
            except Exception:
                pass

        pdf_filename = Path(a.resume_pdf_path).name if a.resume_pdf_path else ""

        # Check for visual audit screenshots
        safe_c_file = re.sub(r'[^a-zA-Z0-9_-]', '_', a.company.lower())
        screenshots = {}
        for step in ["step1_begin", "step2_filled", "step3_submitted"]:
            img_file = SCREENSHOTS_DIR / f"{safe_c_file}_{step}.png"
            if img_file.exists():
                screenshots[step] = f"/screenshots/{safe_c_file}_{step}.png"

        # Discovered recruiters via OSINT finder
        finder = RecruiterFinder()
        recruiter_contacts = await finder.find_recruiters_for_company(a.company)
        contact_list = [
            {
                "name": c.name,
                "title": c.title,
                "email": c.email,
                "confidence_score": c.confidence_score,
                "linkedin_url": c.linkedin_url,
                "email_type": c.email_type
            }
            for c in recruiter_contacts
        ]

        res.append({
            "id": a.id,
            "job_id": a.job_id,
            "company": a.company,
            "title": a.title,
            "url": a.url,
            "resume_pdf_path": a.resume_pdf_path,
            "resume_pdf_url": f"/resumes/{pdf_filename}" if pdf_filename else "",
            "resume_tex_path": a.resume_tex_path,
            "resume_tex_snippet": tex_snippet,
            "applied_at": a.applied_at.strftime("%Y-%m-%d %H:%M"),
            "days_elapsed": days_elapsed,
            "follow_up_advice": follow_up_advice,
            "recruiter_search_url": linkedin_recruiter_url,
            "google_recruiter_url": google_recruiter_url,
            "status": a.status,
            "submission_method": a.submission_method,
            "response_notes": a.response_notes,
            "rejection_reason": a.rejection_reason,
            "tailored_bio": a.tailored_bio or "",
            "provided_details": details,
            "screenshots": screenshots,
            "recruiter_contacts": contact_list
        })
    return res


@app.get("/api/recruiters/{company}")
async def get_company_recruiters(company: str):
    """Retrieve discovered recruiter emails and contacts for a company."""
    finder = RecruiterFinder()
    contacts = await finder.find_recruiters_for_company(company)
    return [
        {
            "name": c.name,
            "title": c.title,
            "email": c.email,
            "company": c.company,
            "domain": c.domain,
            "linkedin_url": c.linkedin_url,
            "confidence_score": c.confidence_score,
            "email_type": c.email_type,
            "source": c.source
        }
        for c in contacts
    ]


@app.get("/api/hook/{job_id}")
async def get_cover_letter_hook(job_id: int):
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")

    hook_text = (
        f"Hi {job.company} Team,\n\n"
        f"I'm Abhishek, a Backend Engineer specializing in Java, Python, FastAPI, and microservices architectures. "
        f"I've built a production-grade in-memory Distributed Key-Value Store with AOF write-ahead durability and LRU cache eviction, "
        f"as well as a cloud-native Voice AI SaaS with LiveKit telephony and real-time WebSocket metrics. "
        f"Seeing your opening for {job.title}, my hands-on background in high-throughput backend systems and automated data pipelines aligns directly with what you are scaling. I'd love to connect!\n\n"
        f"Best,\n"
        f"Abhishek Yadav\n"
        f"Phone: +91-9580818926 | Email: abhicps19@gmail.com\n"
        f"GitHub: https://github.com/Abhiboss07 | LinkedIn: https://linkedin.com/in/abhishek-yadav-4738032b7/"
    )
    safe_subject = urllib.parse.quote(f"Application: {job.title} - Abhishek Yadav")
    safe_body = urllib.parse.quote(hook_text)
    return {
        "company": job.company,
        "title": job.title,
        "hook_text": hook_text,
        "mailto_url": f"mailto:?subject={safe_subject}&body={safe_body}"
    }


@app.post("/api/applications/{app_id}/status")
async def set_app_status(app_id: int, req: StatusUpdateRequest):
    await update_application_status(
        app_id,
        req.status,
        rejection_reason=req.rejection_reason,
        notes=req.notes
    )
    return {"success": True}


async def _run_background_scan():
    global scan_in_progress
    scan_in_progress = True
    try:
        config = load_config()
        raw_jobs = await scrape_all_sources(config)
        for job in raw_jobs:
            eligible, _ = is_job_eligible(job, config)
            if not eligible:
                continue
            score, _, _ = compute_match_score(job, config.profile)
            job.match_score = score
            job.status = "MATCHED" if score >= 60 else "NEW"
            await save_job(job)
    except Exception as e:
        print(f"Background scan error: {e}")
    finally:
        scan_in_progress = False


@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    global scan_in_progress
    if scan_in_progress:
        return {"status": "already_running"}
    background_tasks.add_task(_run_background_scan)
    return {"status": "started"}


@app.post("/api/tailor/{job_id}")
async def tailor_for_job(job_id: int):
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")

    config = load_config()
    tailor_engine = ResumeTailor(config.profile)
    tex_path, pdf_path = tailor_engine.tailor(job)

    # Read rendered LaTeX snippet
    snippet = ""
    if tex_path.exists():
        with open(tex_path, "r", encoding="utf-8") as f:
            snippet = f.read()

    return {
        "success": True,
        "company": job.company,
        "title": job.title,
        "tex_path": str(tex_path),
        "pdf_path": str(pdf_path),
        "pdf_url": f"/resumes/{pdf_path.name}",
        "tex_snippet": snippet[:1500]
    }


@app.post("/api/apply/{job_id}")
async def apply_to_job(job_id: int, dry_run: bool = False):
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")

    config = load_config()
    config.apply.dry_run = dry_run

    tailor_engine = ResumeTailor(config.profile)
    direct_applier = DirectATSApplier(config)
    browser_applier = BrowserApplier(config)

    tex_path, pdf_path, ctx = tailor_engine.tailor_with_context(job)

    # Resolve destination URL if job is from an aggregator (Arbeitnow, WWR, etc.)
    target_source = job.source.lower()
    canonical_url = await browser_applier.resolve_canonical_url(job.url)
    target_url = canonical_url

    # Check if URL directly points to an ATS
    if "ashbyhq.com" in target_url:
        target_source = "ashby"
    elif "greenhouse.io" in target_url:
        target_source = "greenhouse"
    elif "lever.co" in target_url:
        target_source = "lever"

    if target_source in ["greenhouse", "lever"]:
        success, msg = await direct_applier.apply(job, pdf_path, tex_path)
        method = "DIRECT_REST"
        audit = {"canonical_url": target_url, "screenshots": {}}
    else:
        success, msg, audit = await browser_applier.apply(job, pdf_path, return_audit=True)
        method = "BROWSER_ASHBY_AUTOMATED" if "ashby" in audit.get("canonical_url", "") else "BROWSER"

    tailored_bio = ctx.get("tailored_bio", "")
    why_pitch = ctx.get("why_apply_pitch", "")
    details_dict = {
        "full_name": config.profile.full_name,
        "dob": config.profile.dob,
        "age": config.profile.age,
        "email": config.profile.email,
        "phone": config.profile.phone,
        "address_line1": getattr(config.profile, "address_line1", "Jaunpur"),
        "address_line2": getattr(config.profile, "address_line2", "Uttar Pradesh"),
        "city": getattr(config.profile, "city", "Jaunpur"),
        "state": getattr(config.profile, "state", "Uttar Pradesh"),
        "postal_code": getattr(config.profile, "postal_code", "222001"),
        "country": getattr(config.profile, "country", "India"),
        "location": config.profile.location,
        "languages": config.profile.languages,
        "work_mode": config.profile.work_mode,
        "notice_period": config.profile.notice_period,
        "work_authorization": config.profile.work_authorization,
        "salary_expectation": config.profile.salary_expectation,
        "linkedin": config.profile.linkedin,
        "github": config.profile.github,
        "portfolio": config.profile.portfolio,
        "summary": ctx.get("summary", ""),
        "why_apply_pitch": why_pitch,
        "audit_screenshots": audit.get("screenshots", {}),
        "canonical_url": audit.get("canonical_url", target_url)
    }

    # If automated application succeeded, mark SUBMITTED; if it requires manual completion (e.g. login wall / custom questions), mark PREPARED
    status_val = "SUBMITTED" if success else "PREPARED"

    app_record = ApplicationModel(
        job_id=job.id or 0,
        company=job.company,
        title=job.title,
        url=job.url,
        resume_pdf_path=str(pdf_path),
        resume_tex_path=str(tex_path),
        status=status_val,
        submission_method=method,
        response_notes=msg,
        tailored_bio=tailored_bio,
        provided_details=json.dumps(details_dict)
    )
    saved_id = await save_application(app_record)

    return {
        "success": True,
        "application_id": saved_id,
        "status": status_val,
        "message": msg,
        "method": method,
        "pdf_url": f"/resumes/{pdf_path.name}",
        "tailored_bio": tailored_bio,
        "why_apply_pitch": why_pitch,
        "career_url": job.url
    }


@app.get("/api/outreach/generate/{job_id}")
async def generate_recruiter_outreach(job_id: int):
    job = await get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")

    config = load_config()
    tailor_engine = ResumeTailor(config.profile)
    tex_path, pdf_path, ctx = tailor_engine.tailor_with_context(job)

    # 1. Discover Recruiter Email (look in job description or leave unverified)
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", job.description or "")
    is_verified = False
    if email_match and not any(ext in email_match.group(0).lower() for ext in [".png", ".jpg", ".jpeg", ".webp"]):
        discovered_email = email_match.group(0)
        is_verified = True
    else:
        # Do not guess fake unverified emails like careers@company.com which bounce!
        # Provide targeted recruiter search query URLs
        discovered_email = ""

    safe_c = urllib.parse.quote(job.company)
    google_recruiter_url = f"https://www.google.com/search?q=site:linkedin.com/in+%28%22technical+recruiter%22+OR+%22talent+acquisition%22+OR+%22engineering+recruiter%22%29+at+%22{safe_c}%22"
    linkedin_recruiter_url = f"https://www.linkedin.com/search/results/people/?keywords=technical%20recruiter%20{safe_c}"

    # 2. Craft high-converting tailored email pitch
    subject = f"Application: {job.title} — Abhishek Yadav (Backend / Distributed Systems)"
    body = (
        f"Hi {job.company} Hiring Team,\n\n"
        f"I'm Abhishek, a Backend & Software Development Engineer specializing in Java, Python, FastAPI, and microservices architectures. "
        f"I came across your opening for {job.title} and wanted to reach out directly.\n\n"
        f"A few quick highlights that align with what {job.company} is building:\n"
        f"• Distributed Systems: Architected a production-grade in-memory Distributed Key-Value Store in Java 17 with AOF write-ahead durability, O(1) LRU eviction, and 144 concurrency/unit tests.\n"
        f"• Cloud-Native Microservices: Engineered a Voice AI SaaS platform with FastAPI, LiveKit telephony, WebSockets, and Redis persistence.\n"
        f"• Data Pipelines & Automation: Built high-throughput Python pipelines boosting ingestion by 40% with zero-downtime CI/CD workflows.\n\n"
        f"I've attached my tailored resume (PDF) compiled specifically for {job.company}. I'd love to connect and learn more about your technical roadmaps.\n\n"
        f"Best regards,\n"
        f"Abhishek Yadav\n"
        f"Phone: +91-9580818926 | Email: abhicps19@gmail.com\n"
        f"GitHub: https://github.com/Abhiboss07 | LinkedIn: https://linkedin.com/in/abhishek-yadav-4738032b7/\n"
        f"Portfolio: https://portfolio-abhishek-01.vercel.app"
    )

    safe_sub = urllib.parse.quote(subject)
    safe_body = urllib.parse.quote(body)
    mailto_url = f"mailto:{discovered_email}?subject={safe_sub}&body={safe_body}" if discovered_email else f"mailto:?subject={safe_sub}&body={safe_body}"

    return {
        "job_id": job.id,
        "company": job.company,
        "title": job.title,
        "recruiter_email": discovered_email,
        "is_verified": is_verified,
        "google_recruiter_url": google_recruiter_url,
        "linkedin_recruiter_url": linkedin_recruiter_url,
        "email_subject": subject,
        "email_body": body,
        "mailto_url": mailto_url,
        "resume_pdf_url": f"/resumes/{pdf_path.name}",
        "resume_pdf_path": str(pdf_path)
    }


@app.post("/api/outreach/send")
async def send_recruiter_outreach(req: OutreachSendRequest):
    outreach = DirectOutreachModel(
        job_id=req.job_id,
        company=req.company,
        title=req.title,
        recruiter_email=req.recruiter_email,
        email_subject=req.email_subject,
        email_body=req.email_body,
        resume_pdf_path=req.resume_pdf_path or "",
        status=req.status or "DRAFTED",
        notes=req.notes or "Drafted for recruiter outreach"
    )
    saved_id = await save_outreach(outreach)
    safe_sub = urllib.parse.quote(req.email_subject)
    safe_body = urllib.parse.quote(req.email_body)
    mailto_url = f"mailto:{req.recruiter_email}?subject={safe_sub}&body={safe_body}"

    return {
        "success": True,
        "outreach_id": saved_id,
        "status": req.status or "DRAFTED",
        "message": f"Direct outreach recorded as {req.status or 'DRAFTED'} for {req.company}",
        "mailto_url": mailto_url
    }


@app.post("/api/outreach/{outreach_id}/status")
async def update_outreach_record_status(outreach_id: int, req: OutreachStatusRequest):
    await update_outreach_status(outreach_id, req.status, notes=req.notes)
    return {"success": True, "outreach_id": outreach_id, "status": req.status}


@app.delete("/api/outreach/{outreach_id}")
async def delete_outreach_record(outreach_id: int):
    await delete_outreach(outreach_id)
    return {"success": True, "deleted_id": outreach_id}


@app.get("/api/outreach")
async def get_all_outreach():
    records = await get_outreach_list()
    res = []
    for r in records:
        pdf_name = Path(r.resume_pdf_path).name if r.resume_pdf_path else ""
        res.append({
            "id": r.id,
            "job_id": r.job_id,
            "company": r.company,
            "title": r.title,
            "recruiter_email": r.recruiter_email,
            "email_subject": r.email_subject,
            "email_body": r.email_body,
            "resume_pdf_url": f"/resumes/{pdf_name}" if pdf_name else "",
            "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M"),
            "status": r.status,
            "notes": r.notes
        })
    return res


@app.get("/api/resumes")
async def get_resumes_list():
    if not OUTPUT_DIR.exists():
        return []

    files = sorted(OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True)
    res = []
    for f in files:
        name_parts = f.stem.split("_")
        company = name_parts[1] if len(name_parts) > 1 else "Master"
        fmt = f.suffix.upper().replace(".", "")
        size_kb = f"{f.stat().st_size / 1024:.1f} KB"
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        res.append({
            "filename": f.name,
            "company": company,
            "format": fmt,
            "size": size_kb,
            "mtime": mtime,
            "url": f"/resumes/{f.name}"
        })
    return res


@app.get("/api/profile")
async def get_profile():
    config = load_config()
    return config.profile.model_dump()


@app.post("/api/profile")
async def update_profile(req: ProfileUpdateRequest):
    config = load_config()
    p = config.profile

    p.full_name = req.full_name
    p.dob = req.dob
    p.age = req.age
    p.email = req.email
    p.phone = req.phone
    p.address_line1 = req.address_line1 or "Jaunpur"
    p.address_line2 = req.address_line2 or "Uttar Pradesh"
    p.city = req.city or "Jaunpur"
    p.state = req.state or "Uttar Pradesh"
    p.postal_code = req.postal_code or "222001"
    p.country = req.country or "India"
    p.location = req.location or f"{p.city}, {p.state}, {p.country}"
    p.nationality = req.nationality
    p.languages = req.languages or "English, Hindi"
    p.work_authorization = req.work_authorization
    p.notice_period = req.notice_period
    p.willing_to_relocate = req.willing_to_relocate
    p.work_mode = req.work_mode or "Remote Priority / WFH"
    p.salary_expectation = req.salary_expectation or "Competitive / Negotiable"
    p.core_skills = req.core_skills or ""
    p.secondary_skills = req.secondary_skills or ""
    p.telegram_bot_token = req.telegram_bot_token
    p.telegram_chat_id = req.telegram_chat_id
    p.bio = req.bio or ""
    p.linkedin = req.linkedin
    p.github = req.github
    p.portfolio = req.portfolio
    p.current_role = req.current_role
    p.years_experience = req.years_experience

    # Write back to config.yaml
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data["profile"] = p.model_dump()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False)

    return {"success": True, "profile": p.model_dump()}


@app.get("/api/companies")
async def get_companies_directory():
    config = load_config()
    res = []

    for c in config.boards.greenhouse:
        res.append({
            "name": c.capitalize(),
            "handle": c,
            "platform": "Greenhouse",
            "api_url": f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs",
            "career_url": f"https://boards.greenhouse.io/{c}",
            "auto_apply": True
        })

    for c in config.boards.lever:
        res.append({
            "name": c.capitalize(),
            "handle": c,
            "platform": "Lever",
            "api_url": f"https://api.lever.co/v0/postings/{c}",
            "career_url": f"https://jobs.lever.co/{c}",
            "auto_apply": True
        })

    for c in config.boards.ashby:
        res.append({
            "name": c.capitalize(),
            "handle": c,
            "platform": "Ashby",
            "api_url": f"https://api.ashbyhq.com/posting-api/job-board/{c}",
            "career_url": f"https://jobs.ashbyhq.com/{c}",
            "auto_apply": True
        })

    return res
