"""Configuration management for HunterZ using Pydantic."""
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import dotenv
import yaml
from pydantic import BaseModel, Field

dotenv.load_dotenv()


class EducationConfig(BaseModel):
    degree: str = "B.Tech in Computer Science and Engineering"
    university: str = "Veer Bahadur Singh Purvanchal University"
    graduation_year: int = 2027


class ProfileConfig(BaseModel):
    full_name: str = "Abhishek Yadav"
    dob: str = "2005-02-18"  # 18 Feb 2005
    age: int = 21
    email: str = "abhicps19@gmail.com"
    phone: str = "+91-9580818926"
    address_line1: str = "Jaunpur"
    address_line2: str = "Uttar Pradesh"
    city: str = "Jaunpur"
    state: str = "Uttar Pradesh"
    postal_code: str = "222001"
    country: str = "India"
    location: str = "Jaunpur, Uttar Pradesh, India"
    nationality: str = "Indian"
    languages: str = "English, Hindi"
    work_authorization: str = "Authorized to work in India (Open to global remote & visa sponsorship)"
    notice_period: str = "Immediate (0 days)"
    willing_to_relocate: bool = True
    work_mode: str = "Remote Priority / WFH"
    salary_expectation: str = "Competitive / Negotiable"
    core_skills: str = "Java, Python, FastAPI, Spring Boot, Microservices, REST APIs, Distributed Systems, SQL, Redis"
    secondary_skills: str = "React, TypeScript, Docker, CI/CD, Git, Linux"
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    bio: str = "Backend & Software Development Engineer specializing in high-throughput data automation, microservices, and distributed systems."
    linkedin: str = "https://linkedin.com/in/abhishek-yadav-4738032b7/"
    github: str = "https://github.com/Abhiboss07"
    portfolio: str = "https://portfolio-abhishek-01.vercel.app"
    current_role: str = "Software Development Engineer"
    years_experience: int = 1
    education: EducationConfig = Field(default_factory=EducationConfig)


class SearchConfig(BaseModel):
    max_age_hours: int = 48
    highlight_ultra_fresh_minutes: int = 60
    strict_max_age: bool = True
    enable_linkedin: bool = True
    linkedin_safe_mode: bool = True
    linkedin_max_queries: int = 2  # Strict safe limit to protect IP and account
    target_roles: List[str] = [
        "Software Engineer",
        "Software Development Engineer",
        "SDE",
        "SDE-1",
        "SDE 1",
        "Junior Software Engineer",
        "Backend Engineer",
        "Backend Developer",
        "Full Stack Developer",
        "Full Stack Engineer",
        "Forward Deployed Engineer",
        "FDE",
        "Python Developer",
        "Java Developer"
    ]
    exclude_keywords: List[str] = [
        "Senior",
        "Sr.",
        "Lead",
        "Staff",
        "Principal",
        "Director",
        "VP",
        "Manager",
        "Intern",
        "Internship"
    ]
    locations: List[str] = [
        "Remote",
        "India",
        "Bengaluru",
        "Bangalore",
        "Delhi",
        "Noida",
        "Gurugram",
        "Hyderabad",
        "Pune",
        "United States",
        "Anywhere"
    ]


class ApplyConfig(BaseModel):
    mode: str = "hybrid"  # "hybrid", "copilot", "autopilot"
    min_match_score_to_auto_apply: int = 75
    dry_run: bool = False
    resume_template_path: str = "hunterz/resume/templates/resume_base.tex"


class BoardsConfig(BaseModel):
    greenhouse: List[str] = Field(default_factory=list)
    lever: List[str] = Field(default_factory=list)
    ashby: List[str] = Field(default_factory=list)


class HunterZConfig(BaseModel):
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    apply: ApplyConfig = Field(default_factory=ApplyConfig)
    boards: BoardsConfig = Field(default_factory=BoardsConfig)


def load_config(config_path: Optional[str] = None) -> HunterZConfig:
    """Load config from YAML file or return defaults."""
    if config_path:
        path = Path(config_path)
    else:
        path = Path("config.yaml")
        if not path.exists():
            path = Path(__file__).resolve().parent.parent / "config.yaml"

    if not path.exists():
        return HunterZConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cfg = HunterZConfig(**data)
    if not cfg.profile.telegram_bot_token and os.getenv("TELEGRAM_BOT_TOKEN"):
        cfg.profile.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not cfg.profile.telegram_chat_id and os.getenv("TELEGRAM_CHAT_ID"):
        cfg.profile.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return cfg
