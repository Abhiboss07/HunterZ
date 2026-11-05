"""Configuration & Settings View for HunterZ TUI."""
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static
from hunterz.config import HunterZConfig


class ConfigView(Vertical):
    """View to review current candidate profile and scraping/filtering settings."""

    def __init__(self, config: HunterZConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        p = self.config.profile
        s = self.config.search
        a = self.config.apply
        b = self.config.boards

        content = (
            f"[bold cyan]Candidate Profile[/]\n"
            f"[bold white]Name:[/] {p.full_name} | [bold white]Role:[/] {p.current_role} | [bold white]Exp:[/] {p.years_experience} yr\n"
            f"[bold white]Email:[/] {p.email} | [bold white]Phone:[/] {p.phone}\n"
            f"[bold white]GitHub:[/] [blue]{p.github}[/] | [bold white]LinkedIn:[/] [blue]{p.linkedin}[/]\n\n"
            f"[bold cyan]Search & Role Filters[/]\n"
            f"[bold white]Max Post Age:[/] {s.max_age_hours} hours | [bold white]Ultra-Fresh Priority:[/] <{s.highlight_ultra_fresh_minutes} mins\n"
            f"[bold white]Target Roles:[/] [green]{', '.join(s.target_roles[:8])}...[/]\n"
            f"[bold white]Strict Exclusions:[/] [red]{', '.join(s.exclude_keywords)}[/]\n"
            f"[bold white]Target Locations:[/] {', '.join(s.locations[:6])}...\n\n"
            f"[bold cyan]Application Engine[/]\n"
            f"[bold white]Mode:[/] [bold green]{a.mode.upper()}[/] (Direct ATS Autopilot + Portal Review)\n"
            f"[bold white]Auto-Apply Threshold:[/] {a.min_match_score_to_auto_apply}% match score\n"
            f"[bold white]Dry-Run Mode:[/] {'[yellow]ENABLED[/]' if a.dry_run else '[green]DISABLED (Live Submissions)[/]'}\n\n"
            f"[bold cyan]Direct ATS Boards Monitored[/]\n"
            f"[bold white]Greenhouse ({len(b.greenhouse)} companies):[/] {', '.join(b.greenhouse[:10])}...\n"
            f"[bold white]Lever ({len(b.lever)} companies):[/] {', '.join(b.lever[:6])}...\n"
            f"[bold white]Ashby ({len(b.ashby)} companies):[/] {', '.join(b.ashby[:6])}...\n"
        )

        yield Static(content, id="config-static-text")
