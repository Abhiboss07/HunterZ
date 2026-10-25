"""Async SQLite database manager for HunterZ."""
import os
import aiosqlite
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from hunterz.db.models import JobModel, ApplicationModel, DirectOutreachModel

_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _PROJ_ROOT / "data" / "hunterz.db"


async def init_db(db_path: Path = DB_PATH):
    """Initialize SQLite database tables with high-performance WAL mode and indices."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                title TEXT,
                company TEXT,
                location TEXT,
                url TEXT,
                source TEXT,
                posted_at TIMESTAMP,
                discovered_at TIMESTAMP,
                description TEXT,
                match_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'NEW'
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs (posted_at DESC);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs (match_score DESC);")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                company TEXT,
                title TEXT,
                url TEXT,
                resume_pdf_path TEXT,
                resume_tex_path TEXT,
                applied_at TIMESTAMP,
                status TEXT DEFAULT 'SUBMITTED',
                submission_method TEXT DEFAULT 'DIRECT_REST',
                response_notes TEXT,
                rejection_reason TEXT,
                tailored_bio TEXT,
                provided_details TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs (id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_apps_applied_at ON applications (applied_at DESC);")

        # Table for Direct Recruiter Outreach Applications
        await db.execute("""
            CREATE TABLE IF NOT EXISTS direct_outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                company TEXT,
                title TEXT,
                recruiter_email TEXT,
                email_subject TEXT,
                email_body TEXT,
                resume_pdf_path TEXT,
                sent_at TIMESTAMP,
                status TEXT DEFAULT 'SENT',
                notes TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs (id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_outreach_sent_at ON direct_outreach (sent_at DESC);")

        # Graceful migration for existing databases: check and add columns if missing
        try:
            await db.execute("ALTER TABLE applications ADD COLUMN tailored_bio TEXT;")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE applications ADD COLUMN provided_details TEXT;")
        except Exception:
            pass

        await db.commit()


async def save_job(job: JobModel, db_path: Path = DB_PATH) -> Optional[int]:
    """Insert or update a job posting."""
    async with aiosqlite.connect(db_path) as db:
        try:
            cursor = await db.execute("""
                INSERT INTO jobs (external_id, title, company, location, url, source, posted_at, discovered_at, description, match_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    match_score = excluded.match_score,
                    status = CASE WHEN jobs.status = 'APPLIED' THEN 'APPLIED' ELSE excluded.status END
            """, (
                job.external_id,
                job.title,
                job.company,
                job.location,
                job.url,
                job.source,
                job.posted_at.isoformat(),
                job.discovered_at.isoformat(),
                job.description,
                job.match_score,
                job.status
            ))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error saving job: {e}")
            return None


async def get_jobs(status: Optional[str] = None, limit: int = 100, db_path: Path = DB_PATH) -> List[JobModel]:
    """Fetch jobs from the database, sorted newest first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if status:
            cursor = await db.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY posted_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM jobs ORDER BY posted_at DESC LIMIT ?",
                (limit,)
            )
        rows = await cursor.fetchall()
        jobs = []
        for r in rows:
            jobs.append(JobModel(
                id=r["id"],
                external_id=r["external_id"],
                title=r["title"],
                company=r["company"],
                location=r["location"],
                url=r["url"],
                source=r["source"],
                posted_at=datetime.fromisoformat(r["posted_at"]) if isinstance(r["posted_at"], str) else r["posted_at"],
                discovered_at=datetime.fromisoformat(r["discovered_at"]) if isinstance(r["discovered_at"], str) else r["discovered_at"],
                description=r["description"],
                match_score=r["match_score"],
                status=r["status"]
            ))
        return jobs


async def get_job_by_id(job_id: int, db_path: Path = DB_PATH) -> Optional[JobModel]:
    """Fetch a single job directly by primary key ID without limits or truncation."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        r = await cursor.fetchone()
        if not r:
            return None
        return JobModel(
            id=r["id"],
            external_id=r["external_id"],
            title=r["title"],
            company=r["company"],
            location=r["location"],
            url=r["url"],
            source=r["source"],
            posted_at=datetime.fromisoformat(r["posted_at"]) if isinstance(r["posted_at"], str) else r["posted_at"],
            discovered_at=datetime.fromisoformat(r["discovered_at"]) if isinstance(r["discovered_at"], str) else r["discovered_at"],
            description=r["description"],
            match_score=r["match_score"],
            status=r["status"]
        )


async def save_application(app: ApplicationModel, db_path: Path = DB_PATH) -> Optional[int]:
    """Record an application with tailored bio and provided candidate details."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("""
            INSERT INTO applications (
                job_id, company, title, url, resume_pdf_path, resume_tex_path,
                applied_at, status, submission_method, response_notes, rejection_reason,
                tailored_bio, provided_details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            app.job_id,
            app.company,
            app.title,
            app.url,
            app.resume_pdf_path,
            app.resume_tex_path,
            app.applied_at.isoformat(),
            app.status,
            app.submission_method,
            app.response_notes,
            app.rejection_reason,
            app.tailored_bio,
            app.provided_details
        ))
        await db.execute("UPDATE jobs SET status = 'APPLIED' WHERE id = ?", (app.job_id,))
        await db.commit()
        return cursor.lastrowid


async def get_applications(db_path: Path = DB_PATH) -> List[ApplicationModel]:
    """Fetch all recorded applications."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM applications ORDER BY applied_at DESC")
        rows = await cursor.fetchall()
        apps = []
        for r in rows:
            # Safe access for newer columns
            t_bio = r["tailored_bio"] if "tailored_bio" in r.keys() else None
            p_details = r["provided_details"] if "provided_details" in r.keys() else None
            apps.append(ApplicationModel(
                id=r["id"],
                job_id=r["job_id"],
                company=r["company"],
                title=r["title"],
                url=r["url"],
                resume_pdf_path=r["resume_pdf_path"],
                resume_tex_path=r["resume_tex_path"],
                applied_at=datetime.fromisoformat(r["applied_at"]) if isinstance(r["applied_at"], str) else r["applied_at"],
                status=r["status"],
                submission_method=r["submission_method"],
                response_notes=r["response_notes"],
                rejection_reason=r["rejection_reason"],
                tailored_bio=t_bio,
                provided_details=p_details
            ))
        return apps


async def save_outreach(outreach: DirectOutreachModel, db_path: Path = DB_PATH) -> Optional[int]:
    """Record a direct recruiter outreach application."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("""
            INSERT INTO direct_outreach (
                job_id, company, title, recruiter_email, email_subject, email_body,
                resume_pdf_path, sent_at, status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            outreach.job_id,
            outreach.company,
            outreach.title,
            outreach.recruiter_email,
            outreach.email_subject,
            outreach.email_body,
            outreach.resume_pdf_path,
            outreach.sent_at.isoformat(),
            outreach.status,
            outreach.notes
        ))
        await db.execute("UPDATE jobs SET status = 'OUTREACH' WHERE id = ?", (outreach.job_id,))
        await db.commit()
        return cursor.lastrowid


async def get_outreach_list(db_path: Path = DB_PATH) -> List[DirectOutreachModel]:
    """Fetch all direct recruiter outreach records."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM direct_outreach ORDER BY sent_at DESC")
        rows = await cursor.fetchall()
        outreach_list = []
        for r in rows:
            outreach_list.append(DirectOutreachModel(
                id=r["id"],
                job_id=r["job_id"],
                company=r["company"],
                title=r["title"],
                recruiter_email=r["recruiter_email"],
                email_subject=r["email_subject"],
                email_body=r["email_body"],
                resume_pdf_path=r["resume_pdf_path"],
                sent_at=datetime.fromisoformat(r["sent_at"]) if isinstance(r["sent_at"], str) else r["sent_at"],
                status=r["status"],
                notes=r["notes"]
            ))
        return outreach_list


async def update_application_status(app_id: int, status: str, rejection_reason: Optional[str] = None, notes: Optional[str] = None, db_path: Path = DB_PATH):
    """Update status (e.g. INTERVIEW, REJECTED) and notes."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            UPDATE applications
            SET status = ?, rejection_reason = COALESCE(?, rejection_reason), response_notes = COALESCE(?, response_notes)
            WHERE id = ?
        """, (status, rejection_reason, notes, app_id))
        await db.commit()


async def update_outreach_status(outreach_id: int, status: str, notes: Optional[str] = None, db_path: Path = DB_PATH):
    """Update direct outreach status (e.g. DRAFTED, SENT, BOUNCED)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            UPDATE direct_outreach
            SET status = ?, notes = COALESCE(?, notes)
            WHERE id = ?
        """, (status, notes, outreach_id))
        await db.commit()


async def delete_outreach(outreach_id: int, db_path: Path = DB_PATH):
    """Delete a direct outreach record."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM direct_outreach WHERE id = ?", (outreach_id,))
        await db.commit()

