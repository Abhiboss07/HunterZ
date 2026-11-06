"""Build static site assets for GitHub Pages deployment."""
import os
import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from hunterz.config import load_config
from hunterz.db.session import init_db, get_jobs, get_applications, get_outreach_list
from hunterz.matcher.scorer import is_remote_job
from hunterz.tracker.recruiter_finder import RecruiterFinder

DIST_DIR = Path("dist")
STATIC_DATA_DIR = DIST_DIR / "static_data"


async def build_static_site():
    print("[1/5] Initializing build directory...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

    config = load_config()
    await init_db()
    jobs = await get_jobs(limit=1000)
    apps = await get_applications()
    outreach = await get_outreach_list()
    now = datetime.now(timezone.utc)

    # 1. Generate stats.json
    print("[2/5] Compiling stats.json...")
    active_jobs = [j for j in jobs if (now - j.posted_at.replace(tzinfo=timezone.utc)).total_seconds() <= 48 * 3600] if jobs else []
    fresh_count = len([j for j in active_jobs if (now - j.posted_at.replace(tzinfo=timezone.utc)).total_seconds() <= 3600])
    remote_count = len([j for j in active_jobs if is_remote_job(j)])
    match_count = len([j for j in active_jobs if j.match_score >= 80])
    interviews = len([a for a in apps if a.status == "INTERVIEW"])
    total_boards = len(config.boards.greenhouse) + len(config.boards.lever) + len(config.boards.ashby)

    stats_data = {
        "total_jobs": len(active_jobs) if active_jobs else len(jobs),
        "fresh_jobs": fresh_count,
        "remote_jobs": remote_count,
        "high_match_jobs": match_count,
        "applied_count": len(apps),
        "outreach_count": len(outreach),
        "interviews_count": interviews,
        "monitored_boards": total_boards,
        "is_scanning": False,
        "last_updated": now.isoformat()
    }
    with open(STATIC_DATA_DIR / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats_data, f, indent=2)

    # 2. Generate jobs.json
    print("[3/5] Compiling jobs.json...")
    jobs_data = []
    for j in (active_jobs if active_jobs else jobs):
        age_sec = (now - j.posted_at.replace(tzinfo=timezone.utc)).total_seconds()
        hrs = int(age_sec // 3600)
        mins = int((age_sec % 3600) // 60)
        age_str = f"{hrs}h {mins}m ago" if hrs > 0 else f"{mins}m ago"
        jobs_data.append({
            "id": j.id,
            "external_id": j.external_id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "url": j.url,
            "source": j.source,
            "posted_at": j.posted_at.strftime("%Y-%m-%d %H:%M"),
            "age_str": age_str,
            "age_seconds": age_sec,
            "is_fresh": age_sec <= 3600,
            "is_remote": is_remote_job(j),
            "match_score": j.match_score,
            "description": j.description,
            "status": j.status
        })
    with open(STATIC_DATA_DIR / "jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs_data, f, indent=2)

    # 3. Generate applications.json with visual screenshots
    print("[4/5] Compiling applications.json and outreach.json...")
    finder = RecruiterFinder()
    apps_data = []
    for a in apps:
        recs = await finder.find_recruiters_for_company(a.company)
        safe_c = "".join([c if c.isalnum() else "_" for c in a.company.lower()])
        screenshots = {}
        for step in ["step1_begin", "step2_filled", "step3_submitted"]:
            img_file = Path("output/screenshots") / f"{safe_c}_{step}.png"
            if img_file.exists():
                screenshots[step] = f"./screenshots/{safe_c}_{step}.png"

        apps_data.append({
            "id": a.id,
            "job_id": a.job_id,
            "company": a.company,
            "title": a.title,
            "url": a.url,
            "applied_at": a.applied_at.strftime("%Y-%m-%d %H:%M"),
            "days_elapsed": max(0, (now - a.applied_at.replace(tzinfo=timezone.utc)).days),
            "status": a.status,
            "submission_method": a.submission_method,
            "response_notes": a.response_notes,
            "tailored_bio": a.tailored_bio or "",
            "screenshots": screenshots,
            "recruiter_contacts": [
                {"name": r.name, "title": r.title, "email": r.email, "confidence_score": r.confidence_score}
                for r in recs[:4]
            ]
        })
    with open(STATIC_DATA_DIR / "applications.json", "w", encoding="utf-8") as f:
        json.dump(apps_data, f, indent=2)

    with open(STATIC_DATA_DIR / "outreach.json", "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    with open(STATIC_DATA_DIR / "companies.json", "w", encoding="utf-8") as f:
        comps = []
        for c in config.boards.greenhouse:
            comps.append({"name": c.capitalize(), "handle": c, "platform": "Greenhouse", "career_url": f"https://boards.greenhouse.io/{c}"})
        for c in config.boards.lever:
            comps.append({"name": c.capitalize(), "handle": c, "platform": "Lever", "career_url": f"https://jobs.lever.co/{c}"})
        for c in config.boards.ashby:
            comps.append({"name": c.capitalize(), "handle": c, "platform": "Ashby", "career_url": f"https://jobs.ashbyhq.com/{c}"})
        json.dump(comps, f, indent=2)

    with open(STATIC_DATA_DIR / "profile.json", "w", encoding="utf-8") as f:
        p_dict = config.profile.model_dump()
        # Redact raw secret token in static public build
        p_dict["telegram_bot_token"] = "Configured" if p_dict.get("telegram_bot_token") else ""
        json.dump(p_dict, f, indent=2)

    with open(STATIC_DATA_DIR / "resumes.json", "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    # 4. Copy HTML & Static Assets to dist/
    print("[5/5] Copying web template and screenshots to dist/...")
    shutil.copy("hunterz/web/templates/crm.html", DIST_DIR / "index.html")

    dist_screenshots = DIST_DIR / "screenshots"
    dist_screenshots.mkdir(parents=True, exist_ok=True)
    if Path("output/screenshots").exists():
        for ss in Path("output/screenshots").glob("*.png"):
            shutil.copy(ss, dist_screenshots / ss.name)

    print("✔ Static GitHub Pages site built successfully into dist/!")


if __name__ == "__main__":
    asyncio.run(build_static_site())
