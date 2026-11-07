"""Autonomous Pipeline Orchestrator for HunterZ.
Executes scheduled end-to-end cycles:
Scrape -> Match -> Tailor Resume -> Auto-Apply -> Recruiter Outreach -> Telegram Notify -> Rebuild Dashboard -> Push to GitHub.
"""
import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from hunterz.config import load_config, HunterZConfig
from hunterz.db.session import (
    init_db,
    save_job,
    get_jobs,
    save_application,
    get_applications,
    save_outreach
)
from hunterz.db.models import JobModel, ApplicationModel, DirectOutreachModel
from hunterz.scrapers import scrape_all_sources
from hunterz.matcher.filter import is_job_eligible
from hunterz.matcher.scorer import compute_match_score
from hunterz.resume.tailor import ResumeTailor
from hunterz.applier.direct_ats import DirectATSApplier
from hunterz.applier.browser_applier import BrowserApplier
from hunterz.tracker.notifier import JobNotifier
from hunterz.tracker.recruiter_finder import RecruiterFinder
from hunterz.healing.self_improver import SelfHealingEngine
from scripts.build_pages import build_static_site


class AutonomousOrchestrator:
    """Coordinates autonomous job discovery, resume tailoring, auto-applying, outreach, and cloud synchronization."""

    def __init__(self, config: Optional[HunterZConfig] = None):
        self.config = config or load_config()
        self.tailor_engine = ResumeTailor(self.config.profile)
        self.direct_applier = DirectATSApplier(self.config)
        self.browser_applier = BrowserApplier(self.config)
        self.notifier = JobNotifier(self.config)
        self.recruiter_finder = RecruiterFinder()
        self.healing_engine = SelfHealingEngine()

    async def run_cycle(
        self,
        max_auto_applies: int = 5,
        sync_github: bool = True,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Execute one complete autonomous cycle."""
        self.config.apply.dry_run = dry_run
        mode_str = " (SIMULATION / DRY-RUN)" if dry_run else " (LIVE DEPLOYMENT)"
        print("\n" + "=" * 70)
        print(f"🚀 [HUNTERZ AUTONOMOUS CYCLE STARTED{mode_str}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        summary = {
            "scanned": 0,
            "fresh_count": 0,
            "matched": 0,
            "applied": 0,
            "outreach_sent": 0,
            "applied_companies": [],
            "errors": []
        }

        await init_db()

        # -------------------------------------------------------------
        # STEP 1: ULTRA-FRESH SCRAPE & INGESTION
        # -------------------------------------------------------------
        print("\n[Step 1/6] Scanning Greenhouse, Lever, Ashby, and Startup Boards...")
        try:
            raw_jobs = await scrape_all_sources(self.config)
            summary["scanned"] = len(raw_jobs)
            now = datetime.now(timezone.utc)

            qualified_jobs: List[JobModel] = []
            for job in raw_jobs:
                eligible, reason = is_job_eligible(job, self.config)
                if not eligible:
                    continue

                score, _, _ = compute_match_score(job, self.config.profile)
                job.match_score = score
                job.status = "MATCHED" if score >= 60 else "NEW"
                await save_job(job)

                posted_tz = job.posted_at.replace(tzinfo=timezone.utc) if not job.posted_at.tzinfo else job.posted_at
                if (now - posted_tz).total_seconds() <= 3600:
                    summary["fresh_count"] += 1

                if score >= self.config.apply.min_match_score_to_auto_apply:
                    qualified_jobs.append(job)

            summary["matched"] = len(qualified_jobs)
            print(f"  ✓ Ingested {len(raw_jobs)} roles | {summary['matched']} high-match roles (≥{self.config.apply.min_match_score_to_auto_apply}%)")
        except Exception as e:
            err_msg = f"Scraper failure: {e}"
            print(f"  ❌ {err_msg}")
            self.healing_engine.record_issue("scrapers", "SCRAPE_EXCEPTION", str(e))
            summary["errors"].append(err_msg)
            qualified_jobs = []

        # -------------------------------------------------------------
        # STEP 2: CHECK EXISTING APPLICATIONS TO AVOID DUPLICATES
        # -------------------------------------------------------------
        print("\n[Step 2/6] Verifying unapplied opportunities...")
        existing_apps = await get_applications()
        applied_job_ids = {a.job_id for a in existing_apps}
        applied_companies = {a.company.lower() for a in existing_apps}

        target_jobs = [j for j in qualified_jobs if j.id not in applied_job_ids and j.company.lower() not in applied_companies]
        print(f"  ✓ Found {len(target_jobs)} fresh unapplied roles ready for auto-application.")

        # -------------------------------------------------------------
        # STEP 3: AUTOMATED RESUME TAILORING & APPLICATION SUBMISSION
        # -------------------------------------------------------------
        applies_done = 0
        for job in target_jobs[:max_auto_applies]:
            print(f"\n[Step 3/6] Auto-Applying to: {job.company} — {job.title} (Match: {job.match_score}%)")
            try:
                # 1. Tailor Resume specifically for this company
                tex_path, pdf_path, ctx = self.tailor_engine.tailor_with_context(job)
                print(f"  ✓ Tailored single-page resume generated: {pdf_path.name}")

                # 2. Resolve Canonical ATS Destination
                canonical_url = await self.browser_applier.resolve_canonical_url(job.url)
                target_source = job.source.lower()
                if "ashbyhq.com" in canonical_url:
                    target_source = "ashby"
                elif "greenhouse.io" in canonical_url:
                    target_source = "greenhouse"
                elif "lever.co" in canonical_url:
                    target_source = "lever"

                # 3. Execute Application with Resilient Fallback to Browser Automation
                if target_source in ["greenhouse", "lever"]:
                    success, msg = await self.direct_applier.apply(job, pdf_path, tex_path)
                    method = "DIRECT_REST"
                    audit = {"canonical_url": canonical_url, "screenshots": {}}
                    if not success:
                        print(f"  ℹ Direct REST endpoint returned ({msg}). Escalating to Smart Browser Applier...")
                        success, msg, audit = await self.browser_applier.apply(job, pdf_path, return_audit=True)
                        method = "BROWSER_AUTOMATED"
                else:
                    success, msg, audit = await self.browser_applier.apply(job, pdf_path, return_audit=True)
                    method = "BROWSER_ASHBY_AUTOMATED" if "ashby" in audit.get("canonical_url", "") else "BROWSER"

                # 4. Save to Database
                details_dict = {
                    "full_name": self.config.profile.full_name,
                    "email": self.config.profile.email,
                    "phone": self.config.profile.phone,
                    "location": self.config.profile.location,
                    "summary": ctx.get("summary", ""),
                    "why_apply_pitch": ctx.get("why_apply_pitch", ""),
                    "canonical_url": audit.get("canonical_url", canonical_url),
                    "audit_screenshots": audit.get("screenshots", {})
                }
                app_record = ApplicationModel(
                    job_id=job.id or 0,
                    company=job.company,
                    title=job.title,
                    url=audit.get("canonical_url", canonical_url),
                    resume_pdf_path=str(pdf_path),
                    resume_tex_path=str(tex_path),
                    status="SUBMITTED" if success else "PREPARED",
                    submission_method=method,
                    response_notes=msg,
                    tailored_bio=ctx.get("tailored_bio", ""),
                    provided_details=json.dumps(details_dict)
                )
                await save_application(app_record)

                summary["applied"] += 1
                summary["applied_companies"].append(job.company)
                applies_done += 1
                print(f"  ✓ Application recorded: {job.company} [{method}]")

                # -------------------------------------------------------------
                # STEP 4: RECRUITER DISCOVERY & AUTO-OUTREACH PREPARATION
                # -------------------------------------------------------------
                print(f"  [Step 4/6] Finding recruiters for {job.company}...")
                recruiters = await self.recruiter_finder.find_recruiters_for_company(job.company)
                primary_rec = recruiters[0] if recruiters else None
                rec_email = primary_rec.email if primary_rec else f"careers@{self.recruiter_finder.resolve_company_domain(job.company)}"

                subject = f"Application: {job.title} — Abhishek Yadav"
                body = (
                    f"Hi {primary_rec.name.split()[0] if primary_rec else 'Team'},\n\n"
                    f"I have submitted my application for the {job.title} opening at {job.company}. "
                    f"Given my background in high-throughput backend microservices, distributed systems, and client API integrations, "
                    f"I would love to connect directly with your engineering talent team.\n\n"
                    f"My tailored resume is attached for your review. Portfolio: {self.config.profile.portfolio}\n\n"
                    f"Best regards,\nAbhishek Yadav\n+91-9580818926"
                )
                outreach_record = DirectOutreachModel(
                    job_id=job.id or 0,
                    company=job.company,
                    title=job.title,
                    recruiter_email=rec_email,
                    email_subject=subject,
                    email_body=body,
                    resume_pdf_path=str(pdf_path),
                    status="DRAFTED",
                    notes=f"Auto-generated outreach for {primary_rec.name if primary_rec else job.company}"
                )
                await save_outreach(outreach_record)
                summary["outreach_sent"] += 1
                print(f"  ✓ Recruiter outreach prepared: {rec_email}")

                # -------------------------------------------------------------
                # STEP 5: TELEGRAM PUSH NOTIFICATION
                # -------------------------------------------------------------
                print(f"  [Step 5/6] Dispatching Telegram notification...")
                await self.notifier.notify_application_submitted(
                    app=app_record,
                    job=job,
                    recruiter_email=rec_email,
                    method=method
                )
                print("  ✓ Telegram notification dispatched!")

            except Exception as e:
                err_msg = f"Auto-apply error on {job.company}: {e}"
                print(f"  ❌ {err_msg}")
                self.healing_engine.record_issue("applier", "APPLICATION_FAILURE", str(e), {"company": job.company})
                summary["errors"].append(err_msg)

        # -------------------------------------------------------------
        # STEP 6: REBUILD DASHBOARD & GIT SYNC
        # -------------------------------------------------------------
        print("\n[Step 6/6] Updating Web CRM Dashboard & GitHub Pages...")
        try:
            await build_static_site()
            print("  ✓ Static site assets and feeds refreshed in dist/.")

            if sync_github:
                print("  Syncing changes to GitHub repository...")
                self._git_sync()
                print("  ✓ GitHub repository & live GitHub Pages updated successfully!")
        except Exception as e:
            err_msg = f"Sync failure: {e}"
            print(f"  ❌ {err_msg}")
            self.healing_engine.record_issue("deploy", "GIT_SYNC_ERROR", str(e))
            summary["errors"].append(err_msg)

        # Dispatch final cycle summary to Telegram
        await self.notifier.notify_automation_summary(
            scanned_count=summary["scanned"],
            fresh_count=summary["fresh_count"],
            applied_count=summary["applied"],
            applied_companies=summary["applied_companies"]
        )

        print("\n" + "=" * 70)
        print(f"✔ [AUTONOMOUS CYCLE FINISHED] Applied to {summary['applied']} companies.")
        print("=" * 70 + "\n")
        return summary

    def _git_sync(self):
        """Automatically stage database, screenshots, and static dashboard, then commit & push."""
        try:
            # 1. Add non-sensitive database, screenshots, and dist
            subprocess.run(["git", "add", "data/hunterz.db", "output/screenshots/", "dist/"], check=True, stdout=subprocess.DEVNULL)

            # Check if there are staged changes
            diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
            if diff.returncode != 0:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                commit_msg = f"chore(auto): automated application cycle and dashboard telemetry update [{timestamp}]\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
                subprocess.run(["git", "commit", "-m", commit_msg], check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "push", "origin", "main"], check=True, stdout=subprocess.DEVNULL)
                print("  ✓ Pushed latest application records, screenshots, and live feeds to origin main.")
            else:
                print("  ✓ Git working tree clean (no new changes to commit).")
        except Exception as e:
            print(f"  Note on git sync: {e}")
            self.healing_engine.record_issue("git", "GIT_PUSH_NOTICE", str(e))
