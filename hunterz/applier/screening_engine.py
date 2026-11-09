import os
import re
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from hunterz.config import ProfileConfig


class ScreeningQuestionEngine:
    """Intelligently maps, synthesizes, and caches candidate answers for custom

    application screening questions, ensuring no question is left blank or answered
    with 0 experience for requested technologies.
    """

    STOPWORDS = {
        "how", "many", "years", "of", "do", "you", "have", "with", "experience",
        "please", "specify", "your", "the", "a", "an", "in", "to", "for", "are",
        "what", "is", "indicate", "at", "on", "from", "any", "which", "select"
    }

    def __init__(self, profile: ProfileConfig, cache_file: Optional[Path] = None):
        self.profile = profile
        self.cache_file = Path(cache_file) if cache_file else Path("data/answers_cache.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def normalize_question(self, question: str) -> str:
        """Strips punctuation and stopwords to produce a deterministic key."""
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", question.lower())
        tokens = [t.strip() for t in cleaned.split() if t.strip() and t.strip() not in self.STOPWORDS]
        if not tokens:
            tokens = [t.strip() for t in cleaned.split() if t.strip()]
        return "_".join(tokens)

    async def get_answer(
        self,
        question: str,
        placeholder: str = "",
        choices: Optional[List[str]] = None,
        job_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolves an answer for a screening question using cache, profile rules, or LLM reasoning."""
        q_norm = self.normalize_question(question)
        q_lower = f"{question} {placeholder}".lower()

        # Tier 1: Cache Lookup
        if q_norm in self._cache:
            val = self._cache[q_norm]
            return self._match_choice(val, choices) if choices else val

        for cached_key, cached_val in self._cache.items():
            if cached_key in q_norm or q_norm in cached_key:
                return self._match_choice(cached_val, choices) if choices else cached_val

        # Tier 2: Deterministic Profile and Heuristic Rules
        answer = self._resolve_from_rules(q_lower, question)

        # Tier 3: LLM Reasoning Fallback or Heuristic Synthesizer
        if answer is None:
            answer = await self._synthesize_answer(question, choices, job_context)

        if answer is not None:
            self._cache[q_norm] = str(answer)
            self._save_cache()
            return self._match_choice(str(answer), choices) if choices else str(answer)

        return None

    def _resolve_from_rules(self, q_lower: str, question: str) -> Optional[str]:
        """Maps standard identity, location, role, and compliance questions."""
        p = self.profile

        # 1. Names
        if any(k in q_lower for k in ["first name", "given name", "forename"]):
            return p.full_name.split()[0]
        if any(k in q_lower for k in ["last name", "surname", "family name"]):
            parts = p.full_name.split()
            return parts[-1] if len(parts) > 1 else parts[0]
        if any(k in q_lower for k in ["full name", "legal name", "candidate name", "preferred name"]):
            return p.full_name

        # 2. Contact
        if "email" in q_lower:
            return p.email
        if any(k in q_lower for k in ["phone", "mobile", "telephone", "cell"]):
            return p.phone

        # 3. Location & Address
        if any(k in q_lower for k in ["address line 1", "street address", "first line"]):
            return getattr(p, "address_line1", "Jaunpur")
        if any(k in q_lower for k in ["address line 2", "apartment", "suite"]):
            return getattr(p, "address_line2", "Uttar Pradesh")
        if "city" in q_lower:
            return getattr(p, "city", "Jaunpur")
        if any(k in q_lower for k in ["state", "province", "region"]):
            return getattr(p, "state", "Uttar Pradesh")
        if any(k in q_lower for k in ["postal", "zip", "pincode", "pin"]):
            return getattr(p, "postal_code", "222001")
        if "country" in q_lower:
            return getattr(p, "country", "India")
        if any(k in q_lower for k in ["location", "current location", "where are you"]):
            return p.location

        # 4. URLs
        if "linkedin" in q_lower:
            return p.linkedin
        if any(k in q_lower for k in ["github", "git", "repository"]):
            return p.github
        if any(k in q_lower for k in ["portfolio", "website", "personal site", "blog"]):
            return p.portfolio

        # 5. Work Authorization & Visa
        if any(k in q_lower for k in ["authorized to work", "legally authorized", "work authorization", "eligible to work", "legal right"]):
            return "Yes"
        if any(k in q_lower for k in ["require sponsorship", "need sponsorship", "visa sponsorship"]):
            return "No"

        # 6. Negative screening / Legal & Conflict
        if any(k in q_lower for k in ["conflict of interest", "convicted", "felony", "criminal", "misconduct", "disciplinary", "related to any current employees"]):
            return "No"

        # 7. Availability, Notice Period & Relocation
        if any(k in q_lower for k in ["notice period", "availability", "how soon", "start date", "when can you start"]):
            return getattr(p, "notice_period", "Immediate (0 days)")
        if any(k in q_lower for k in ["relocate", "relocation", "willing to relocate"]):
            return "Yes"
        if any(k in q_lower for k in ["work arrangement", "remote", "hybrid", "on-site", "work mode"]):
            return getattr(p, "work_mode", "Remote Priority / WFH")

        # 8. Compensation
        if any(k in q_lower for k in ["salary", "compensation", "desired pay", "expected pay", "rate"]):
            return getattr(p, "salary_expectation", "Competitive / Negotiable")

        # 9. Source / Referral
        if any(k in q_lower for k in ["hear about", "referral", "source", "how did you find"]):
            return "LinkedIn"

        # 10. Education
        if any(k in q_lower for k in ["graduation year", "grad year"]):
            return str(getattr(p.education, "graduation_year", 2027))
        if any(k in q_lower for k in ["university", "college", "school", "institution", "alma mater"]):
            return p.education.university
        if any(k in q_lower for k in ["degree", "qualification", "major", "field of study"]):
            return p.education.degree

        # 11. Work Experience & The "No Zero Experience" Rule
        if any(k in q_lower for k in ["years of experience", "total experience", "yoe", "years with", "years working"]):
            # For primary backend tech stack: 2 years; for others: 1 year. Never 0!
            primary_stack = ["java", "python", "fastapi", "spring", "backend", "sql", "api", "git", "linux", "docker"]
            if any(t in q_lower for t in primary_stack):
                return "2"
            return "1"

        if any(k in q_lower for k in ["current company", "current employer", "organization"]):
            return "Software Engineer"
        if any(k in q_lower for k in ["current title", "current role", "job title", "designation"]):
            return p.current_role

        # 12. Technical Highlights & Pitch
        if any(k in q_lower for k in ["project", "achievement", "proud of", "technical accomplishment", "built"]):
            return (
                "Engineered a distributed key-value store in Java 17 using Raft consensus, "
                "sub-millisecond P99 latency, and a real-time voice AI platform using FastAPI and WebSockets."
            )
        if any(k in q_lower for k in ["why do you want", "what excites you", "why this role", "cover letter", "tell us about yourself", "summary", "note to hiring"]):
            return (
                f"SDE focused on building high-performance distributed systems, microservices, and backend APIs. "
                f"Core strengths in Java 17, Python, FastAPI, Spring Boot, Redis, and high-concurrency systems."
            )

        return None

    async def _synthesize_answer(
        self,
        question: str,
        choices: Optional[List[str]] = None,
        job_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates an affirmative, qualified response via LLM or structured heuristic synthesizer."""
        # 1. Try external LLM if API key is configured
        llm_answer = await self._call_llm_api(question, choices, job_context)
        if llm_answer:
            return llm_answer

        # 2. Heuristic fallback based on question shape
        q_lower = question.lower()

        # Boolean inquiry
        if any(q_lower.startswith(prefix) for prefix in ["are you", "do you", "will you", "have you", "can you", "is "]):
            if any(w in q_lower for w in ["conflict", "felony", "crime", "convict", "misconduct", "dismissed"]):
                return "No"
            return "Yes"

        # Numeric inquiry
        if any(w in q_lower for w in ["how many", "number of", "years"]):
            return "1"

        # Pitch or open-ended inquiry
        return (
            "Experienced in building high-throughput distributed systems, resilient backend APIs, "
            "and microservices using Java 17 and Python. Highly motivated to deliver clean, scalable solutions."
        )

    async def _call_llm_api(
        self,
        question: str,
        choices: Optional[List[str]],
        job_context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Calls available LLM API (Groq, Gemini, Anthropic, or OpenAI) if credentials exist."""
        prompt = (
            f"You are answering a job application screening question on behalf of a Software Development Engineer candidate.\n"
            f"Candidate: Abhishek Yadav (SDE-1, Java 17, Spring Boot, Python, FastAPI, Redis, Microservices).\n"
            f"Target Rules:\n"
            f"- Never state 0 years of experience. Infer at least 1 year from related software engineering experience.\n"
            f"- Answer affirmatively for work authorization, legal right to work, and relocation.\n"
            f"- Answer 'No' for conflicts of interest or criminal records.\n"
            f"- If choices are provided, you MUST pick exactly one choice from the list.\n"
            f"Question: {question}\n"
        )
        if choices:
            prompt += f"Allowed Choices: {json.dumps(choices)}\n"

        # Check Groq API
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                        json={
                            "model": "llama-3.3-70b-versatile",
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "max_tokens": 100,
                        },
                    )
                    if resp.status_code == 200:
                        text = resp.json()["choices"][0]["message"]["content"].strip()
                        return text
            except Exception:
                pass

        # Check Gemini API
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                    resp = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                    )
                    if resp.status_code == 200:
                        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return text
            except Exception:
                pass

        return None

    def _match_choice(self, answer: str, choices: List[str]) -> str:
        """Finds the best matching choice among allowed dropdown options."""
        clean_choices = [c for c in choices if not any(p in c.lower() for p in ["select", "choose", "none of the above", "--"])]
        if not clean_choices:
            clean_choices = choices

        ans_lower = answer.lower()
        # Exact match
        for c in clean_choices:
            if c.lower() == ans_lower:
                return c

        # Substring match
        for c in clean_choices:
            if ans_lower in c.lower() or c.lower() in ans_lower:
                return c

        return clean_choices[0] if clean_choices else answer
