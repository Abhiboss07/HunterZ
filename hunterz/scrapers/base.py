"""Base scraper class for HunterZ job sources."""
from abc import ABC, abstractmethod
from typing import List
from hunterz.db.models import JobModel
from hunterz.config import HunterZConfig


class BaseScraper(ABC):
    """Abstract base class that all platform scrapers must implement."""

    def __init__(self, config: HunterZConfig):
        self.config = config

    @abstractmethod
    async def scrape(self) -> List[JobModel]:
        """Scrape jobs from the source and return a list of JobModel instances."""
        pass
