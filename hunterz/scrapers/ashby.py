"""Ashby Public Job Board API Scraper with high concurrency."""
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from hunterz.scrapers.base import BaseScraper
from hunterz.db.models import JobModel


class AshbyScraper(BaseScraper):
    """Scrapes jobs directly from Ashby public job board API with concurrent board queries."""

    async def scrape(self) -> List[JobModel]:
        jobs: List[JobModel] = []
        companies = self.config.boards.ashby
        max_age = timedelta(hours=self.config.search.max_age_hours)
        now = datetime.now(timezone.utc)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        semaphore = asyncio.Semaphore(10)

        async def fetch_ashby(client: httpx.AsyncClient, company: str):
            url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
            async with semaphore:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return []
                    data = resp.json()
                    job_list = data.get("jobs", [])
                    company_jobs = []

                    for item in job_list:
                        published_str = item.get("publishedAt")
                        if published_str:
                            try:
                                posted_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                            except Exception:
                                posted_at = now - timedelta(hours=1)
                        else:
                            posted_at = now - timedelta(hours=1)

                        title = item.get("title", "").strip()
                        location = item.get("locationName", "Remote")
                        job_url = item.get("jobUrl", f"https://jobs.ashbyhq.com/{company}/{item.get('id')}")
                        desc = item.get("descriptionPlain", "") or ""

                        company_jobs.append(JobModel(
                            external_id=f"ashby_{company}_{item.get('id')}",
                            title=title,
                            company=company.capitalize(),
                            location=location,
                            url=job_url,
                            source="ashby",
                            posted_at=posted_at.replace(tzinfo=None),
                            description=desc[:4000]
                        ))
                    return company_jobs
                except Exception:
                    return []

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            tasks = [fetch_ashby(client, c) for c in companies]
            results = await asyncio.gather(*tasks)
            for r in results:
                jobs.extend(r)

        return jobs
