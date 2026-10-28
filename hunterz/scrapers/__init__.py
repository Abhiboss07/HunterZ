"""Scraper orchestrator for HunterZ."""
import asyncio
from typing import List
from hunterz.config import HunterZConfig
from hunterz.db.models import JobModel
from hunterz.scrapers.greenhouse import GreenhouseScraper
from hunterz.scrapers.lever import LeverScraper
from hunterz.scrapers.ashby import AshbyScraper
from hunterz.scrapers.linkedin import LinkedInScraper
from hunterz.scrapers.startup_portals import StartupPortalsScraper


async def scrape_all_sources(config: HunterZConfig) -> List[JobModel]:
    """Run all enabled scrapers concurrently and return combined jobs."""
    scrapers = [
        GreenhouseScraper(config),
        LeverScraper(config),
        AshbyScraper(config),
        LinkedInScraper(config),
        StartupPortalsScraper(config)
    ]

    tasks = [scraper.scrape() for scraper in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs: List[JobModel] = []
    seen_ids = set()

    for res in results:
        if isinstance(res, list):
            for job in res:
                if job.external_id not in seen_ids:
                    seen_ids.add(job.external_id)
                    all_jobs.append(job)

    # Sort newest first
    all_jobs.sort(key=lambda j: j.posted_at, reverse=True)
    return all_jobs
