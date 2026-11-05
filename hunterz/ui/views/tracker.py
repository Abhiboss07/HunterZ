"""Applications Tracker View for HunterZ TUI."""
from typing import List, Optional
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Static, Button
from hunterz.db.models import ApplicationModel


class TrackerView(Vertical):
    """View to track applications, review statuses, and inspect rejection reasons."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.applications: List[ApplicationModel] = []
        self.selected_app: Optional[ApplicationModel] = None

    def compose(self) -> ComposeResult:
        yield DataTable(id="apps-table", cursor_type="row")
        with Vertical(id="app-detail-pane"):
            yield Static("Select an application above to inspect details and feedback.", id="app-detail-text")
            with Horizontal(id="tracker-actions"):
                yield Button("Mark Interview", id="btn-status-interview", variant="success")
                yield Button("Mark Rejected", id="btn-status-rejected", variant="error")
                yield Button("Mark Offer", id="btn-status-offer", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#apps-table", DataTable)
        table.add_columns("Applied Date", "Company", "Role", "Submission", "Status", "Notes / Rejection Reason")

    def update_applications(self, apps: List[ApplicationModel]) -> None:
        """Populate applications table."""
        self.applications = apps
        table = self.query_one("#apps-table", DataTable)
        table.clear()

        for a in apps:
            date_str = a.applied_at.strftime("%Y-%m-%d %H:%M")

            if a.status == "INTERVIEW":
                status_str = "[bold green]🎉 INTERVIEW[/]"
            elif a.status == "OFFER":
                status_str = "[bold magenta]🏆 OFFER[/]"
            elif a.status == "REJECTED":
                status_str = "[bold red]❌ REJECTED[/]"
            else:
                status_str = "[bold cyan]📤 SUBMITTED[/]"

            reason_str = a.rejection_reason or a.response_notes or "[dim]Under Review[/]"

            table.add_row(
                date_str,
                f"[bold white]{a.company}[/]",
                a.title,
                f"[{a.submission_method}]",
                status_str,
                reason_str,
                key=str(a.id)
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        matched = [a for a in self.applications if str(a.id) == str(row_key)]
        if matched:
            self.selected_app = matched[0]
            app = self.selected_app
            detail_widget = self.query_one("#app-detail-text", Static)
            detail_widget.update(
                f"[bold cyan]{app.title}[/] at [bold white]{app.company}[/]\n"
                f"[dim]Applied:[/] {app.applied_at.strftime('%Y-%m-%d %H:%M')} via {app.submission_method}\n"
                f"[dim]Resume PDF:[/] [green]{app.resume_pdf_path}[/]\n"
                f"[bold]Status:[/] {app.status}\n"
                f"[bold]Rejection Analysis / Feedback:[/] [yellow]{app.rejection_reason or 'No rejection recorded.'}[/]"
            )
