"""Interactive Profile & CRM Settings Editor View for HunterZ TUI."""
import yaml
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Input, Button, Label, DataTable
from hunterz.config import HunterZConfig


class ProfileEditorView(ScrollableContainer):
    """CRM view allowing Abhishek to inspect and edit his profile details and monitored companies."""

    def __init__(self, config: HunterZConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        p = self.config.profile
        s = self.config.search
        b = self.config.boards

        yield Static("[bold cyan]═══════ 👤 Candidate CRM Profile & Details Editor ═══════[/]", classes="stat-label")
        yield Static("[dim]Modify any field below and click 'Save Changes' to update your local config.yaml instantly.[/]\n")

        with Horizontal(classes="profile-input-row"):
            yield Label("Full Name:", classes="profile-input-label")
            yield Input(value=p.full_name, id="input-name", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Date of Birth:", classes="profile-input-label")
            yield Input(value=p.dob, id="input-dob", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Age:", classes="profile-input-label")
            yield Input(value=str(p.age), id="input-age", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Email:", classes="profile-input-label")
            yield Input(value=p.email, id="input-email", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Phone:", classes="profile-input-label")
            yield Input(value=p.phone, id="input-phone", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Location / Country:", classes="profile-input-label")
            yield Input(value=p.location, id="input-location", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Notice Period:", classes="profile-input-label")
            yield Input(value=p.notice_period, id="input-notice", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("LinkedIn URL:", classes="profile-input-label")
            yield Input(value=p.linkedin, id="input-linkedin", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("GitHub URL:", classes="profile-input-label")
            yield Input(value=p.github, id="input-github", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Portfolio URL:", classes="profile-input-label")
            yield Input(value=p.portfolio, id="input-portfolio", classes="profile-input-field")

        with Horizontal(classes="profile-input-row"):
            yield Label("Target Roles:", classes="profile-input-label")
            yield Input(value=", ".join(s.target_roles[:8]), id="input-roles", classes="profile-input-field")

        with Horizontal(id="profile-action-bar"):
            yield Button("💾 Save Profile Changes to config.yaml", id="btn-save-profile", variant="success")

        yield Static("\n[bold cyan]═══════ 🏢 Monitored Company Directory (120+ Boards) ═══════[/]", classes="stat-label")
        yield DataTable(id="companies-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#companies-table", DataTable)
        table.add_columns("Platform", "Company Handle / Name", "Target Portal Status")

        # Greenhouse
        for c in self.config.boards.greenhouse:
            table.add_row("[green]Greenhouse API[/]", c.capitalize(), "[bold green]ACTIVE (Auto-Apply REST)[/]")
        # Lever
        for c in self.config.boards.lever:
            table.add_row("[cyan]Lever API[/]", c.capitalize(), "[bold green]ACTIVE (Auto-Apply REST)[/]")
        # Ashby
        for c in self.config.boards.ashby:
            table.add_row("[yellow]Ashby API[/]", c.capitalize(), "[bold green]ACTIVE (Auto-Apply REST)[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save-profile":
            self.save_profile()

    def save_profile(self) -> None:
        """Update in-memory profile and write to config.yaml."""
        p = self.config.profile
        p.full_name = self.query_one("#input-name", Input).value.strip()
        p.dob = self.query_one("#input-dob", Input).value.strip()
        try:
            p.age = int(self.query_one("#input-age", Input).value.strip())
        except ValueError:
            pass
        p.email = self.query_one("#input-email", Input).value.strip()
        p.phone = self.query_one("#input-phone", Input).value.strip()
        p.location = self.query_one("#input-location", Input).value.strip()
        p.notice_period = self.query_one("#input-notice", Input).value.strip()
        p.linkedin = self.query_one("#input-linkedin", Input).value.strip()
        p.github = self.query_one("#input-github", Input).value.strip()
        p.portfolio = self.query_one("#input-portfolio", Input).value.strip()

        # Update config.yaml file on disk
        cfg_path = Path("config.yaml")
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            data["profile"]["full_name"] = p.full_name
            data["profile"]["dob"] = p.dob
            data["profile"]["age"] = p.age
            data["profile"]["email"] = p.email
            data["profile"]["phone"] = p.phone
            data["profile"]["location"] = p.location
            data["profile"]["notice_period"] = p.notice_period
            data["profile"]["linkedin"] = p.linkedin
            data["profile"]["github"] = p.github
            data["profile"]["portfolio"] = p.portfolio

            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, sort_keys=False)

        self.app.notify("Profile changes successfully saved to config.yaml!", severity="information")
