"""Direct REST API application submitter for Greenhouse, Lever, and Ashby."""
import httpx
from pathlib import Path
from typing import Tuple, Dict, Any
from hunterz.db.models import JobModel, ApplicationModel
from hunterz.config import HunterZConfig


class DirectATSApplier:
    """Submits applications directly through ATS REST APIs with multipart/form-data."""

    def __init__(self, config: HunterZConfig):
        self.config = config

    async def apply(self, job: JobModel, resume_pdf: Path, resume_tex: Path) -> Tuple[bool, str]:
        """
        Submits application for a given job.
        Returns: (success: bool, message: str)
        """
        if self.config.apply.dry_run:
            return True, f"[DRY-RUN] Simulated submission to {job.company} ({job.source}) with {resume_pdf.name}"

        profile = self.config.profile

        # Validate resume PDF exists
        if not resume_pdf.exists() or resume_pdf.stat().st_size == 0:
            return False, f"Resume PDF not found or empty: {resume_pdf}"

        # 1. Greenhouse Direct Form API
        if job.source == "greenhouse":
            return await self._apply_greenhouse(job, resume_pdf)

        # 2. Lever Direct Form API
        elif job.source == "lever":
            return await self._apply_lever(job, resume_pdf)

        # 3. Ashby Direct Form API
        elif job.source == "ashby":
            return await self._apply_ashby(job, resume_pdf)

        else:
            return False, f"Direct API submission not supported for source '{job.source}'. Use Co-pilot mode."

    async def _apply_greenhouse(self, job: JobModel, resume_pdf: Path) -> Tuple[bool, str]:
        # Extract board and job ID from external_id: greenhouse_{board}_{id}
        parts = job.external_id.split("_")
        if len(parts) < 3:
            return False, "Invalid Greenhouse external ID format"

        board = parts[1]
        job_id = parts[2]
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}/applications"

        first_name, *last_names = self.config.profile.full_name.split()
        last_name = " ".join(last_names) if last_names else first_name

        data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": self.config.profile.email,
            "phone": self.config.profile.phone,
            "linkedin_profile": self.config.profile.linkedin,
            "website": self.config.profile.portfolio,
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                with open(resume_pdf, "rb") as f:
                    files = {"resume": (resume_pdf.name, f.read(), "application/pdf")}
                    resp = await client.post(api_url, data=data, files=files)
                    if resp.status_code in [200, 201]:
                        return True, f"Successfully submitted to Greenhouse ({job.company})!"
                    else:
                        return False, f"Greenhouse response {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"Greenhouse submission exception: {str(e)}"

    async def _apply_lever(self, job: JobModel, resume_pdf: Path) -> Tuple[bool, str]:
        parts = job.external_id.split("_")
        if len(parts) < 3:
            return False, "Invalid Lever external ID format"

        company = parts[1]
        job_id = parts[2]
        api_url = f"https://api.lever.co/v0/postings/{company}/{job_id}/apply"

        data = {
            "name": self.config.profile.full_name,
            "email": self.config.profile.email,
            "phone": self.config.profile.phone,
            "urls[LinkedIn]": self.config.profile.linkedin,
            "urls[GitHub]": self.config.profile.github,
            "urls[Portfolio]": self.config.profile.portfolio,
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                with open(resume_pdf, "rb") as f:
                    files = {"resume": (resume_pdf.name, f.read(), "application/pdf")}
                    resp = await client.post(api_url, data=data, files=files)
                    if resp.status_code in [200, 201]:
                        return True, f"Successfully submitted to Lever ({job.company})!"
                    else:
                        return False, f"Lever response {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"Lever submission exception: {str(e)}"

    async def _apply_ashby(self, job: JobModel, resume_pdf: Path) -> Tuple[bool, str]:
        # Ashby application endpoint
        parts = job.external_id.split("_")
        company = parts[1] if len(parts) > 1 else job.company.lower()
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}/application"

        data = {
            "name": self.config.profile.full_name,
            "email": self.config.profile.email,
            "phone": self.config.profile.phone,
            "linkedinUrl": self.config.profile.linkedin,
            "githubUrl": self.config.profile.github,
            "portfolioUrl": self.config.profile.portfolio,
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                with open(resume_pdf, "rb") as f:
                    files = {"resume": (resume_pdf.name, f.read(), "application/pdf")}
                    resp = await client.post(api_url, data=data, files=files)
                    if resp.status_code in [200, 201]:
                        return True, f"Successfully submitted to Ashby ({job.company})!"
                    else:
                        return False, f"Ashby response {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"Ashby submission exception: {str(e)}"
