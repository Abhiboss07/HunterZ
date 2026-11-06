"""Ultra-Fresh Job Detection Engine (~1 min to 15 min publication delta)."""
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any
from hunterz.db.models import JobModel
from hunterz.config import HunterZConfig
from hunterz.scrapers.greenhouse import GreenhouseScraper
from hunterz.scrapers.lever import LeverScraper
from hunterz.scrapers.ashby import AshbyScraper
from hunterz.scrapers.startup_portals import StartupPortalsScraper


class UltraFreshScanner:
    """
    High-frequency scanner engineered to discover newly published openings
    within ~1 minute to 15 minutes of being posted on ATS boards.
    """

    def __init__(self, config: HunterZConfig):
        self.config = config
        self.known_external_ids: set = set()

    async def scan_for_ultra_fresh(self, max_minutes: int = 15) -> List[Tuple[JobModel, str]]:
        """
        Polls ATS endpoints with millisecond timestamps and returns newly posted roles
        categorized by recency delta ('1_MIN_AGO', '15_MIN_AGO', 'FRESH_1H').
        """
        now = datetime.now(timezone.utc)
        all_raw_jobs: List[JobModel] = []

        scrapers = [
            AshbyScraper(self.config),
            GreenhouseScraper(self.config),
            LeverScraper(self.config),
            StartupPortalsScraper(self.config)
        ]

        tasks = [s.scrape() for s in scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                all_raw_jobs.extend(res)

        fresh_results: List[Tuple[JobModel, str]] = []

        for job in all_raw_jobs:
            # Calculate exact age in seconds
            posted_tz = job.posted_at.replace(tzinfo=timezone.utc) if not job.posted_at.tzinfo else job.posted_at
            age_seconds = max(0.0, (now - posted_tz).total_seconds())

            if age_seconds <= 120:
                delta_tag = "⚡ ULTRA_FRESH_1M"
            elif age_seconds <= 900:
                delta_tag = "🔥 FRESH_15M"
            elif age_seconds <= 3600:
                delta_tag = "✨ FRESH_1H"
            else:
                continue  # Outside ultra-fresh threshold

            fresh_results.append((job, delta_tag))

        # Sort with newest (~1m ago) at the top
        fresh_results.sort(key=lambda item: (now - (item[0].posted_at.replace(tzinfo=timezone.utc) if not item[0].posted_at.tzinfo else item[0].posted_at)).total_seconds())
        return fresh_results
