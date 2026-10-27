"""Greenhouse Public Board API Scraper."""
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from bs4 import BeautifulSoup
from hunterz.scrapers.base import BaseScraper
from hunterz.db.models import JobModel


class GreenhouseScraper(BaseScraper):
    """Scrapes jobs directly from Greenhouse public board API with high concurrency and millisecond precision."""

    async def scrape(self) -> List[JobModel]:
        jobs: List[JobModel] = []
        boards = self.config.boards.greenhouse
        max_age = timedelta(hours=self.config.search.max_age_hours)
        now = datetime.now(timezone.utc)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        semaphore = asyncio.Semaphore(10)

        async def fetch_board(client: httpx.AsyncClient, board: str):
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            async with semaphore:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return []
                    data = resp.json()
                    raw_jobs = data.get("jobs", [])
                    board_jobs = []

                    for item in raw_jobs:
                        updated_str = item.get("updated_at")
                        if updated_str:
                            try:
                                posted_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                            except Exception:
                                posted_at = now - timedelta(hours=1)
                        else:
                            posted_at = now - timedelta(hours=1)

                        title = item.get("title", "").strip()
                        location_obj = item.get("location", {})
                        location = location_obj.get("name", "Unknown") if isinstance(location_obj, dict) else str(location_obj)

                        raw_html = item.get("content", "")
                        clean_desc = BeautifulSoup(raw_html, "html.parser").get_text(separator="\n").strip() if raw_html else ""

                        board_jobs.append(JobModel(
                            external_id=f"greenhouse_{board}_{item.get('id')}",
                            title=title,
                            company=board.capitalize(),
                            location=location,
                            url=item.get("absolute_url", f"https://boards.greenhouse.io/{board}/jobs/{item.get('id')}"),
                            source="greenhouse",
                            posted_at=posted_at.replace(tzinfo=None),
                            description=clean_desc[:4000]
                        ))
                    return board_jobs
                except Exception:
                    return []

        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            tasks = [fetch_board(client, b) for b in boards]
            results = await asyncio.gather(*tasks)
            for r in results:
                jobs.extend(r)

        return jobs
