"""Company Resumes and Tailored Profiles Inspector View for HunterZ TUI."""
import os
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Static, Button
from hunterz.config import HunterZConfig
from hunterz.db.models import ApplicationModel

OUTPUT_DIR = Path("output/resumes")


class ResumeInspectorView(Vertical):
    """View to inspect tailored resumes by company, review customized LaTeX & PDF paths."""

    def __init__(self, config: HunterZConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.resumes: List[Dict[str, Any]] = []
        self.selected_resume: Optional[Dict[str, Any]] = None

    def compose(self) -> ComposeResult:
        yield DataTable(id="resumes-table", cursor_type="row")
        with Vertical(id="resume-detail-pane"):
            yield Static("Select a company resume above to inspect its tailored contents.", id="resume-detail-text")
            with Horizontal(id="resume-actions"):
                yield Button("View Resume Details", id="btn-view-resume", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#resumes-table", DataTable)
        table.add_columns("Company", "Format", "Filename", "File Size", "Last Modified")
        self.refresh_resumes()

    def refresh_resumes(self) -> None:
        """Scan output/resumes for generated files."""
        table = self.query_one("#resumes-table", DataTable)
        table.clear()
        self.resumes = []

        if not OUTPUT_DIR.exists():
            return

        files = sorted(OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True)

        for f in files:
            name_parts = f.stem.split("_")
            company = name_parts[1] if len(name_parts) > 1 else "Master"
            fmt = f.suffix.upper().replace(".", "")
            size_kb = f"{f.stat().st_size / 1024:.1f} KB"
            import datetime
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

            entry = {
                "company": company,
                "format": fmt,
                "path": str(f.resolve()),
                "filename": f.name,
                "size": size_kb,
                "mtime": mtime
            }
            self.resumes.append(entry)

            fmt_styled = f"[bold green]{fmt}[/]" if fmt == "PDF" else f"[bold cyan]{fmt}[/]"
            table.add_row(
                f"[bold white]{company}[/]",
                fmt_styled,
                f.name,
                size_kb,
                mtime,
                key=str(f.name)
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        matched = [r for r in self.resumes if r["filename"] == str(row_key)]
        if matched:
            self.selected_resume = matched[0]
            r = self.selected_resume
            detail_widget = self.query_one("#resume-detail-text", Static)

            preview_snippet = ""
            if r["format"] in ["TEX", "HTML"] and Path(r["path"]).exists():
                try:
                    with open(r["path"], "r", encoding="utf-8") as f:
                        preview_snippet = f"\n\n[bold]Content Preview:[/]\n" + f.read()[:600] + "..."
                except Exception:
                    pass

            detail_widget.update(
                f"[bold cyan]Company:[/] [bold white]{r['company']}[/] | [bold cyan]Format:[/] {r['format']}\n"
                f"[bold white]File Path:[/] [green]{r['path']}[/] ({r['size']})\n"
                f"[dim]Generated:[/] {r['mtime']}"
                f"{preview_snippet}"
            )
