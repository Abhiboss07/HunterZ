import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from hunterz.config import HunterZConfig
from hunterz.db.models import JobModel
from hunterz.applier.direct_ats import DirectATSApplier
from hunterz.applier.browser_applier import BrowserApplier


class ApplicationDispatcher:
    """Coordinates job application routing between Direct ATS REST APIs and

    Playwright-based smart browser automation with automatic escalation on failure.
    """

    def __init__(self, config: HunterZConfig):
        self.config = config
        self.direct_applier = DirectATSApplier(config)
        self.browser_applier = BrowserApplier(config)

    async def apply_job(
        self,
        job: JobModel,
        resume_pdf: Path,
        resume_tex: Path,
        dry_run: bool = False,
        log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str, str, str, Dict[str, Any]]:
        """Applies to a job using Direct REST if applicable, escalating seamlessly

        to BrowserApplier on failure or custom form requirements.

        Returns:
            (success: bool, status: str, method: str, message: str, audit_data: dict)
        """
        # 1. Resolve canonical destination URL
        canonical_url = await self.browser_applier.resolve_canonical_url(job.url, company=job.company)

        target_source = job.source.lower()
        if "ashbyhq.com" in canonical_url:
            target_source = "ashby"
        elif "greenhouse.io" in canonical_url:
            target_source = "greenhouse"
        elif "lever.co" in canonical_url:
            target_source = "lever"

        audit_data: Dict[str, Any] = {
            "canonical_url": canonical_url,
            "target_source": target_source,
            "screenshots": {},
        }

        # 2. Dry run handling
        if dry_run or getattr(self.config.apply, "dry_run", False):
            if log:
                log(f"[SIMULATION] Dry-run application staged for {job.company} via canonical {canonical_url}")
            return True, "SUBMITTED", "SIMULATED", "Dry-run application simulated successfully.", audit_data

        # 3. Direct REST Submission attempt for Greenhouse and Lever
        if target_source in ["greenhouse", "lever"]:
            if log:
                log(f"Attempting Direct ATS REST API submission for {job.company} ({target_source})...")

            try:
                success, msg = await self.direct_applier.apply(job, resume_pdf, resume_tex)
                if success:
                    status = "SUBMITTED"
                    method = "DIRECT_REST"
                    if log:
                        log(f"[SUCCESS] Direct REST submission successful: {msg}")
                    return True, status, method, msg, audit_data
                else:
                    if log:
                        log(f"[NOTICE] Direct REST endpoint returned ({msg}). Escalating to Smart Browser Applier...")
            except Exception as e:
                if log:
                    log(f"[NOTICE] Direct REST exception: {e}. Escalating to Smart Browser Applier...")

            # Escalation to BrowserApplier
            method = "BROWSER_AUTOMATED"
            success, msg, browser_audit = await self.browser_applier.apply(job, resume_pdf, return_audit=True)
            audit_data.update(browser_audit)
            status = "SUBMITTED" if success else "PREPARED"
            return success, status, method, msg, audit_data

        # 4. Browser Automation for Ashby and generic portals
        else:
            method = "BROWSER_ASHBY_AUTOMATED" if "ashby" in canonical_url else "BROWSER"
            if log:
                log(f"Dispatching to Smart Browser Applier for {job.company} ({method})...")

            success, msg, browser_audit = await self.browser_applier.apply(job, resume_pdf, return_audit=True)
            audit_data.update(browser_audit)
            status = "SUBMITTED" if success else "PREPARED"
            return success, status, method, msg, audit_data
