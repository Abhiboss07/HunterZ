"""Resume Tailoring Engine: dynamically optimizes bullet points, summary, and skills for each specific job."""
import re
from pathlib import Path
from typing import Tuple, Dict, Any, List
import jinja2
from hunterz.db.models import JobModel
from hunterz.config import ProfileConfig
from hunterz.resume.compiler import compile_tex_to_pdf, compile_html_to_pdf

OUTPUT_DIR = Path("output/resumes")


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters to ensure 100% compilation safety."""
    if not isinstance(text, str):
        return str(text)
    conv = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    regex = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key=lambda item: -len(item))))
    return regex.sub(lambda match: conv[match.group()], text)


# Custom Jinja2 Environment for LaTeX syntax
latex_env = jinja2.Environment(
    block_start_string=r'\BLOCK{',
    block_end_string=r'}',
    variable_start_string=r'\VAR{',
    variable_end_string=r'}',
    comment_start_string=r'\#{',
    comment_end_string=r'}',
    line_statement_prefix='%%',
    line_comment_prefix='%#',
    trim_blocks=True,
    autoescape=False,
)
latex_env.filters['latex'] = escape_latex


class ResumeTailor:
    """Adapts Abhishek's resume for maximum ATS score against a specific Job Description."""

    def __init__(self, profile: ProfileConfig):
        self.profile = profile
        self.tex_template_path = Path("hunterz/resume/templates/resume_base.tex")
        self.html_template_path = Path("hunterz/resume/templates/resume_ats.html")

    def _extract_tailored_context(self, job: JobModel) -> Dict[str, Any]:
        """Align summary, bullet points, tailored bio, and application pitch to specific JD requirements."""
        jd_text = f"{job.title} {job.description}".lower()
        title_lower = job.title.lower()

        # 1. Role Domain Classification & Deep Semantic Pitch Crafting
        is_fde = any(k in title_lower or k in jd_text for k in ["forward deployed", "fde", "solutions engineer", "deployment engineer", "integration engineer"])
        is_fullstack = any(k in title_lower or k in jd_text for k in ["full stack", "fullstack", "frontend and backend", "web developer"])
        is_distributed = any(k in title_lower or k in jd_text for k in ["distributed", "concurrency", "low latency", "storage", "database", "core systems", "scale"])
        is_python_data = any(k in title_lower or k in jd_text for k in ["python developer", "data engineer", "pipeline", "etl", "scraping", "automation"])

        is_camunda = "camunda" in job.company.lower() or "process" in title_lower or "bpmn" in jd_text

        if is_camunda or is_fde:
            tailored_bio = (
                f"Forward Deployed & Backend Engineer with hands-on experience bridging customer technical integration needs with robust microservices. "
                f"Adept at deploying distributed data automation pipelines, troubleshooting production APIs in real time, and delivering rapid, high-impact software solutions for {job.company}."
            )
            why_apply_pitch = (
                f"Why Abhishek for {job.title} at {job.company}: Abhishek combines deep hands-on backend expertise (Java 17, Python, FastAPI) "
                f"with client-facing integration agility, having architected production data automation pipelines and high-throughput microservices. "
                f"His ability to quickly analyze complex systems and deliver production-grade code aligns directly with {job.company}'s mission."
            )
            focus_str = "forward deployed engineering, client integration pipelines, and high-reliability microservices"
            headline = f"Forward Deployed Engineer | Distributed Systems & Process Automation"
        elif is_fullstack:
            tailored_bio = (
                f"Full Stack Engineer with strong foundation in responsive React/TypeScript frontends and high-performance Python/FastAPI microservices backends. "
                f"Creator of a cloud-native Voice AI platform featuring real-time WebSocket metrics, JWT authorization, and MongoDB/Redis persistence."
            )
            why_apply_pitch = (
                f"Why Abhishek for {job.title} at {job.company}: Abhishek offers complete vertical ownership—from crafting clean, responsive TypeScript/React interfaces "
                f"to designing robust RESTful APIs, Redis caching layers, and automated GitHub Actions CI/CD workflows ready for production from day one."
            )
            focus_str = "full-stack web architectures, reactive frontends, and scalable cloud microservices"
            headline = "Full Stack Engineer | React, TypeScript & Python Microservices"
        elif is_distributed:
            tailored_bio = (
                f"Backend & Systems Engineer specializing in distributed systems, concurrency, and persistent in-memory caching. "
                f"Architected an in-memory Distributed Key-Value Store in Java 17 with AOF write-ahead logging, LRU eviction, and multi-threaded TCP server."
            )
            why_apply_pitch = (
                f"Why Abhishek for {job.title} at {job.company}: Abhishek brings verified systems-level programming depth across Java 17 and Python, "
                f"a proven track record implementing write-ahead persistence (AOF) and cache algorithms from scratch, and 144+ unit and concurrency tests ensuring zero regressions."
            )
            focus_str = "distributed systems, high-concurrency architectures, and low-latency data storage"
            headline = "Backend & Distributed Systems Engineer | Java 17 & Microservices"
        else:
            tailored_bio = (
                f"Backend & Software Development Engineer (SDE-1) with 1 year of production experience architecting high-throughput data automation pipelines and RESTful microservices. "
                f"Specializes in Java, Python, FastAPI, Spring Boot, SQL, and Dockerized microservice deployments."
            )
            why_apply_pitch = (
                f"Why Abhishek for {job.title} at {job.company}: Abhishek is an immediate-impact SDE-1 who brings verified production code in Java and Python, "
                f"automated CI/CD pipelines that reduced transaction errors by 30%, and an engineering mindset focused on clean code, automated testing, and reliability."
            )
            focus_str = "scalable backend architectures, clean RESTful APIs, and automated microservices"
            headline = "Software Development Engineer (SDE-1) | Backend & Microservices"

        tailored_summary = (
            f"Software Development Engineer specializing in {focus_str} "
            f"using Java, Python, FastAPI, and Spring Boot. Passionate about building robust APIs, optimizing system throughput, "
            f"and automating production workflows with clean code and rigorous unit testing."
        )

        # Work Experience Bullet Points - Rich, Quantified, High-Impact
        if is_camunda or is_fde:
            exp_current = [
                "Architected and deployed high-throughput Python and Java data pipelines and RESTful microservices using \\textbf{FastAPI, Requests, and BeautifulSoup}, boosting data ingestion by \\textbf{40\\%} with automated schema verification and deduplication.",
                "Engineered automated \\textbf{GitHub Actions CI/CD} pipelines and unit test suites across microservice endpoints, reducing invalid transaction records by \\textbf{30\\%} and ensuring zero-downtime production deployments.",
                "Led customer-facing technical integrations and API troubleshooting, developing modular connectors for legacy REST endpoints and authoring documentation for field deployment agility."
            ]
            exp_intern = [
                "Built automated lead-generation and web scraping pipelines with Python and RESTful API integrations, increasing data acquisition by 40% while improving data quality by 35% through backend verification.",
                "Developed microservices-based automation with GitHub Actions CI/CD and unit testing, improving overall data pipeline reliability, error recovery, and fault tolerance."
            ]
        else:
            exp_current = [
                "Architected and deployed high-throughput Python data pipelines and RESTful microservices using \\textbf{BeautifulSoup, Requests, and FastAPI}, boosting data ingestion by \\textbf{40\\%} with automated verification and deduplication.",
                "Engineered automated \\textbf{GitHub Actions CI/CD} pipelines and comprehensive unit test suites, reducing invalid transaction records by \\textbf{30\\%} and ensuring zero-downtime microservice deployments.",
                "Implemented resilient error handling and asynchronous queueing with Celery and Redis, improving backend endpoint throughput under peak traffic loads."
            ]
            exp_intern = [
                "Built automated lead-generation and web scraping pipelines with Python and RESTful API integrations, increasing data acquisition by 40% while improving data quality by 35% through backend verification.",
                "Developed microservices-based automation with GitHub Actions CI/CD and unit testing, improving overall data pipeline reliability and fault tolerance."
            ]

        # Projects descriptions and detailed bullets
        proj_kv_bullets = [
            "Architected a high-concurrency in-memory KV store in Java 17 featuring a multi-client TCP server (FixedThreadPool) and O(1) LRU cache eviction.",
            "Implemented dual-strategy TTL expiry and AOF write-ahead logging with fsync policies and atomic compaction; verified via 144 unit and concurrency tests."
        ]
        proj_voice_bullets = [
            "Built a cloud-native Voice AI SaaS platform with microservices backend (FastAPI, Redis, Celery, Docker), LiveKit SIP telephony, and OpenAI/Gemini voice models.",
            "Engineered WebSocket real-time metrics streaming, JWT authorization, and responsive React/TypeScript UI for low-latency interactive audio sessions."
        ]
        proj_nexus_bullets = [
            "Developed an open-source cross-platform system telemetry and diagnostics control center using Rust, Tauri v2, React, and TypeScript.",
            "Designed modular plugin architecture with real-time process monitoring, memory analysis, and AI-assisted performance diagnostics."
        ]

        proj_kv = "Built a production-grade in-memory KV store in Java 17: multi-client TCP server, O(1) LRU cache eviction, dual-strategy TTL expiry, and AOF write-ahead logging with fsync policies and atomic compaction. 144 unit & concurrency tests."
        proj_voice = "Engineered a cloud-native Voice AI SaaS platform with microservices backend (FastAPI, MongoDB, Redis, Celery, Docker), JWT auth, WebSocket metrics, LiveKit SIP telephony, and OpenAI/Gemini voice models. Frontend built with React and TypeScript."
        proj_nexus = "Developing a modern Linux command center using Rust, Tauri v2, React, and TypeScript for real-time CPU, memory, and disk monitoring. Modular plugin-based architecture with AI-assisted diagnostics."

        return {
            "name": self.profile.full_name,
            "headline": headline,
            "phone": self.profile.phone,
            "location": self.profile.location,
            "email": self.profile.email,
            "github": self.profile.github,
            "linkedin": self.profile.linkedin,
            "portfolio": self.profile.portfolio,
            "summary": tailored_summary,
            "tailored_bio": tailored_bio,
            "why_apply_pitch": why_apply_pitch,
            "experience_current": exp_current,
            "experience_intern": exp_intern,
            "project_kv": proj_kv,
            "project_voice": proj_voice,
            "project_nexus": proj_nexus,
            "project_kv_bullets": proj_kv_bullets,
            "project_voice_bullets": proj_voice_bullets,
            "project_nexus_bullets": proj_nexus_bullets,
            "coursework": "Distributed Systems, Object-Oriented Programming (Java), Data Structures & Algorithms, Computer Networks, Operating Systems, Database Management Systems",
            "skills_languages": "Java 17, Python, TypeScript, SQL, Rust, C++",
            "skills_backend": "FastAPI, Spring Boot, RESTful APIs, Microservices, gRPC",
            "skills_devops": "Docker, CI/CD, GitHub Actions, Linux, Kubernetes Basics",
            "skills_api": "RESTful API Design, WebSockets, JWT, RBAC, OAuth2",
            "skills_databases": "Redis, MongoDB, MySQL, PostgreSQL, Celery",
            "skills_testing": "Unit & Concurrency Testing (JUnit 5, PyTest), TDD",
            "skills_ai": "OpenAI, Gemini, Agentic Workflows, Prompt Engineering",
            "skills_data": "Data Pipelines, Web Scraping, Process Automation, ETL",
            "skills_frontend": "React, TypeScript, Tailwind CSS, HTML5/CSS3",
            "skills_tools": "Git, VS Code, Cursor, Postman, Linux (Arch/CachyOS)"
        }

    def tailor_with_context(self, job: JobModel) -> Tuple[Path, Path, Dict[str, Any]]:
        """
        Generate tailored .tex and .pdf for this job posting and return the extracted context.
        Returns: (tex_path, pdf_path, context)
        """
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_company = re.sub(r'[^a-zA-Z0-9_-]', '_', job.company)
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(job.id or job.external_id))
        base_name = f"Resume_{safe_company}_{safe_id}"

        tex_out = OUTPUT_DIR / f"{base_name}.tex"
        pdf_out = OUTPUT_DIR / f"{base_name}.pdf"
        html_out = OUTPUT_DIR / f"{base_name}.html"

        context = self._extract_tailored_context(job)

        # 1. Render LaTeX template with LaTeX-safe Jinja2 environment
        if self.tex_template_path.exists():
            with open(self.tex_template_path, "r", encoding="utf-8") as f:
                tex_tmpl = latex_env.from_string(f.read())
            rendered_tex = tex_tmpl.render(**context)
            with open(tex_out, "w", encoding="utf-8") as f:
                f.write(rendered_tex)

        # 2. Try compiling LaTeX locally
        compiled_pdf = compile_tex_to_pdf(tex_out, OUTPUT_DIR)
        if compiled_pdf and compiled_pdf.exists():
            return tex_out, compiled_pdf, context

        # 3. Fallback: Render HTML template and compile to PDF via local headless Chrome
        if self.html_template_path.exists():
            with open(self.html_template_path, "r", encoding="utf-8") as f:
                html_tmpl = jinja2.Template(f.read())

            html_context = dict(context)
            html_context["experience_current"] = [
                b.replace("\\textbf{", "<strong>").replace("}", "</strong>").replace("\\%", "%")
                for b in context["experience_current"]
            ]
            rendered_html = html_tmpl.render(**html_context)
            with open(html_out, "w", encoding="utf-8") as f:
                f.write(rendered_html)

            compile_html_to_pdf(html_out, pdf_out)

        return tex_out, pdf_out, context

    def tailor(self, job: JobModel) -> Tuple[Path, Path]:
        """Generate tailored .tex and .pdf for this job posting."""
        tex_out, pdf_out, _ = self.tailor_with_context(job)
        return tex_out, pdf_out
