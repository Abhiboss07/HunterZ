"""Lever Postings API Scraper with high concurrency."""
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from hunterz.scrapers.base import BaseScraper
from hunterz.db.models import JobModel


class LeverScraper(BaseScraper):
    """Scrapes jobs directly from Lever public postings API with concurrent board polling."""

    async def scrape(self) -> List[JobModel]:
        jobs: List[JobModel] = []
        companies = self.config.boards.lever
        max_age = timedelta(hours=self.config.search.max_age_hours)
        now = datetime.now(timezone.utc)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        semaphore = asyncio.Semaphore(10)

        async def fetch_company(client: httpx.AsyncClient, company: str):
            url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            async with semaphore:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return []
                    postings = resp.json()
                    if not isinstance(postings, list):
                        return []

                    company_jobs = []
                    for item in postings:
                        created_at_ms = item.get("createdAt")
                        if created_at_ms:
                            posted_at = datetime.fromtimestamp(created_at_ms / 1000.0, tz=timezone.utc)
                        else:
                            posted_at = now - timedelta(hours=1)

                        title = item.get("text", "").strip()
                        categories = item.get("categories", {})
                        location = categories.get("location", "Unknown") if isinstance(categories, dict) else "Unknown"
                        desc = item.get("descriptionPlain", "") or ""

                        company_jobs.append(JobModel(
                            external_id=f"lever_{company}_{item.get('id')}",
                            title=title,
                            company=company.capitalize(),
                            location=location,
                            url=item.get("hostedUrl", f"https://jobs.lever.co/{company}/{item.get('id')}"),
                            source="lever",
                            posted_at=posted_at.replace(tzinfo=None),
                            description=desc[:4000]
                        ))
                    return company_jobs
                except Exception:
                    return []

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            tasks = [fetch_company(client, c) for c in companies]
            results = await asyncio.gather(*tasks)
            for r in results:
                jobs.extend(r)

        return jobs
