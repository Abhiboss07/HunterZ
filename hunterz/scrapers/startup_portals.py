"""Startup, Community & Remote Job Scrapers (RemoteOK, WeWorkRemotely, Arbeitnow, Jobicy, HackerNews, YCombinator, Wellfound)."""
import asyncio
import httpx
import re
import warnings
from datetime import datetime, timezone, timedelta
from typing import List
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from hunterz.scrapers.base import BaseScraper
from hunterz.db.models import JobModel

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class StartupPortalsScraper(BaseScraper):
    """Scrapes early-stage startups and 100% remote software roles across multiple high-yield portals."""

    async def scrape(self) -> List[JobModel]:
        jobs: List[JobModel] = []
        max_age = timedelta(hours=self.config.search.max_age_hours or 48)
        now = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=15.0, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            tasks = [
                self._scrape_weworkremotely(client, now, max_age),
                self._scrape_arbeitnow(client, now, max_age),
                self._scrape_jobicy(client, now, max_age),
                self._scrape_remoteok(client, now, max_age),
                self._scrape_hackernews(client, now, max_age),
                self._scrape_ycombinator(client, now, max_age),
                self._scrape_wellfound(client, now, max_age),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    jobs.extend(r)

        return jobs

    async def _scrape_weworkremotely(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        jobs = []
        try:
            url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.find_all("item")
                for it in items:
                    pub_date = it.find("pubdate")
                    if not pub_date:
                        continue
                    try:
                        from email.utils import parsedate_to_datetime
                        posted_at = parsedate_to_datetime(pub_date.text)
                    except Exception:
                        continue

                    title_elem = it.find("title")
                    title_full = title_elem.text if title_elem else ""
                    if ":" in title_full:
                        company, title = title_full.split(":", 1)
                        company = company.strip()
                        title = title.strip()
                    else:
                        company = "Remote Tech"
                        title = title_full.strip()

                    link = it.find("link").text if it.find("link") else ""
                    desc = it.find("description").text if it.find("description") else ""

                    jobs.append(JobModel(
                        external_id=f"wwr_{abs(hash(link))}",
                        title=title,
                        company=company,
                        location="Remote",
                        url=link,
                        source="weworkremotely",
                        posted_at=posted_at.replace(tzinfo=None),
                        description=BeautifulSoup(desc, "html.parser").get_text(separator="\n").strip()[:4000]
                    ))
        except Exception:
            pass
        return jobs

    async def _scrape_arbeitnow(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        jobs = []
        try:
            resp = await client.get("https://www.arbeitnow.com/api/job-board-api")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for item in data:
                    created_at = item.get("created_at")
                    if not created_at:
                        continue
                    posted_at = datetime.fromtimestamp(created_at, tz=timezone.utc)

                    title = item.get("title", "").strip()
                    company = item.get("company_name", "").strip()
                    url = item.get("url", "")
                    loc = "Remote" if item.get("remote") else item.get("location", "Remote")

                    jobs.append(JobModel(
                        external_id=f"arbeitnow_{item.get('slug')}",
                        title=title,
                        company=company,
                        location=loc,
                        url=url,
                        source="arbeitnow",
                        posted_at=posted_at.replace(tzinfo=None),
                        description=(item.get("description", "") or "")[:4000]
                    ))
        except Exception:
            pass
        return jobs

    async def _scrape_jobicy(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        jobs = []
        try:
            resp = await client.get("https://jobicy.com/api/v2/remote-jobs?count=50&tag=dev")
            if resp.status_code == 200:
                jobs_data = resp.json().get("jobs", [])
                for item in jobs_data:
                    pub_date = item.get("pubDate")
                    if not pub_date:
                        continue
                    try:
                        posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except Exception:
                        try:
                            from email.utils import parsedate_to_datetime
                            posted_at = parsedate_to_datetime(pub_date)
                        except Exception:
                            posted_at = now - timedelta(hours=2)

                    jobs.append(JobModel(
                        external_id=f"jobicy_{item.get('id')}",
                        title=item.get("jobTitle", "").strip(),
                        company=item.get("companyName", "").strip(),
                        location="Remote",
                        url=item.get("url", ""),
                        source="jobicy",
                        posted_at=posted_at.replace(tzinfo=None),
                        description=(item.get("jobDescription", "") or "")[:4000]
                    ))
        except Exception:
            pass
        return jobs

    async def _scrape_remoteok(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        jobs = []
        try:
            resp = await client.get("https://remoteok.com/api")
            if resp.status_code == 200:
                data = resp.json()
                for item in data[1:]:
                    if not isinstance(item, dict):
                        continue
                    date_str = item.get("date")
                    if not date_str:
                        continue
                    try:
                        posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except Exception:
                        continue

                    title = item.get("position", "").strip()
                    company = item.get("company", "").strip()
                    url = item.get("url", "")

                    jobs.append(JobModel(
                        external_id=f"remoteok_{item.get('id')}",
                        title=title,
                        company=company,
                        location="Remote",
                        url=url,
                        source="remoteok",
                        posted_at=posted_at.replace(tzinfo=None),
                        description=(item.get("description", "") or "")[:4000]
                    ))
        except Exception:
            pass
        return jobs

    async def _scrape_hackernews(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        jobs = []
        try:
            user_resp = await client.get("https://hacker-news.firebaseio.com/v0/user/whoishiring.json")
            if user_resp.status_code != 200:
                return []
            submitted = user_resp.json().get("submitted", [])[:3]

            for story_id in submitted:
                story_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                if story_resp.status_code != 200:
                    continue
                story = story_resp.json()
                title = story.get("title", "")
                if "who is hiring" not in title.lower():
                    continue

                kids = story.get("kids", [])[:40]
                for kid_id in kids:
                    try:
                        comment_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json")
                        if comment_resp.status_code != 200:
                            continue
                        comment = comment_resp.json()
                        text = comment.get("text", "")
                        if not text:
                            continue

                        clean_text = BeautifulSoup(text, "html.parser").get_text(separator="\n").strip()
                        lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
                        if not lines:
                            continue

                        first_line = lines[0]
                        parts = [p.strip() for p in first_line.split("|")]
                        company = parts[0] if len(parts) > 0 else "Hacker News Startup"
                        role_cand = parts[1] if len(parts) > 1 else first_line
                        loc_cand = parts[2] if len(parts) > 2 else "Remote"

                        if not any(k in first_line.lower() for k in ["engineer", "developer", "sde", "backend", "full stack"]):
                            continue

                        time_val = comment.get("time", 0)
                        posted_at = datetime.fromtimestamp(time_val, tz=timezone.utc)

                        jobs.append(JobModel(
                            external_id=f"hn_{kid_id}",
                            title=role_cand[:60],
                            company=company[:40],
                            location="Remote" if "remote" in first_line.lower() else loc_cand[:30],
                            url=f"https://news.ycombinator.com/item?id={kid_id}",
                            source="hackernews",
                            posted_at=posted_at.replace(tzinfo=None),
                            description=clean_text[:4000]
                        ))
                    except Exception:
                        continue
                break
        except Exception:
            pass
        return jobs

    async def _scrape_ycombinator(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        """Scrapes real-time Y Combinator startup jobs via official Algolia feed."""
        jobs = []
        try:
            url = "https://hn.algolia.com/api/v1/search_by_date?tags=job&hitsPerPage=50"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json().get("hits", [])
                for item in data:
                    created_str = item.get("created_at")
                    if not created_str:
                        continue
                    try:
                        posted_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    except Exception:
                        continue

                    title = item.get("title", "").strip()
                    if not title:
                        continue

                    company = "YC Startup"
                    clean_title = title
                    m = re.match(r"^([^(]+)\s*(\(YC\s*[A-Z0-9]+\))?\s*(?:is hiring|hiring)?\s*(.*)$", title, re.IGNORECASE)
                    if m:
                        c_part = m.group(1).strip()
                        t_part = m.group(3).strip()
                        if c_part:
                            company = c_part
                        if t_part:
                            clean_title = t_part

                    job_url = item.get("url", f"https://news.ycombinator.com/item?id={item.get('objectID')}")
                    jobs.append(JobModel(
                        external_id=f"yc_{item.get('objectID')}",
                        title=clean_title[:60],
                        company=company[:40],
                        location="Remote",
                        url=job_url,
                        source="ycombinator",
                        posted_at=posted_at.replace(tzinfo=None),
                        description=f"{title} - Apply at {job_url}"
                    ))
        except Exception:
            pass
        return jobs

    async def _scrape_wellfound(self, client: httpx.AsyncClient, now: datetime, max_age: timedelta) -> List[JobModel]:
        """Scrapes fresh Wellfound (AngelList) startup software roles."""
        jobs = []
        try:
            url = "https://wellfound.com/jobs"
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=re.compile(r"/jobs/\d+"))
                for a in links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or len(title) < 4:
                        continue
                    full_url = f"https://wellfound.com{href}" if href.startswith("/") else href
                    m = re.search(r"/jobs/(\d+)", href)
                    job_id = m.group(1) if m else str(abs(hash(href)))
                    jobs.append(JobModel(
                        external_id=f"wellfound_{job_id}",
                        title=title[:60],
                        company="Wellfound Startup",
                        location="Remote",
                        url=full_url,
                        source="wellfound",
                        posted_at=now - timedelta(hours=2),  # Default to within last 2 hours
                        description=f"Position: {title} on Wellfound (AngelList). Direct startup application."
                    ))
        except Exception:
            pass
        return jobs
