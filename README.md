# ⚡ HunterZ: Autonomous SDE Job Hunter, Multi-ATS Auto-Applier & AI Resume Tailor

<div align="center">

![HunterZ Banner](https://img.shields.io/badge/Status-Production%20Ready-10B981?style=for-the-badge&logo=rocket)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Playwright](https://img.shields.io/badge/Automation-Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![Local First](https://img.shields.io/badge/Privacy-100%25%20Local--First-6366F1?style=for-the-badge&logo=shield)

**HunterZ** is a high-performance, local-first Terminal engine and Awwwards-caliber Web CRM built to discover newly posted Software Engineer / SDE-1 / Backend / Full Stack / FDE roles within minutes of posting, semantically tailor your resume into a single-page document, auto-fill complex ATS job applications with live screenshot verification, and discover recruiter emails across any company.

[Features](#-key-features) • [Architecture](#-system-architecture) • [Quick Start](#-quick-start) • [Verification Protocol](#-4-layer-verification-protocol) • [Recruiter Finder](#-universal-recruiter-email-finder) • [CLI Reference](#-cli-commands) • [Configuration](#-configuration)

</div>

---

## 🌟 Key Features

### 1. Ultra-Fresh Multi-Platform Scrapers (<1 min to 48 hours)
- **Direct ATS REST APIs**: Directly queries Greenhouse, Lever, and Ashby public board endpoints with zero CAPTCHAs, zero IP-bans, and exact publication timestamps.
- **Aggregators & Startup Portals**: Ingests fresh openings from Arbeitnow, RemoteOK, We Work Remotely, Y Combinator, Hacker News, and Jobicy.
- **LinkedIn Recent Job Stream**: Scrapes public LinkedIn feeds with `<24h` and `<1h` parameters.
- **Strict 48-Hour Hard Cutoff Rule**: Automatically filters out stale openings older than 48 hours so you only compete for roles posted right now.

### 2. Semantic Single-Page Resume Tailoring Engine
- **Target Role Alignment**: Dynamically aligns your professional summary, work experience bullets, and skills to target roles (Forward Deployed Engineer, Distributed Systems, Full Stack, Microservices).
- **Zero Bottom Gap Vertical Rhythm**: Calibrated layout density (`8mm 11mm` margins, `9.1pt` typography, structured tabular skill matrices) ensures your resume fills **100% of exactly 1 single A4 page** with zero awkward trailing gaps and zero spillover.
- **Clean PDF Generation**: Uses local headless Chrome with `--no-pdf-header-footer` to ensure zero browser URL or timestamp leaks.
- **LaTeX Source & PDF**: Generates both `.tex` source and compiled `.pdf` documents locally in under 1 second.

### 3. Smart Hybrid Application Engine
- **Direct REST API Submissions**: Submits multipart/form-data directly to Greenhouse, Lever, and Ashby endpoints in under 300ms.
- **Canonical ATS Redirect Resolution**: Follows redirects from job aggregators (e.g. Arbeitnow) to their true underlying enterprise ATS (Ashby, Greenhouse, Lever).
- **Dynamic Form Automator**: Natively handles complex React single-page forms, radio groups, Yes/No toggle buttons, searchable comboboxes, and GDPR consents.

### 4. 4-Layer Verification Protocol & Visual Screenshot Audit
- **Step 1 (Process Begun)**: Captures screenshot when the browser enters the canonical job portal.
- **Step 2 (Form Populated)**: Captures screenshot with all candidate fields, address, and tailored PDF attached.
- **Step 3 (Submission Status)**: Captures final confirmation or security challenge (reCAPTCHA) screen.
- All screenshots are timestamped, saved to `output/screenshots/`, and embedded in the Web CRM application dossier.

### 5. Universal Recruiter OSINT Email Finder
- **Works for ANY Company**: Automatically derives corporate domain names from any company or job URL (`hunterz recruiters <company>`).
- **Talent Directories & Patterns**: Combines curated talent leads for top tech employers with enterprise email permutations (`first.last@company.com`, `first@company.com`, `flast@company.com`).
- **Corporate Inbound Inboxes**: Inquires verified departmental inboxes (`talent@`, `careers@`, `recruiting@`, `jobs@`).

### 6. Real-Time Tracking & Awwwards-Caliber Web CRM
- **Real-Time Terminal Tracker**: `hunterz tracker --watch` continuously monitors application pipeline updates, visual audit statuses, and recruiter contacts.
- **Modern Web CRM Dashboard**: Built with FastAPI, Alpine.js, Tailwind CSS, and Lucide icons featuring live 4-second polling synchronization.

---

## 🏛️ System Architecture

```
                                  ┌─────────────────────────────┐
                                  │      HUNTERZ ENGINE         │
                                  └──────────────┬──────────────┘
                                                 │
                  ┌──────────────────────────────┼──────────────────────────────┐
                  ▼                              ▼                              ▼
     ┌────────────────────────┐     ┌────────────────────────┐     ┌────────────────────────┐
     │  Multi-Source Scraper  │     │ Resume Tailor Engine   │     │ Smart ATS Applier      │
     │  - Greenhouse / Lever  │     │ - Jinja2 LaTeX/HTML    │     │ - Canonical Resolver   │
     │  - Ashby Public Boards │     │ - Single-Page Budget   │     │ - Direct REST Submitter│
     │  - Arbeitnow / Startups│     │ - Chrome Engine w/o    │     │ - Ashby React Filler   │
     │  - 48h Hard Cutoff     │     │   Header/Footer Leaks  │     │ - Visual Audit Engine  │
     └────────────┬───────────┘     └────────────┬───────────┘     └────────────┬───────────┘
                  │                              │                              │
                  └──────────────────────────────┼──────────────────────────────┘
                                                 │
                                                 ▼
                                    ┌─────────────────────────┐
                                    │     SQLite WAL DB       │
                                    │  jobs / apps / outreach │
                                    └────────────┬────────────┘
                                                 │
                                ┌────────────────┴────────────────┐
                                ▼                                 ▼
                   ┌─────────────────────────┐       ┌─────────────────────────┐
                   │    Web CRM Dashboard    │       │    Terminal CLI Suite   │
                   │  - 4s Real-Time Polling │       │  - hunterz tracker -w   │
                   │  - Visual Dossier Modal │       │  - hunterz recruiters   │
                   │  - Recruiter Outreach   │       │  - hunterz apply / scan │
                   └─────────────────────────┘       └─────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Installation

Ensure Python 3.11+ is installed. Activate the virtual environment:

```bash
cd /home/abhiboss/Projects/HunterZ
source .venv/bin/activate
```

### 2. Launch the Web CRM Dashboard

```bash
hunterz web
# Opens http://127.0.0.1:8096 in your browser
```

### 3. Monitor Applications Live in Terminal

```bash
hunterz tracker --watch
```

---

## 🛡️ 4-Layer Verification Protocol

To prevent blind submissions and false-positive flags, HunterZ enforces a 4-layer verification protocol:

1. **Local Visual Audit**: High-resolution screenshots captured at every stage:
   - `output/screenshots/<company>_step1_begin.png`
   - `output/screenshots/<company>_step2_filled.png`
   - `output/screenshots/<company>_step3_submitted.png`
2. **DOM & File Attachment Verification**: Verifies the tailored resume PDF was accepted and attached to `input#_systemfield_resume`.
3. **Security Challenge Detection**: Accurately detects whether an application was received directly (HTTP 200/confirmation) or encountered a Cloudflare/Google reCAPTCHA verification challenge.
4. **Recruiter Backchannel Outreach**: Generates tailored email pitches and outreach links to talent partners for immediate follow-up.

---

## 🎯 Universal Recruiter Email Finder

Find recruiter contacts and company talent inboxes for **ANY** company:

```bash
# Find recruiters for Camunda:
hunterz recruiters Camunda

# Find recruiters for Stripe:
hunterz recruiters Stripe

# Find recruiters for any other company:
hunterz recruiters Databricks
hunterz recruiters Postman
hunterz recruiters Linear
```

---

## ⌨️ CLI Commands

| Command | Description |
| :--- | :--- |
| `hunterz web` | Launch the Web CRM Dashboard on `http://127.0.0.1:8096` |
| `hunterz tracker` | Display the application pipeline with visual audit status |
| `hunterz tracker --watch` | Real-time live auto-refreshing application pipeline monitor |
| `hunterz recruiters <company>` | Discover recruiter emails, titles, and talent inboxes |
| `hunterz scan` | Trigger multi-source scrapers across 8 platforms and 166 boards |
| `hunterz tailor <job_id>` | Generate single-page tailored LaTeX & PDF resume for a job ID |
| `hunterz apply <job_id> --live` | Submit live application with visual audit screenshots |
| `hunterz apply <job_id> --dry-run` | Simulate application without sending real data |
| `hunterz profile` | Display candidate profile, address, and Telegram settings |
| `hunterz resumes` | List all company-tailored resumes in `output/resumes/` |
| `hunterz db` | Print database statistics and table metrics |

---

## ⚙️ Configuration (`config.yaml`)

Update your verified details, address, target roles, and Telegram alerts in `config.yaml`:

```yaml
profile:
  full_name: Abhishek Yadav
  dob: '2005-02-18'
  age: 21
  email: abhicps19@gmail.com
  phone: +91-9580818926
  address_line1: Jaunpur
  address_line2: Uttar Pradesh
  city: Jaunpur
  state: Uttar Pradesh
  postal_code: '222001'
  country: India
  location: Jaunpur, Uttar Pradesh, India
  work_authorization: Authorized to work in India (Open to global remote & visa sponsorship)
  notice_period: Immediate (0 days)
  willing_to_relocate: true
  work_mode: Remote Priority / WFH
  salary_expectation: Competitive / Negotiable
  linkedin: https://linkedin.com/in/abhishek-yadav-4738032b7/
  github: https://github.com/Abhiboss07
  portfolio: https://portfolio-abhishek-01.vercel.app
  telegram_bot_token: 'YOUR_TELEGRAM_BOT_TOKEN'
  telegram_chat_id: 'YOUR_TELEGRAM_CHAT_ID'

search:
  max_age_hours: 48
  strict_max_age: true
  highlight_ultra_fresh_minutes: 60
  target_roles:
    - Software Engineer
    - SDE-1
    - Backend Engineer
    - Full Stack Developer
    - Forward Deployed Engineer

apply:
  mode: hybrid
  min_match_score_to_auto_apply: 75
  dry_run: false
```

---

## 🔒 Privacy & Local-First Philosophy

- **Zero Cloud Leak**: 100% of candidate profile parsing, resume tailoring, and screenshot capture happens locally on your machine.
- **Zero Third-Party AI Data Collection**: No personal contact information, resumes, or application metrics are transmitted to external AI aggregators.
- **Local Persistence**: All data is stored in your private SQLite database (`data/hunterz.db`) and local folders (`output/resumes/`, `output/screenshots/`).

---

<div align="center">
Built for engineering velocity by Abhishek Yadav.
</div>
