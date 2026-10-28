"""LinkedIn Public Guest Job Search Scraper with strict safety limits and rate protection."""
import asyncio
import random
import httpx
from datetime import datetime, timezone, timedelta
from typing import List
from bs4 import BeautifulSoup
from hunterz.scrapers.base import BaseScraper
from hunterz.db.models import JobModel

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
]


class LinkedInScraper(BaseScraper):
    """Scrapes fresh jobs (<1h & <24h) from LinkedIn Guest Search with strict safety limits."""

    async def scrape(self) -> List[JobModel]:
        # Respect user settings: skip if disabled or if safe mode restricts
        if not getattr(self.config.search, "enable_linkedin", True):
            return []

        jobs: List[JobModel] = []
        max_queries = getattr(self.config.search, "linkedin_max_queries", 2)
        safe_mode = getattr(self.config.search, "linkedin_safe_mode", True)

        # In safe mode, limit queries strictly to 1-2 to protect personal account and IP
        target_roles = ["Software Engineer", "Backend Engineer"] if safe_mode else self.config.search.target_roles[:2]
        locations = ["Remote"] if safe_mode else ["Remote", "India"]

        query_plan = []
        for r in target_roles:
            for loc in locations:
                query_plan.append((r, loc, "r3600"))  # <1 hour filter
                if not safe_mode:
                    query_plan.append((r, loc, "r86400"))  # <24 hour filter

        query_plan = query_plan[:max_queries]

        async def fetch_one(client: httpx.AsyncClient, role: str, loc: str, time_filter: str) -> List[JobModel]:
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={role}&location={loc}&f_TPR={time_filter}&start=0"
            try:
                # Polite human-like delay between requests (3.5 - 5.5s) to guarantee safe zone
                delay = random.uniform(3.5, 5.5) if safe_mode else random.uniform(1.0, 2.0)
                await asyncio.sleep(delay)

                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }

                resp = await client.get(url, headers=headers, timeout=12.0)
                if resp.status_code in [429, 999, 403]:
                    # LinkedIn rate limit detected: abort immediately to protect IP
                    return []
                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                batch_jobs = []

                for card in cards:
                    title_elem = card.find("h3", class_="base-search-card__title")
                    company_elem = card.find("h4", class_="base-search-card__subtitle")
                    location_elem = card.find("span", class_="job-search-card__location")
                    link_elem = card.find("a", class_="base-card__full-link")
                    time_elem = card.find("time")

                    if not (title_elem and link_elem):
                        continue

                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"
                    location = location_elem.get_text(strip=True) if location_elem else loc
                    job_url = link_elem.get("href", "").split("?")[0]
                    job_id = job_url.split("-")[-1] if "-" in job_url else str(hash(job_url))

                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    posted_at = now - timedelta(minutes=15) if time_filter == "r3600" else now - timedelta(hours=4)

                    if time_elem and time_elem.get("datetime"):
                        try:
                            posted_at = datetime.fromisoformat(time_elem.get("datetime"))
                        except Exception:
                            pass

                    batch_jobs.append(JobModel(
                        external_id=f"linkedin_{job_id}",
                        title=title,
                        company=company,
                        location=location,
                        url=job_url,
                        source="linkedin",
                        posted_at=posted_at,
                        description=f"Position: {title} at {company} ({location})"
                    ))
                return batch_jobs
            except Exception:
                return []

        # Run sequentially with timeout to prevent IP concurrency bursts
        async with httpx.AsyncClient(timeout=15.0) as client:
            for r, loc, tf in query_plan:
                res = await fetch_one(client, r, loc, tf)
                jobs.extend(res)
                if not res:
                    # If empty or throttled, avoid further requests
                    break

        return jobs
