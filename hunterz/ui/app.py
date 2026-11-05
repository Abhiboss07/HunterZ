"""Main Textual Application for HunterZ TUI."""
import asyncio
import webbrowser
from datetime import datetime, timezone
from typing import Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Tabs, Tab, Static, Button
from hunterz.config import HunterZConfig, load_config
from hunterz.ui.theme import TUI_CSS
from hunterz.ui.views.feed import FeedView
from hunterz.ui.views.tracker import TrackerView
from hunterz.ui.views.profile_editor import ProfileEditorView
from hunterz.ui.views.resume_inspector import ResumeInspectorView
from hunterz.matcher.scorer import is_remote_job
from hunterz.db.session import (
    init_db,
    get_jobs,
    get_applications,
    save_job,
    save_application,
    update_application_status
)
from hunterz.db.models import JobModel, ApplicationModel
from hunterz.scrapers import scrape_all_sources
from hunterz.matcher.filter import is_job_eligible
from hunterz.matcher.scorer import compute_match_score
from hunterz.resume.tailor import ResumeTailor
from hunterz.applier.direct_ats import DirectATSApplier
from hunterz.applier.browser_applier import BrowserApplier


class HunterZApp(App):
    """Autonomous CLI/TUI Job Hunter and Tracker."""

    CSS = TUI_CSS
    TITLE = "HUNTERZ // Autonomous SDE Job Hunter & Resume Tailor"
    SUB_TITLE = "Local-First • Real-Time Scraper • Auto-Apply Engine"

    BINDINGS = [
        Binding("s", "scan_jobs", "Scan Now (Scrape)", priority=True),
        Binding("a", "apply_current", "Apply to Job", priority=True),
        Binding("t", "tailor_current", "Tailor Resume", priority=True),
        Binding("r", "refresh_data", "Refresh Data", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, config: Optional[HunterZConfig] = None):
        super().__init__()
        self.config = config or load_config()
        self.tailor = ResumeTailor(self.config.profile)
        self.direct_applier = DirectATSApplier(self.config)
        self.browser_applier = BrowserApplier(self.config)
        self.is_scanning = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        total_boards = len(self.config.boards.greenhouse) + len(self.config.boards.lever) + len(self.config.boards.ashby)

        with Horizontal(id="stats-panel"):
            with Vertical(classes="stat-box"):
                yield Static("⚡ ULTRA-FRESH (<1H)", classes="stat-label")
                yield Static("0", id="stat-fresh", classes="stat-val-cyan")
            with Vertical(classes="stat-box"):
                yield Static("🌐 REMOTE JOBS", classes="stat-label")
                yield Static("0", id="stat-remote", classes="stat-val-green")
            with Vertical(classes="stat-box"):
                yield Static("🎯 TOP MATCH (≥80%)", classes="stat-label")
                yield Static("0", id="stat-matched", classes="stat-val-green")
            with Vertical(classes="stat-box"):
                yield Static("📤 APPLIED", classes="stat-label")
                yield Static("0", id="stat-applied", classes="stat-val-amber")
            with Vertical(classes="stat-box"):
                yield Static("🏢 MONITORED BOARDS", classes="stat-label")
                yield Static(str(total_boards), id="stat-boards", classes="stat-val-purple")

        yield Tabs(
            Tab("Job Pipeline (CRM)", id="tab-feed"),
            Tab("Application Tracker", id="tab-tracker"),
            Tab("Company Resumes", id="tab-resumes"),
            Tab("Profile & Settings (CRM)", id="tab-config"),
            id="main-tabs"
        )

        with Vertical(id="views-container"):
            yield FeedView(self.config.profile, id="view-feed")
            yield TrackerView(id="view-tracker")
            yield ResumeInspectorView(self.config, id="view-resumes")
            yield ProfileEditorView(self.config, id="view-config")

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize database and load existing data."""
        await init_db()

        # Switch to feed view initially
        self.query_one("#view-tracker").display = False
        self.query_one("#view-resumes").display = False
        self.query_one("#view-config").display = False

        await self.refresh_dashboard_data()

        # Run an initial background scan if database has few jobs
        jobs = await get_jobs()
        if len(jobs) == 0:
            asyncio.create_task(self.action_scan_jobs())

    async def refresh_dashboard_data(self) -> None:
        """Reload jobs, applications, and update UI tables and stat counters."""
        jobs = await get_jobs(limit=500)
        apps = await get_applications()
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Update Feed, Tracker & Resumes
        feed_view = self.query_one("#view-feed", FeedView)
        feed_view.update_jobs(jobs)

        tracker_view = self.query_one("#view-tracker", TrackerView)
        tracker_view.update_applications(apps)

        resumes_view = self.query_one("#view-resumes", ResumeInspectorView)
        resumes_view.refresh_resumes()

        # Update Stats
        fresh_count = len([j for j in jobs if (now - j.posted_at).total_seconds() <= 3600])
        remote_count = len([j for j in jobs if is_remote_job(j)])
        matched_jobs = len([j for j in jobs if j.match_score >= 80])
        applied_count = len(apps)
        total_boards = len(self.config.boards.greenhouse) + len(self.config.boards.lever) + len(self.config.boards.ashby)

        self.query_one("#stat-fresh", Static).update(str(fresh_count))
        self.query_one("#stat-remote", Static).update(str(remote_count))
        self.query_one("#stat-matched", Static).update(str(matched_jobs))
        self.query_one("#stat-applied", Static).update(str(applied_count))
        self.query_one("#stat-boards", Static).update(str(total_boards))

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle tab switching."""
        tab_id = event.tab.id
        self.query_one("#view-feed").display = (tab_id == "tab-feed")
        self.query_one("#view-tracker").display = (tab_id == "tab-tracker")
        self.query_one("#view-resumes").display = (tab_id == "tab-resumes")
        self.query_one("#view-config").display = (tab_id == "tab-config")

    async def action_scan_jobs(self) -> None:
        """Run scraping and matching in background."""
        if self.is_scanning:
            self.notify("A job scan is already running...", severity="warning")
            return

        self.is_scanning = True
        self.notify("Scanning Greenhouse, Lever, Ashby, LinkedIn, and Startup portals (<24h)...", severity="information")

        try:
            raw_jobs = await scrape_all_sources(self.config)
            added_count = 0

            for job in raw_jobs:
                eligible, reason = is_job_eligible(job, self.config)
                if not eligible:
                    continue

                score, matched_skills, _ = compute_match_score(job, self.config.profile)
                job.match_score = score
                job.status = "MATCHED" if score >= 60 else "NEW"

                saved_id = await save_job(job)
                if saved_id:
                    added_count += 1

                # If Autopilot mode is on and match score >= threshold, auto apply!
                if self.config.apply.mode == "autopilot" and score >= self.config.apply.min_match_score_to_auto_apply:
                    await self._execute_application(job)

            self.notify(f"Scan complete: Found and saved {added_count} eligible SDE jobs!", severity="information")
        except Exception as e:
            self.notify(f"Scan failed: {str(e)}", severity="error")
        finally:
            self.is_scanning = False
            await self.refresh_dashboard_data()

    async def _execute_application(self, job: JobModel) -> None:
        """Tailor resume and submit application for job."""
        self.notify(f"Tailoring resume for {job.company}...", severity="information")
        tex_path, pdf_path = self.tailor.tailor(job)

        self.notify(f"Submitting application to {job.company} ({job.source})...", severity="information")

        if job.source in ["greenhouse", "lever", "ashby"]:
            success, msg = await self.direct_applier.apply(job, pdf_path, tex_path)
            method = "DIRECT_REST"
        else:
            success, msg = await self.browser_applier.apply(job, pdf_path)
            method = "BROWSER"

        if success:
            app = ApplicationModel(
                job_id=job.id or 0,
                company=job.company,
                title=job.title,
                url=job.url,
                resume_pdf_path=str(pdf_path),
                resume_tex_path=str(tex_path),
                status="SUBMITTED",
                submission_method=method,
                response_notes=msg
            )
            await save_application(app)
            self.notify(f"Application sent to {job.company}! PDF: {pdf_path.name}", severity="information")
        else:
            self.notify(f"Failed to apply to {job.company}: {msg}", severity="error")

        await self.refresh_dashboard_data()

    async def action_apply_current(self) -> None:
        """Apply to currently selected job in feed."""
        feed = self.query_one("#view-feed", FeedView)
        job = feed.selected_job
        if not job:
            self.notify("Please select a job from the table first.", severity="warning")
            return

        await self._execute_application(job)

    async def action_tailor_current(self) -> None:
        """Generate tailored resume for currently selected job without submitting."""
        feed = self.query_one("#view-feed", FeedView)
        job = feed.selected_job
        if not job:
            self.notify("Please select a job from the table first.", severity="warning")
            return

        self.notify(f"Tailoring resume for {job.company}...", severity="information")
        tex_path, pdf_path = self.tailor.tailor(job)
        self.notify(f"Tailored resume saved:\nPDF: {pdf_path}\nTeX: {tex_path}", severity="information")

    async def action_refresh_data(self) -> None:
        """Refresh table and stats."""
        await self.refresh_dashboard_data()
        self.notify("Dashboard refreshed.", severity="information")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle UI button clicks."""
        btn_id = event.button.id

        if btn_id == "btn-apply":
            await self.action_apply_current()
        elif btn_id == "btn-tailor":
            await self.action_tailor_current()
        elif btn_id == "btn-open-url":
            feed = self.query_one("#view-feed", FeedView)
            if feed.selected_job and feed.selected_job.url:
                webbrowser.open(feed.selected_job.url)
        elif btn_id == "btn-ignore":
            feed = self.query_one("#view-feed", FeedView)
            if feed.selected_job:
                feed.selected_job.status = "IGNORED"
                await save_job(feed.selected_job)
                await self.refresh_dashboard_data()
        elif btn_id == "btn-status-interview":
            tracker = self.query_one("#view-tracker", TrackerView)
            if tracker.selected_app and tracker.selected_app.id:
                await update_application_status(tracker.selected_app.id, "INTERVIEW")
                await self.refresh_dashboard_data()
        elif btn_id == "btn-status-rejected":
            tracker = self.query_one("#view-tracker", TrackerView)
            if tracker.selected_app and tracker.selected_app.id:
                await update_application_status(
                    tracker.selected_app.id,
                    "REJECTED",
                    rejection_reason="Position filled / General ATS screening"
                )
                await self.refresh_dashboard_data()
        elif btn_id == "btn-status-offer":
            tracker = self.query_one("#view-tracker", TrackerView)
            if tracker.selected_app and tracker.selected_app.id:
                await update_application_status(tracker.selected_app.id, "OFFER")
                await self.refresh_dashboard_data()
