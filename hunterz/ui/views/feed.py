"""Live Job Stream View with CRM Split Dossier and Quick Filters."""
from datetime import datetime, timezone
from typing import List, Optional
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Static, Button, Label
from hunterz.db.models import JobModel
from hunterz.matcher.scorer import compute_match_score, is_remote_job
from hunterz.config import ProfileConfig


class FeedView(Vertical):
    """Interactive CRM job stream with split-screen dossier, skills analysis, and quick filters."""

    def __init__(self, profile: ProfileConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.all_jobs: List[JobModel] = []
        self.displayed_jobs: List[JobModel] = []
        self.selected_job: Optional[JobModel] = None
        self.current_filter: str = "all"

    def compose(self) -> ComposeResult:
        with Horizontal(id="quick-filters"):
            yield Label("Quick Filters: ", classes="stat-label")
            yield Button("All (0)", id="filter-all", variant="primary")
            yield Button("⚡ <1h Fresh (0)", id="filter-fresh")
            yield Button("🌐 Remote (0)", id="filter-remote")
            yield Button("🎯 Match ≥80% (0)", id="filter-match")
            yield Button("Greenhouse", id="filter-greenhouse")
            yield Button("Lever", id="filter-lever")
            yield Button("Ashby", id="filter-ashby")
            yield Button("LinkedIn", id="filter-linkedin")

        with Horizontal(id="feed-split"):
            with Vertical(id="feed-table-container"):
                yield DataTable(id="jobs-table", cursor_type="row")

            with Vertical(id="feed-dossier-container"):
                yield Static(
                    "[bold cyan]CRM Job Dossier[/]\n\n"
                    "[dim]Select any job from the left table to inspect full requirements, "
                    "skills breakdown, and tailored resume alignment preview.[/]",
                    id="dossier-text"
                )
                with Horizontal(id="action-buttons"):
                    yield Button("⚡ Apply & Tailor", id="btn-apply", variant="success")
                    yield Button("📄 Tailor Resume Only", id="btn-tailor")
                    yield Button("🌐 Open URL", id="btn-open-url")
                    yield Button("Archive", id="btn-ignore", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.add_columns("Age / Recency", "Match", "Role / Title", "Company", "Location", "Source")

    def update_jobs(self, jobs: List[JobModel]) -> None:
        """Populate or refresh the jobs table and update filter counts."""
        self.all_jobs = jobs
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Calculate filter metrics
        fresh_count = len([j for j in jobs if (now - j.posted_at).total_seconds() <= 3600])
        remote_count = len([j for j in jobs if is_remote_job(j)])
        match_count = len([j for j in jobs if j.match_score >= 80])

        self.query_one("#filter-all", Button).label = f"All ({len(jobs)})"
        self.query_one("#filter-fresh", Button).label = f"⚡ <1h ({fresh_count})"
        self.query_one("#filter-remote", Button).label = f"🌐 Remote ({remote_count})"
        self.query_one("#filter-match", Button).label = f"🎯 ≥80% ({match_count})"

        self.apply_filter(self.current_filter)

    def apply_filter(self, filter_name: str) -> None:
        self.current_filter = filter_name
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if filter_name == "fresh":
            self.displayed_jobs = [j for j in self.all_jobs if (now - j.posted_at).total_seconds() <= 3600]
        elif filter_name == "remote":
            self.displayed_jobs = [j for j in self.all_jobs if is_remote_job(j)]
        elif filter_name == "match":
            self.displayed_jobs = [j for j in self.all_jobs if j.match_score >= 80]
        elif filter_name in ["greenhouse", "lever", "ashby", "linkedin"]:
            self.displayed_jobs = [j for j in self.all_jobs if j.source == filter_name]
        else:
            self.displayed_jobs = self.all_jobs

        table = self.query_one("#jobs-table", DataTable)
        table.clear()

        for job in self.displayed_jobs:
            diff = now - job.posted_at
            hours = diff.total_seconds() / 3600
            minutes = diff.total_seconds() / 60

            if minutes <= 15:
                age_str = f"[bold green]🔥 {int(minutes)}m ago[/]"
            elif minutes < 60:
                age_str = f"[bold cyan]⚡ {int(minutes)}m ago[/]"
            elif hours < 6:
                age_str = f"[bold yellow]🟡 {int(hours)}h ago[/]"
            else:
                age_str = f"[dim]⚪ {int(hours)}h ago[/]"

            # Format Match Score
            if job.match_score >= 80:
                match_str = f"[bold green]{job.match_score}%[/]"
            elif job.match_score >= 60:
                match_str = f"[yellow]{job.match_score}%[/]"
            else:
                match_str = f"[dim]{job.match_score}%[/]"

            remote_badge = " [green](Remote)[/]" if is_remote_job(job) else ""

            table.add_row(
                age_str,
                match_str,
                job.title,
                f"[bold white]{job.company}[/]",
                f"{job.location[:16]}{remote_badge}",
                f"[{job.source}]",
                key=str(job.external_id)
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "filter-all":
            self.apply_filter("all")
        elif btn_id == "filter-fresh":
            self.apply_filter("fresh")
        elif btn_id == "filter-remote":
            self.apply_filter("remote")
        elif btn_id == "filter-match":
            self.apply_filter("match")
        elif btn_id == "filter-greenhouse":
            self.apply_filter("greenhouse")
        elif btn_id == "filter-lever":
            self.apply_filter("lever")
        elif btn_id == "filter-ashby":
            self.apply_filter("ashby")
        elif btn_id == "filter-linkedin":
            self.apply_filter("linkedin")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection to update rich CRM dossier pane."""
        row_key = event.row_key.value
        matched = [j for j in self.all_jobs if str(j.external_id) == str(row_key)]
        if not matched:
            return

        self.selected_job = matched[0]
        job = self.selected_job

        score, matched_skills, missing_skills = compute_match_score(job, self.profile)
        remote_tag = "[bold green]🌐 100% REMOTE FRIENDLY[/]" if is_remote_job(job) else f"[dim]📍 {job.location}[/]"

        matched_str = ", ".join([f"[bold green]✔ {s}[/]" for s in matched_skills]) if matched_skills else "[dim]General match[/]"
        missing_str = ", ".join([f"[dim]▲ {s}[/]" for s in missing_skills]) if missing_skills else "[dim]None[/]"

        dossier = self.query_one("#dossier-text", Static)
        dossier.update(
            f"[bold cyan]{job.title}[/]\n"
            f"[bold white]{job.company}[/] | {remote_tag} | Source: [cyan]{job.source.upper()}[/]\n"
            f"[bold]Match Score:[/] [bold green]{score}%[/] | Posted: [yellow]{job.posted_at.strftime('%Y-%m-%d %H:%M')}[/]\n\n"
            f"[bold cyan]Technical Skill Alignment[/]\n"
            f"  • {matched_str}\n"
            f"  • Growth Keywords: {missing_str}\n\n"
            f"[bold cyan]Tailored Resume Alignment Strategy[/]\n"
            f"[italic]Highlighting Java, Python, and microservices optimization tailored for {job.company}'s backend requirements.[/]\n\n"
            f"[bold cyan]Job Description Snippet[/]\n"
            f"{job.description[:1000]}..."
        )
