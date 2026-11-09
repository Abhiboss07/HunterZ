"""Typer CLI interface for HunterZ."""
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from hunterz.config import load_config
from hunterz.db.session import init_db, get_jobs, get_job_by_id, get_applications, save_job, save_application
from hunterz.scrapers import scrape_all_sources
from hunterz.matcher.filter import is_job_eligible
from hunterz.matcher.scorer import compute_match_score
from hunterz.resume.tailor import ResumeTailor
from hunterz.applier.direct_ats import DirectATSApplier
from hunterz.applier.browser_applier import BrowserApplier
from hunterz.applier.dispatcher import ApplicationDispatcher

app = typer.Typer(
    name="hunterz",
    help="⚡ HunterZ: Autonomous Job Hunter, Real-Time Scraper & AI Resume Tailor CLI",
    add_completion=False
)
console = Console()


@app.command()
def web(
    port: int = typer.Option(8096, "--port", "-p", help="Port to run the Web CRM on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open browser")
):
    """Launch the modern Web-based CRM Dashboard on http://127.0.0.1:8096."""
    import webbrowser
    import uvicorn
    import threading

    url = f"http://{host}:{port}/"
    clean_url = url.rstrip("/")
    console.print(Panel(
        f"[bold green]✔ HunterZ Web CRM is starting![/]\n\n"
        f"[bold white]Dashboard URL:[/] [link={clean_url}][bold yellow underline]{clean_url}[/][/link]\n"
        f"[dim]Features: 48h Hard Cutoff • Sort by Latest • Direct Outreach • 166 Boards Directory[/]",
        title="⚡ HunterZ Web CRM",
        border_style="yellow"
    ))

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(clean_url)).start()

    uvicorn.run("hunterz.web.app:app", host=host, port=port, log_level="info")


@app.command()
def tui():
    """Launch the interactive Terminal User Interface (TUI) Dashboard."""
    from hunterz.ui.app import HunterZApp
    tui_app = HunterZApp()
    tui_app.run()


@app.command()
def scan(
    max_age: int = typer.Option(24, "--max-age", "-a", help="Max job age in hours"),
    min_score: int = typer.Option(60, "--min-score", "-m", help="Minimum match score to display")
):
    """Scan all sources (Greenhouse, Lever, Ashby, LinkedIn, Startup Portals) for fresh openings."""
    config = load_config()
    config.search.max_age_hours = max_age

    async def _run_scan():
        await init_db()
        console.print(Panel(
            f"[bold cyan]Scanning job sources (<{max_age}h old) for roles:[/] {', '.join(config.search.target_roles[:4])}...",
            title="🔍 HunterZ Scanner",
            border_style="cyan"
        ))

        with console.status("[bold green]Querying ATS APIs & Job Feeds..."):
            raw_jobs = await scrape_all_sources(config)

        table = Table(title=f"Fresh Job Matches (<{max_age}h)", show_lines=True)
        table.add_column("Score", style="bold green", width=8)
        table.add_column("Company", style="bold white", width=18)
        table.add_column("Title", style="cyan", width=30)
        table.add_column("Location", width=16)
        table.add_column("Source", style="dim", width=12)

        matched_count = 0
        for job in raw_jobs:
            eligible, reason = is_job_eligible(job, config)
            if not eligible:
                continue

            score, matched_skills, _ = compute_match_score(job, config.profile)
            job.match_score = score
            job.status = "MATCHED" if score >= 60 else "NEW"
            await save_job(job)

            if score >= min_score:
                matched_count += 1
                score_str = f"[bold green]{score}%[/]" if score >= 75 else f"[yellow]{score}%[/]"
                table.add_row(
                    score_str,
                    job.company,
                    job.title,
                    job.location[:16],
                    f"[{job.source}]"
                )

        console.print(table)
        console.print(f"[bold green]✔ Scan Complete:[/] Found [bold]{matched_count}[/] relevant SDE positions above {min_score}% match score.\n")

    asyncio.run(_run_scan())


@app.command()
def tracker(
    watch: bool = typer.Option(False, "--watch", "-w", help="Monitor application pipeline live in real-time")
):
    """Print the real-time status table of all submitted applications, screenshots, and recruiter contacts."""
    import time
    from hunterz.tracker.recruiter_finder import RecruiterFinder

    async def _render_tracker_table():
        await init_db()
        apps = await get_applications()

        if not apps:
            console.print("[yellow]No applications recorded yet. Run `hunterz tui` or `hunterz scan` to apply.[/]")
            return

        table = Table(title="📬 HunterZ Live Real-Time Application Pipeline", show_lines=True)
        table.add_column("ID", width=4)
        table.add_column("Applied Date", width=16)
        table.add_column("Company", style="bold white", width=16)
        table.add_column("Role", style="cyan", width=26)
        table.add_column("Status", width=14)
        table.add_column("Visual Audit (Screenshots)", width=26)
        table.add_column("Discovered Recruiter Contacts", width=34)

        finder = RecruiterFinder()
        for a in apps:
            if a.status == "INTERVIEW":
                status_str = "[bold green]🎉 INTERVIEW[/]"
            elif a.status == "OFFER":
                status_str = "[bold magenta]🏆 OFFER[/]"
            elif a.status == "REJECTED":
                status_str = "[bold red]❌ REJECTED[/]"
            else:
                status_str = "[bold cyan]📤 SUBMITTED[/]"

            # Check screenshots on disk
            import re
            safe_c = re.sub(r'[^a-zA-Z0-9_-]', '_', a.company.lower())
            ss_dir = Path("output/screenshots")
            found_ss = []
            if (ss_dir / f"{safe_c}_step1_begin.png").exists():
                found_ss.append("Step 1 (Begin)")
            if (ss_dir / f"{safe_c}_step2_filled.png").exists():
                found_ss.append("Step 2 (Filled)")
            if (ss_dir / f"{safe_c}_step3_submitted.png").exists():
                found_ss.append("Step 3 (Submit)")

            ss_str = "[green]✔ " + ", ".join(found_ss) + "[/]" if found_ss else "[dim]None recorded[/]"

            # Recruiter contacts
            recruiters = await finder.find_recruiters_for_company(a.company)
            if recruiters:
                top_recs = recruiters[:2]
                rec_str = "\n".join([f"• {r.name}: [underline green]{r.email}[/]" for r in top_recs])
            else:
                rec_str = f"[dim]Search: linkedin.com/search?q={a.company}[/]"

            table.add_row(
                str(a.id),
                a.applied_at.strftime("%Y-%m-%d %H:%M"),
                a.company,
                a.title,
                status_str,
                ss_str,
                rec_str
            )

        console.clear()
        console.print(table)
        console.print(f"[dim]Live sync timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')} | Total Applications: {len(apps)}[/]")

    async def _run_tracker_loop():
        if watch:
            console.print("[cyan]Starting real-time live tracker loop (Press Ctrl+C to exit)...[/]")
            try:
                while True:
                    await _render_tracker_table()
                    await asyncio.sleep(3)
            except KeyboardInterrupt:
                console.print("\n[yellow]Live tracker stopped.[/]")
        else:
            await _render_tracker_table()

    asyncio.run(_run_tracker_loop())


@app.command()
def recruiters(
    company: str = typer.Argument(..., help="Name of company to find recruiter emails for")
):
    """Find recruiters, talent partners, and company inboxes with confidence scores."""
    from hunterz.tracker.recruiter_finder import RecruiterFinder

    async def _run_find():
        finder = RecruiterFinder()
        contacts = await finder.find_recruiters_for_company(company)

        table = Table(title=f"🎯 Recruiter & Talent Contacts: {company}", show_lines=True)
        table.add_column("Name", style="bold white", width=22)
        table.add_column("Title", style="cyan", width=34)
        table.add_column("Email Address", style="bold green", width=28)
        table.add_column("Confidence", width=12)
        table.add_column("Source", width=18)

        for c in contacts:
            table.add_row(
                c.name,
                c.title,
                c.email,
                f"{c.confidence_score}%",
                c.source
            )

        console.print(table)

    asyncio.run(_run_find())


@app.command()
def apply(
    job_id: int = typer.Argument(..., help="ID of the job from database to apply to"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Simulate submission without sending real data")
):
    """Tailor resume, capture visual audit screenshots, and apply to a job by ID."""
    from hunterz.tracker.recruiter_finder import RecruiterFinder

    async def _run_apply():
        await init_db()
        job = await get_job_by_id(job_id)

        if not job:
            console.print(f"[red]Error:[/] Job with ID {job_id} not found.")
            return
        config = load_config()
        config.apply.dry_run = dry_run

        tailor_engine = ResumeTailor(config.profile)
        dispatcher = ApplicationDispatcher(config)

        console.print(f"[cyan]1. Tailoring resume for:[/] [bold]{job.title}[/] at [bold]{job.company}[/]...")
        tex_path, pdf_path, ctx = tailor_engine.tailor_with_context(job)

        mode_str = "[yellow](DRY-RUN SIMULATION)[/]" if dry_run else "[red](LIVE SUBMISSION)[/]"
        console.print(f"[cyan]2. Submitting application {mode_str}...[/]")

        success, status, method, msg, audit = await dispatcher.apply_job(
            job=job,
            resume_pdf=pdf_path,
            resume_tex=tex_path,
            dry_run=dry_run,
            log=lambda m: console.print(f"  [dim]{m}[/]")
        )
        canonical_url = audit.get("canonical_url", job.url)


        # Discovered recruiters for immediate outreach
        finder = RecruiterFinder()
        recs = await finder.find_recruiters_for_company(job.company)

        if success:
            import json
            from hunterz.db.models import ApplicationModel
            details_dict = {
                "full_name": config.profile.full_name,
                "email": config.profile.email,
                "phone": config.profile.phone,
                "location": config.profile.location,
                "linkedin": config.profile.linkedin,
                "summary": ctx.get("summary", ""),
                "audit_screenshots": audit.get("screenshots", {}),
                "canonical_url": audit.get("canonical_url", canonical_url)
            }
            app_record = ApplicationModel(
                job_id=job.id or 0,
                company=job.company,
                title=job.title,
                url=audit.get("canonical_url", canonical_url),
                resume_pdf_path=str(pdf_path),
                resume_tex_path=str(tex_path),
                status="SUBMITTED",
                submission_method=method,
                response_notes=msg,
                tailored_bio=ctx.get("tailored_bio", ""),
                provided_details=json.dumps(details_dict)
            )
            await save_application(app_record)

            rec_info = "\n".join([f"  • [bold white]{r.name}[/] ({r.title}): [underline green]{r.email}[/]" for r in recs[:3]])
            ss_info = "\n".join([f"  • [bold white]{k}:[/] [blue]{v}[/]" for k, v in audit.get("screenshots", {}).items()]) or "  • Visual audit recorded on disk"

            console.print(Panel(
                f"[bold green]✔ Application Processed Successfully![/]\n\n"
                f"[bold white]Company:[/] {job.company}\n"
                f"[bold white]Role:[/] {job.title}\n"
                f"[bold white]Canonical Portal:[/] [blue]{audit.get('canonical_url', canonical_url)}[/]\n"
                f"[bold white]Submission Method:[/] {method}\n"
                f"[bold white]Tailored Resume:[/] [green]{pdf_path}[/]\n"
                f"[bold white]Status Message:[/] {msg}\n\n"
                f"[bold cyan]📸 Visual Audit Screenshots:[/]\n{ss_info}\n\n"
                f"[bold cyan]🎯 Recruiter & Talent Contacts Found:[/]\n{rec_info}",
                title="📬 Application Submitted with Visual Verification",
                border_style="green"
            ))
        else:
            console.print(f"[bold red]❌ Application Failed:[/] {msg}")

    asyncio.run(_run_apply())


@app.command()
def tailor(
    job_id: int = typer.Argument(..., help="ID of the job from database to tailor resume for")
):
    """Generate a tailored LaTeX and PDF resume specifically for a job ID."""
    async def _run_tailor():
        await init_db()
        job = await get_job_by_id(job_id)

        if not job:
            console.print(f"[red]Error:[/] Job with ID {job_id} not found.")
            return
        config = load_config()
        tailor_engine = ResumeTailor(config.profile)

        console.print(f"[cyan]Tailoring resume for:[/] [bold]{job.title}[/] at [bold]{job.company}[/]...")
        tex_path, pdf_path = tailor_engine.tailor(job)

        console.print(Panel(
            f"[bold green]✔ Tailoring Complete![/]\n\n"
            f"[bold white]LaTeX Source:[/] [blue]{tex_path}[/]\n"
            f"[bold white]Compiled PDF:[/] [green]{pdf_path}[/]",
            title="📄 Tailored Resume Generated",
            border_style="green"
        ))

    asyncio.run(_run_tailor())


@app.command()
def profile():
    """Display your verified profile details, skills, and configuration stored locally."""
    config = load_config()
    p = config.profile
    e = p.education

    console.print(Panel(
        f"[bold cyan]Full Name:[/] [bold white]{p.full_name}[/]\n"
        f"[bold cyan]Date of Birth:[/] [bold white]{p.dob}[/] ([green]{p.age} years old[/])\n"
        f"[bold cyan]Location / Nationality:[/] {p.location} ({p.nationality})\n"
        f"[bold cyan]Residential Address:[/] [bold white]{getattr(p, 'address_line1', 'Jaunpur')}, {getattr(p, 'city', 'Jaunpur')}, {getattr(p, 'state', 'Uttar Pradesh')} - {getattr(p, 'postal_code', '222001')}, {getattr(p, 'country', 'India')}[/]\n"
        f"[bold cyan]Work Authorization:[/] [green]{p.work_authorization}[/]\n"
        f"[bold cyan]Notice Period:[/] {p.notice_period} | [bold cyan]Relocation:[/] {'Yes' if p.willing_to_relocate else 'No'}\n\n"
        f"[bold cyan]Contact & Links:[/]\n"
        f"  • [bold white]Email:[/] {p.email}\n"
        f"  • [bold white]Phone:[/] {p.phone}\n"
        f"  • [bold white]LinkedIn:[/] [blue]{p.linkedin}[/]\n"
        f"  • [bold white]GitHub:[/] [blue]{p.github}[/]\n"
        f"  • [bold white]Portfolio:[/] [blue]{p.portfolio}[/]\n\n"
        f"[bold cyan]Telegram Notifications:[/]\n"
        f"  • [bold white]Bot Token:[/] {'Configured [green]✔[/]' if p.telegram_bot_token else '[yellow]Not set[/]'}\n"
        f"  • [bold white]Chat ID:[/] {p.telegram_chat_id or '[yellow]Not set[/]'}\n\n"
        f"[bold cyan]Education:[/]\n"
        f"  • [bold white]{e.degree}[/] at [bold white]{e.university}[/] (Graduation: {e.graduation_year})\n\n"
        f"[bold cyan]Current Experience:[/]\n"
        f"  • [bold white]{p.current_role}[/] ({p.years_experience} year experience)",
        title="👤 Candidate Profile (Stored Locally & Securely)",
        border_style="cyan"
    ))


@app.command()
def resumes():
    """List all generated company-tailored resumes in output/resumes/."""
    from pathlib import Path
    import os
    import datetime

    out_dir = Path("output/resumes")
    if not out_dir.exists():
        console.print("[yellow]No resumes directory found.[/]")
        return

    files = sorted(out_dir.glob("*.*"), key=os.path.getmtime, reverse=True)
    if not files:
        console.print("[yellow]No tailored resumes generated yet. Run `hunterz tailor <id>` or use the TUI.[/]")
        return

    table = Table(title="📄 Generated Company-Tailored Resumes", show_lines=True)
    table.add_column("Company", style="bold white", width=22)
    table.add_column("Format", width=8)
    table.add_column("Filename", style="cyan", width=34)
    table.add_column("Size", width=10)
    table.add_column("Last Modified", width=16)

    for f in files:
        name_parts = f.stem.split("_")
        company = name_parts[1] if len(name_parts) > 1 else "Master"
        fmt = f.suffix.upper().replace(".", "")
        size_kb = f"{f.stat().st_size / 1024:.1f} KB"
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        fmt_styled = f"[bold green]{fmt}[/]" if fmt == "PDF" else f"[bold cyan]{fmt}[/]"
        table.add_row(
            company,
            fmt_styled,
            f.name,
            size_kb,
            mtime
        )

    console.print(table)


@app.command()
def db():
    """Inspect local SQLite database (data/hunterz.db) tables, counts, and statuses."""
    async def _inspect_db():
        await init_db()
        jobs = await get_jobs(limit=1000)
        apps = await get_applications()

        console.print(Panel(
            f"[bold white]Database Location:[/] data/hunterz.db\n"
            f"[bold white]Total Discovered Jobs:[/] [bold cyan]{len(jobs)}[/]\n"
            f"[bold white]High-Match Jobs (≥75%):[/] [bold green]{len([j for j in jobs if j.match_score >= 75])}[/]\n"
            f"[bold white]Total Applications Submitted:[/] [bold yellow]{len(apps)}[/]\n"
            f"[bold white]Active Interviews:[/] [bold green]{len([a for a in apps if a.status == 'INTERVIEW'])}[/]\n"
            f"[bold white]Active Rejections Analyzed:[/] [bold red]{len([a for a in apps if a.status == 'REJECTED'])}[/]",
            title="🗄️ Database Inspection Summary",
            border_style="cyan"
        ))

        # Sources breakdown
        sources = {}
        for j in jobs:
            sources[j.source] = sources.get(j.source, 0) + 1

        source_table = Table(title="Jobs by Source Feed", show_lines=False)
        source_table.add_column("Source", style="cyan")
        source_table.add_column("Job Count", style="bold white")
        for s, count in sources.items():
            source_table.add_row(s, str(count))

        console.print(source_table)

    asyncio.run(_inspect_db())


@app.command()
def auto(
    once: bool = typer.Option(True, "--once/--loop", help="Run a single cycle or continuous autonomous daemon"),
    interval: int = typer.Option(60, "--interval", "-i", help="Interval in minutes between cycles when running in loop mode"),
    schedule: Optional[str] = typer.Option(None, "--schedule", "-s", help="Comma-separated scheduled times (e.g. '09:00,14:00,19:00')"),
    limit: int = typer.Option(5, "--limit", "-l", help="Max auto-applications per cycle"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate applications without sending live form data"),
    no_push: bool = typer.Option(False, "--no-push", help="Skip git commit and push to GitHub")
):
    """Run autonomous end-to-end pipeline: Scrape -> Match -> Tailor -> Auto-Apply -> Outreach -> Telegram Alert -> Git Sync."""
    import time
    from hunterz.automation.orchestrator import AutonomousOrchestrator

    async def _run():
        orchestrator = AutonomousOrchestrator()

        if schedule:
            target_times = [t.strip() for t in schedule.split(",") if t.strip()]
            console.print(Panel(
                f"[bold cyan]Autonomous HunterZ Daemon Scheduled[/]\n"
                f"[bold white]Target Times:[/] {', '.join(target_times)}\n"
                f"[bold white]Max Auto-Applies per Run:[/] {limit}\n"
                f"[bold white]Mode:[/] {'[yellow]Simulation / Dry-Run[/]' if dry_run else '[red]Live Submission[/]'}\n"
                f"[bold white]GitHub Cloud Sync:[/] {'Disabled' if no_push else 'Enabled (git push origin main)'}\n"
                f"[dim]Running background monitor... Press Ctrl+C to stop.[/]",
                title="⏰ Scheduled Automation Mode",
                border_style="cyan"
            ))
            ran_today = set()
            try:
                while True:
                    now_str = time.strftime("%H:%M")
                    today_str = time.strftime("%Y-%m-%d")
                    for t in target_times:
                        key = f"{today_str}_{t}"
                        if now_str == t and key not in ran_today:
                            console.print(f"[bold green]🔔 Scheduled trigger fired for {t}![/]")
                            await orchestrator.run_cycle(max_auto_applies=limit, sync_github=not no_push, dry_run=dry_run)
                            ran_today.add(key)
                    await asyncio.sleep(30)
            except KeyboardInterrupt:
                console.print("\n[yellow]Autonomous scheduler stopped.[/]")
        elif once:
            mode_lbl = " [yellow](Simulation / Dry-Run)[/]" if dry_run else " [red](Live Submission)[/]"
            console.print(f"[cyan]Executing immediate autonomous pipeline cycle{mode_lbl}...[/]")
            res = await orchestrator.run_cycle(max_auto_applies=limit, sync_github=not no_push, dry_run=dry_run)
            console.print(Panel(
                f"[bold green]✔ Autonomous Run Completed![/]\n\n"
                f"[bold white]Roles Scanned:[/] {res['scanned']}\n"
                f"[bold white]Ultra-Fresh Roles (<1h):[/] {res['fresh_count']}\n"
                f"[bold white]High-Match Qualified Roles:[/] {res['matched']}\n"
                f"[bold white]Auto-Applications Processed:[/] [bold green]{res['applied']}[/]\n"
                f"[bold white]Recruiter Outreaches Prepared:[/] [bold cyan]{res['outreach_sent']}[/]\n"
                f"[bold white]Companies Applied:[/] {', '.join(res['applied_companies']) if res['applied_companies'] else 'None'}\n"
                f"[bold white]Live Dashboard Status:[/] [blue]https://abhiboss07.github.io/HunterZ/[/]",
                title="⚡ Pipeline Summary",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold cyan]Autonomous HunterZ Continuous Daemon Active[/]\n"
                f"[bold white]Cadence:[/] Every {interval} minutes\n"
                f"[bold white]Max Applies per Interval:[/] {limit}\n"
                f"[bold white]Mode:[/] {'[yellow]Simulation / Dry-Run[/]' if dry_run else '[red]Live Submission[/]'}\n"
                f"[bold white]Cloud Sync:[/] {'Disabled' if no_push else 'Enabled'}\n"
                f"[dim]Monitoring jobs continuously... Press Ctrl+C to stop.[/]",
                title="🔁 Continuous Interval Mode",
                border_style="cyan"
            ))
            try:
                while True:
                    await orchestrator.run_cycle(max_auto_applies=limit, sync_github=not no_push, dry_run=dry_run)
                    console.print(f"[dim]Sleeping for {interval} minutes until next cycle...[/]")
                    await asyncio.sleep(interval * 60)
            except KeyboardInterrupt:
                console.print("\n[yellow]Daemon stopped.[/]")

    asyncio.run(_run())


@app.command()
def fresh(
    minutes: int = typer.Option(15, "--minutes", "-m", help="Age limit in minutes for ultra-fresh roles (e.g. 1, 5, 15)")
):
    """Scan for ultra-fresh roles posted ~1 minute to 15 minutes ago with exact timestamps."""
    from hunterz.scrapers.ultra_fresh import UltraFreshScanner

    async def _run_fresh():
        config = load_config()
        scanner = UltraFreshScanner(config)
        console.print(f"[cyan]⚡ Scanning ATS boards for ultra-fresh roles posted within last {minutes} minutes...[/]")
        results = await scanner.scan_for_ultra_fresh(max_minutes=minutes)

        if not results:
            console.print(f"[yellow]No openings discovered posted within the last {minutes}m. Run `hunterz scan` for all 48h roles.[/]")
            return

        table = Table(title=f"⚡ Ultra-Fresh Roles (<{minutes}m recency)", show_lines=True)
        table.add_column("Recency", style="bold red", width=18)
        table.add_column("Company", style="bold white", width=18)
        table.add_column("Position", style="cyan", width=30)
        table.add_column("Location", width=16)
        table.add_column("Match", width=8)
        table.add_column("Source", width=12)

        for job, tag in results:
            table.add_row(
                tag,
                job.company,
                job.title,
                job.location[:16],
                f"{job.match_score}%",
                job.source.upper()
            )

        console.print(table)

    asyncio.run(_run_fresh())


@app.command()
def health():
    """Inspect self-healing engine diagnostics, error reflections, and auto-learned heuristics."""
    from hunterz.healing.self_improver import SelfHealingEngine

    engine = SelfHealingEngine()
    metrics = engine.get_healing_metrics()

    console.print(Panel(
        f"[bold white]Total Anomaly Incidents Logged:[/] [bold cyan]{metrics['total_incidents_recorded']}[/]\n"
        f"[bold white]Auto-Adapted & Self-Healed Count:[/] [bold green]{metrics['auto_adapted_count']}[/]\n"
        f"[bold white]Healing Success Rate:[/] [bold green]{metrics['healing_success_rate']}[/]\n\n"
        f"[bold white]Active Runtime Heuristics:[/]\n"
        f"  • [cyan]Selector Wait Timeout:[/] {engine.active_heuristics.get('selector_wait_timeout_ms')}ms\n"
        f"  • [cyan]Retry Backoff Multiplier:[/] {engine.active_heuristics.get('retry_backoff_multiplier')}x\n"
        f"  • [cyan]Known ATS Canonical Aliases:[/] {len(engine.active_heuristics.get('known_ats_aliases', {}))} mapped\n"
        f"  • [cyan]Adaptive Form Field Synonyms:[/] {len(engine.active_heuristics.get('form_field_synonyms', {}))} categories\n\n"
        f"[bold white]Recent Auto-Fixes Applied:[/]\n" +
        ("\n".join([f"  • [green]✔[/] {f}" for f in metrics['recent_fixes']]) if metrics['recent_fixes'] else "  • [dim]System running with zero unrecovered errors.[/]"),
        title="🛡️ HunterZ Self-Healing Diagnostics",
        border_style="green"
    ))


def main():
    """Default entry point. If no args provided, launches TUI."""
    import sys
    if len(sys.argv) == 1:
        from hunterz.ui.app import HunterZApp
        tui_app = HunterZApp()
        tui_app.run()
    else:
        app()


if __name__ == "__main__":
    main()
