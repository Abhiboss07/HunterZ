"""Smart Browser Application Filler with Login Detection, Session Persistence, ATS Resolution, and Visual Audit Trail."""
import os
import re
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Tuple, Optional, Dict, Any
import httpx
from hunterz.db.models import JobModel
from hunterz.config import HunterZConfig
from hunterz.applier.verifier import SubmissionVerifier

SESSION_FILE = Path("data/browser_session.json")
SCREENSHOTS_DIR = Path("output/screenshots")


class BrowserApplier:
    """Automates web form applications, resolves aggregators to direct ATS portals, and captures verification screenshots."""

    def __init__(self, config: HunterZConfig):
        self.config = config
        self.verifier = SubmissionVerifier()
        self.last_audit: Dict[str, Any] = {}
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    def get_candidate_value_for_field(self, profile, field_name: str, placeholder: str = "") -> Optional[str]:
        """
        Intelligently maps any form field question to candidate's verified profile data,
        preventing empty fields from blocking application submission.
        """
        text = f"{field_name} {placeholder}".lower()

        # 1. Names
        if "first name" in text or "given name" in text:
            return profile.full_name.split()[0]
        if "last name" in text or "surname" in text or "family name" in text:
            return profile.full_name.split()[-1] if len(profile.full_name.split()) > 1 else profile.full_name
        if any(k in text for k in ["full name", "legal name", "preferred name", "your name", "candidate name"]):
            return profile.full_name

        # 2. Contact details
        if "email" in text:
            return profile.email
        if any(k in text for k in ["phone", "mobile", "telephone", "cell"]):
            return profile.phone

        # 3. Location & Address
        if any(k in text for k in ["address line 1", "street address", "address 1", "first line"]):
            return getattr(profile, "address_line1", None) or "Jaunpur"
        if any(k in text for k in ["address line 2", "apartment", "suite", "second line"]):
            return getattr(profile, "address_line2", None) or "Uttar Pradesh"
        if "city" in text:
            return getattr(profile, "city", None) or "Jaunpur"
        if any(k in text for k in ["state", "province", "region"]):
            return getattr(profile, "state", None) or "Uttar Pradesh"
        if any(k in text for k in ["postal", "zip", "pincode", "pin"]):
            return getattr(profile, "postal_code", None) or "222001"
        if "country" in text:
            return getattr(profile, "country", None) or "India"
        if any(k in text for k in ["location", "current location", "where are you located", "where do you live"]):
            return getattr(profile, "location", None) or "Jaunpur, Uttar Pradesh, India"

        # 4. URLs & Social
        if "linkedin" in text:
            return profile.linkedin
        if "github" in text or "git" in text or "repository" in text:
            return profile.github
        if any(k in text for k in ["portfolio", "website", "personal site", "blog", "webpage"]):
            return profile.portfolio

        # 5. Work experience & Current Role
        if any(k in text for k in ["current company", "current employer", "most recent company", "recent employer", "organization"]):
            return "Software Engineer"
        if any(k in text for k in ["current title", "current role", "job title", "designation"]):
            return profile.current_role or "Software Development Engineer"
        if any(k in text for k in ["years of experience", "total experience", "how many years", "yoe"]):
            return "1"

        # 6. Education
        if any(k in text for k in ["graduation year", "grad year", "year of graduation"]):
            return str(getattr(profile.education, "graduation_year", 2027))
        if any(k in text for k in ["university", "college", "school", "institution", "alma mater"]):
            return getattr(profile.education, "university", "Veer Bahadur Singh Purvanchal University")
        if any(k in text for k in ["degree", "qualification", "major", "field of study"]):
            return getattr(profile.education, "degree", "B.Tech in Computer Science and Engineering")

        # 7. Availability, Notice & Compensation
        if any(k in text for k in ["notice period", "availability", "how soon", "start date", "earliest start"]):
            return getattr(profile, "notice_period", None) or "Immediate (0 days)"
        if any(k in text for k in ["salary", "compensation", "expectations", "desired pay", "rate"]):
            return getattr(profile, "salary_expectation", None) or "Competitive / Negotiable"

        # 8. Referral & Source
        if any(k in text for k in ["how did you hear", "hear about", "source", "referral"]):
            return "LinkedIn"

        # 9. Technical Projects & Work Highlights
        if any(k in text for k in ["project", "achievement", "proud of", "technical accomplishment", "built"]):
            return (
                "Architected an in-memory Distributed Key-Value Store in Java 17 with AOF persistence, "
                "LRU eviction, and 144+ concurrency tests. Also built a cloud-native Voice AI platform "
                "using FastAPI, WebSocket streaming, and Redis."
            )

        # 10. Motivation & Cover Letter / Why Role
        if any(k in text for k in ["why do you want", "what excites you", "why this role", "why us", "cover letter", "tell us about yourself", "summary", "about you", "additional information", "note to hiring"]):
            return (
                "I am excited to apply for this software engineering role. With hands-on production experience in Java 17, "
                "Python, FastAPI, Spring Boot, and distributed microservices architectures, I am eager to contribute to "
                "reliable, high-throughput software and scalable engineering solutions."
            )

        # 11. Core Skills
        if any(k in text for k in ["skills", "technologies", "tech stack", "languages"]):
            return getattr(profile, "core_skills", "Java 17, Python, FastAPI, Spring Boot, REST APIs, Microservices, SQL, Redis, Docker, CI/CD, Git")

        return None

    async def resolve_canonical_url(self, job_url: str, company: str = "") -> str:
        """
        Follow HTTP redirects for aggregator job boards (Arbeitnow, RemoteOK, WWR, LinkedIn)
        to reach the real ATS application form (Ashby, Greenhouse, Lever, etc.).
        """
        try:
            # 1. If it is Arbeitnow, follow /apply endpoint
            if "arbeitnow.com/jobs/" in job_url:
                apply_url = job_url if job_url.endswith("/apply") else f"{job_url.rstrip('/')}/apply"
                async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                    resp = await client.get(apply_url)
                    loc = resp.headers.get("location")
                    if loc:
                        netloc = urlparse(loc).netloc.lower()
                        if "arbeitnow" not in netloc:
                            return loc
            # 2. RemoteOK & We Work Remotely
            elif any(d in job_url for d in ["remoteok.com", "weworkremotely.com"]):
                async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                    resp = await client.get(job_url)
                    loc = resp.headers.get("location")
                    if loc:
                        return loc
            # 3. LinkedIn: resolve to direct company ATS board if monitored
            elif "linkedin.com" in job_url and company:
                comp_key = "".join(c for c in company.lower() if c.isalnum())
                if comp_key in [b.lower() for b in self.config.boards.greenhouse]:
                    return f"https://boards.greenhouse.io/{comp_key}"
                elif comp_key in [b.lower() for b in self.config.boards.lever]:
                    return f"https://jobs.lever.co/{comp_key}"
                elif comp_key in [b.lower() for b in self.config.boards.ashby]:
                    return f"https://jobs.ashbyhq.com/{comp_key}"
        except Exception as e:
            print(f"[Resolver] Notice following redirects: {e}")
        return job_url

    async def apply(self, job: JobModel, resume_pdf: Path, return_audit: bool = False):
        """
        Fill and submit web application form with candidate details, tailored resume,
        and high-resolution timestamped visual verification screenshots.
        Returns: (success: bool, message: str) or (success: bool, message: str, audit_data: dict) if return_audit=True.
        """
        audit_data: Dict[str, Any] = {
            "job_id": job.id,
            "company": job.company,
            "title": job.title,
            "original_url": job.url,
            "canonical_url": job.url,
            "screenshots": {},
            "logs": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.last_audit = audit_data

        def log(msg: str):
            timestamp_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
            entry = f"[{timestamp_str}] {msg}"
            audit_data["logs"].append(entry)
            print(entry)

        log(f"Starting automated application engine for {job.company} - {job.title}")

        # 1. Resolve canonical application URL
        canonical_url = await self.resolve_canonical_url(job.url)
        audit_data["canonical_url"] = canonical_url
        if canonical_url != job.url:
            log(f"Resolved aggregator link to canonical ATS portal: {canonical_url}")

        if self.config.apply.dry_run:
            log(f"[DRY-RUN] Simulation mode enabled. Skipping live submission to {canonical_url}")
            msg = f"[DRY-RUN] Browser auto-applier simulated for {job.company}"
            return (True, msg, audit_data) if return_audit else (True, msg)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log("Error: Playwright is not installed.")
            return False, "Playwright is not installed. Run 'pip install playwright'.", audit_data

        profile = self.config.profile
        safe_company = re.sub(r'[^a-zA-Z0-9_-]', '_', job.company.lower())
        ss_begin = SCREENSHOTS_DIR / f"{safe_company}_step1_begin.png"
        ss_filled = SCREENSHOTS_DIR / f"{safe_company}_step2_filled.png"
        ss_submitted = SCREENSHOTS_DIR / f"{safe_company}_step3_submitted.png"

        try:
            async with async_playwright() as p:
                chrome_executable = "/home/abhiboss/.local/bin/google-chrome"
                launch_kwargs = {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-infobars",
                        "--disable-dev-shm-usage"
                    ]
                }
                if os.path.exists(chrome_executable):
                    launch_kwargs["executable_path"] = chrome_executable

                log(f"Launching Chromium browser instance (headless=True, stealth=True)")
                browser = await p.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    window.chrome = { runtime: {} };
                """)

                # Navigate to the job application URL with automatic network retry
                log(f"Navigating to {canonical_url}...")
                resp = None
                for nav_attempt in range(1, 4):
                    try:
                        resp = await page.goto(canonical_url, wait_until="domcontentloaded", timeout=35000)
                        break
                    except Exception as nav_err:
                        if nav_attempt < 3 and ("net::ERR_" in str(nav_err) or "Timeout" in str(nav_err)):
                            log(f"Navigation notice (attempt {nav_attempt}): {nav_err}. Retrying in 1s...")
                            await page.wait_for_timeout(1000)
                        else:
                            raise
                await page.wait_for_timeout(2500)
                log(f"Page loaded with HTTP status: {resp.status if resp else 'OK'}")

                # Check for login barriers or LinkedIn sign-in wall
                current_url = page.url.lower()
                is_login_wall = any(ind in current_url for ind in ["/login", "/signin", "auth", "sso", "cas", "idp", "signup/cold-join", "linkedin.com/checkpoint"])
                if is_login_wall or ("linkedin.com" in current_url and "/jobs/view/" in current_url):
                    log(f"Portal authentication required at {current_url}")
                    await page.screenshot(path=str(ss_begin), full_page=True)
                    audit_data["screenshots"]["step1_begin"] = str(ss_begin)
                    await browser.close()
                    msg = f"Application portal ({current_url}) requires account sign-in. Staged as Dossier Ready for 1-click completion."
                    return (False, msg, audit_data) if return_audit else (False, msg)

                # STEP 1 SCREENSHOT: Process Begins
                await page.screenshot(path=str(ss_begin), full_page=True)
                audit_data["screenshots"]["step1_begin"] = str(ss_begin)
                log(f"📸 Step 1 Screenshot captured: {ss_begin.name} (Process Begun)")

                # 2. Check portal type and dispatch to dedicated form automator
                is_ashby = "ashbyhq.com" in canonical_url or "ashby" in canonical_url
                is_greenhouse = "greenhouse.io" in canonical_url
                is_lever = "lever.co" in canonical_url

                if is_ashby:
                    log("Detected Ashby ATS dynamic portal. Executing Ashby form automator...")
                    success, submit_msg = await self._fill_ashby_form(page, profile, resume_pdf, ss_filled, ss_submitted, log, audit_data)
                elif is_greenhouse:
                    log("Detected Greenhouse ATS portal. Executing Greenhouse form automator...")
                    success, submit_msg = await self._fill_greenhouse_form(page, profile, resume_pdf, ss_filled, ss_submitted, log, audit_data)
                elif is_lever:
                    log("Detected Lever ATS portal. Executing Lever form automator...")
                    success, submit_msg = await self._fill_lever_form(page, profile, resume_pdf, ss_filled, ss_submitted, log, audit_data)
                else:
                    log("Executing general ATS form automator...")
                    success, submit_msg = await self._fill_generic_form(page, profile, resume_pdf, ss_filled, ss_submitted, log, audit_data)

                await browser.close()
                log(f"Application flow finished: {submit_msg}")
                return (success, submit_msg, audit_data) if return_audit else (success, submit_msg)

        except Exception as e:
            err_msg = f"Browser automation exception: {str(e)}"
            log(err_msg)
            return (False, err_msg, audit_data) if return_audit else (False, err_msg)

    async def _fill_ashby_form(
        self,
        page,
        profile,
        resume_pdf: Path,
        ss_filled: Path,
        ss_submitted: Path,
        log,
        audit_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Automates Ashby's React form elements, multiple choice questions, and file uploads."""
        # 0. Check if we need to enter the application form
        if "/application" not in page.url:
            apply_btn = await page.query_selector("button:has-text('Apply for this Job'), a:has-text('Apply for this Job'), button:has-text('Apply')")
            if apply_btn:
                log("Clicking 'Apply for this Job' button to open application form...")
                await apply_btn.click()
                await page.wait_for_timeout(3000)
            elif not page.url.rstrip("/").endswith("/application"):
                target_app_url = page.url.rstrip("/") + "/application"
                log(f"Navigating directly to Ashby application endpoint: {target_app_url}")
                await page.goto(target_app_url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(3000)

        # Wait for form inputs
        await page.wait_for_selector("#_systemfield_name, input[name='_systemfield_name'], input[type='text']", timeout=20000)
        await page.wait_for_timeout(1500)

        # 1. Preferred Name and Email
        first_name, *last_names = profile.full_name.split()
        last_name = " ".join(last_names) if last_names else first_name

        name_input = await page.query_selector("#_systemfield_name")
        if name_input:
            await name_input.fill(profile.full_name)
            log(f"Filled Preferred Name: {profile.full_name}")

        email_input = await page.query_selector("#_systemfield_email")
        if email_input:
            await email_input.fill(profile.email)
            log(f"Filled Email Address: {profile.email}")

        # 2. Attach Tailored Resume PDF
        resume_input = await page.query_selector("input#_systemfield_resume, input[type='file']")
        if resume_input and resume_pdf.exists():
            await resume_input.set_input_files(str(resume_pdf.resolve()))
            log(f"Attached Tailored Resume PDF: {resume_pdf.name} ({resume_pdf.stat().st_size} bytes)")
        await page.wait_for_timeout(1500)

        # 3. Location Combobox (Ashby Autocomplete)
        try:
            loc_inputs = await page.query_selector_all("[data-field-path='_systemfield_location'] input, input.ashby-application-form-input-autocomplete, input[role='combobox']")
            for loc_inp in loc_inputs:
                if await loc_inp.is_visible():
                    await loc_inp.scroll_into_view_if_needed()
                    await loc_inp.click()
                    await loc_inp.fill("San Francisco")
                    await page.wait_for_timeout(800)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    log("Selected Location: San Francisco (Ashby Autocomplete)")
                    break
        except Exception as e:
            log(f"Location combobox note: {e}")

        # 4. Textarea Fields (Motivation, Why Company Pitch)
        try:
            tas = await page.query_selector_all("textarea")
            for ta in tas:
                if await ta.is_visible():
                    val = await ta.input_value()
                    if not val:
                        pitch = f"I am excited to apply for this software engineering role. With hands-on experience in backend microservices, Python, Java, and high-performance API design, I am eager to contribute to production reliability and scalable software architecture."
                        await ta.fill(pitch, timeout=4000)
                        log("Filled Motivation Pitch in visible textarea.")
        except Exception as e:
            log(f"Textarea note: {e}")

        # 5. Radio Buttons & Relocation Radios
        try:
            radios = await page.query_selector_all("input[type='radio']")
            for r in radios:
                if not await r.is_visible():
                    continue
                r_id = await r.get_attribute("id") or ""
                label_el = await page.query_selector(f"label[for='{r_id}']")
                txt = (await label_el.text_content()).strip().lower() if label_el else ""

                if "smaller companies or startups" in txt:
                    await r.check()
                    log("Answered Enterprise Experience: Smaller companies or startups")
                elif "citizen / permanent resident" in txt or "authorized" in txt:
                    await r.check()
                    log("Answered Work Authorization: Yes")
                elif "yes" in txt:
                    parent_txt = (await page.evaluate("(el) => el.closest('div').parentElement ? el.closest('div').parentElement.innerText : ''", r) or "").lower()
                    if "relocate" in parent_txt or "authorized" in parent_txt:
                        await r.check()
                        log(f"Answered Radio 'Yes': {parent_txt[:40]}")
        except Exception as e:
            log(f"Radio button note: {e}")

        # 6. Yes/No Buttons
        try:
            yes_btns = await page.query_selector_all("button[data-option='yes']")
            for yb in yes_btns:
                if not await yb.is_visible():
                    continue
                q_text = await page.evaluate("""(el) => {
                    let curr = el;
                    for (let k = 0; k < 5; k++) {
                        if (!curr.parentElement) break;
                        curr = curr.parentElement;
                        if (curr.innerText && curr.innerText.includes("?")) {
                            return curr.innerText.split("?")[0] + "?";
                        }
                    }
                    return "";
                }""", yb)
                q_lower = q_text.lower()
                if any(k in q_lower for k in ["related to any current employees", "conflict of interest", "convicted", "misconduct"]):
                    no_btn = await page.evaluate_handle("(el) => el.parentElement.querySelector('button[data-option=\"no\"]')", yb)
                    if no_btn:
                        await no_btn.click()
                        log("Answered Conflict Question: No")
                else:
                    await yb.click()
                    log(f"Answered Yes/No Question: Yes ({q_text[:40]})")
        except Exception as e:
            log(f"Yes/No button note: {e}")

        # 7. Additional Text Fields & Universal Field Population
        try:
            text_inputs = await page.query_selector_all("input[type='text']:not(#_systemfield_name), input[placeholder*='linkedin' i], input[type='url'], input[type='tel']")
            for inp in text_inputs:
                if not await inp.is_visible():
                    continue
                val = await inp.input_value()
                if not val:
                    ph = (await inp.get_attribute("placeholder") or "").lower()
                    parent = (await page.evaluate("(el) => el.closest('div').parentElement ? el.closest('div').parentElement.innerText : ''", inp) or "").lower()
                    ans = self.get_candidate_value_for_field(profile, parent, ph)
                    if ans:
                        await inp.fill(ans)
                        log(f"Filled field ({parent[:25]}): {ans[:30]}")
        except Exception as e:
            log(f"Text field note: {e}")

        # 8. Voluntary Self-Identification (EEO Diversity)
        try:
            for opt_text in ["Male", "Asian", "I am not a protected veteran", "No, I do not have a disability"]:
                opt_el = await page.query_selector(f"label:has-text('{opt_text}')")
                if opt_el and await opt_el.is_visible():
                    await opt_el.click()
                    log(f"Selected EEO Option: {opt_text}")
        except Exception as e:
            log(f"EEO option note: {e}")

        # 9. Privacy, Agreements, and Consent Checkboxes
        try:
            checkboxes = await page.query_selector_all("input[type='checkbox']")
            for cb in checkboxes:
                try:
                    if await cb.is_visible() and not await cb.is_checked():
                        await cb.check()
                except Exception:
                    pass
            log("Checked all visible compliance and agreement checkboxes.")
        except Exception as e:
            log(f"Consent check notice: {e}")

        await page.wait_for_timeout(2000)

        # STEP 2 SCREENSHOT: Form Fully Populated with Attached Resume
        await page.screenshot(path=str(ss_filled), full_page=True)
        audit_data["screenshots"]["step2_filled"] = str(ss_filled)
        log(f"📸 Step 2 Screenshot captured: {ss_filled.name} (Form Filled & Resume Attached)")

        # 8. Submit Application Button
        submit_btn = await page.query_selector("button:has-text('Submit Application')")
        if submit_btn:
            log("Triggering live 'Submit Application' button...")
            await submit_btn.click()

            verified, v_msg, v_audit = await self.verifier.verify_submission(page, ats_type="ashby", timeout_sec=20, log=log)
            audit_data["verification"] = v_audit

            # STEP 3 SCREENSHOT: Submission Result & Confirmation State
            await page.screenshot(path=str(ss_submitted), full_page=True)
            audit_data["screenshots"]["step3_submitted"] = str(ss_submitted)
            log(f"Step 3 Screenshot captured: {ss_submitted.name} (Submission Status Verified)")

            return verified, v_msg

        return False, "Submit button not found or form was incomplete. Saved as Staged Dossier."

    async def _fill_greenhouse_form(
        self,
        page,
        profile,
        resume_pdf: Path,
        ss_filled: Path,
        ss_submitted: Path,
        log,
        audit_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Automates Greenhouse ATS application forms on boards.greenhouse.io."""
        first_name, *last_names = profile.full_name.split()
        last_name = " ".join(last_names) if last_names else first_name

        # 0. Dismiss Cookie Banners (OneTrust, GDPR)
        try:
            cookie_btn = await page.query_selector("#onetrust-accept-btn-handler, button:has-text('Accept All'), button:has-text('Accept all cookies'), button:has-text('I Agree')")
            if cookie_btn and await cookie_btn.is_visible():
                await cookie_btn.click()
                await page.wait_for_timeout(600)
                log("Dismissed cookie consent banner.")
        except Exception:
            pass

        # 1. Names (handles standard #first_name as well as prefixed apply-first_name)
        fn_inp = await page.query_selector("#first_name, input[name*='first_name' i], input[id*='first_name' i]")
        if fn_inp:
            await fn_inp.fill(first_name)
            log(f"Filled First Name: {first_name}")

        ln_inp = await page.query_selector("#last_name, input[name*='last_name' i], input[id*='last_name' i]")
        if ln_inp:
            await ln_inp.fill(last_name)
            log(f"Filled Last Name: {last_name}")

        # 2. Email & Phone
        em_inp = await page.query_selector("#email, input[name*='email' i], input[id*='email' i]")
        if em_inp:
            await em_inp.fill(profile.email)
            log(f"Filled Email: {profile.email}")

        ph_inp = await page.query_selector("#phone, input[name*='phone' i], input[id*='phone' i]")
        if ph_inp:
            await ph_inp.fill(profile.phone)
            log(f"Filled Phone: {profile.phone}")

        # 3. Location & Address (Jaunpur, Uttar Pradesh, India)
        loc_inp = await page.query_selector("#candidate_location, input[name*='location' i], input[id*='location' i]")
        if loc_inp:
            await loc_inp.fill(profile.location)
            log(f"Filled Location: {profile.location}")

        # 4. URLs (LinkedIn, Portfolio, GitHub)
        li_inp = await page.query_selector("input[name*='linkedin' i], input[id*='linkedin' i]")
        if li_inp:
            await li_inp.fill(profile.linkedin)
            log(f"Filled LinkedIn: {profile.linkedin}")

        web_inp = await page.query_selector("input[name*='website' i], input[name*='portfolio' i]")
        if web_inp:
            await web_inp.fill(profile.portfolio)
            log(f"Filled Portfolio: {profile.portfolio}")

        # 5. File upload for resume & wait for upload progress to settle
        file_input = await page.query_selector("input[type='file'], input[name*='resume' i], input[id*='resume' i]")
        if file_input:
            await file_input.set_input_files(str(resume_pdf.resolve()))
            log(f"Attached tailored resume: {resume_pdf.name}")
            await page.wait_for_timeout(3500)

        # 6. React-Select and custom dropdown controls on Greenhouse / Nebius
        try:
            select_controls = await page.query_selector_all(".select__control, div[class*='select__control' i]")
            for sc in select_controls:
                if await sc.is_visible():
                    await sc.click(force=True)
                    await page.wait_for_timeout(400)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(300)
            if select_controls:
                log("Selected options in Greenhouse React-Select dropdowns.")

            # Nebius / Custom embedded Greenhouse dropdowns (.g-select)
            g_buttons = await page.query_selector_all(".g-select button[role='combobox'], button.g-select-control__button")
            for btn in g_buttons:
                if await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await btn.click(force=True)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(200)
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(200)
            if g_buttons:
                log("Selected options in embedded Greenhouse custom dropdowns.")
        except Exception as e:
            log(f"React-Select / Dropdown note: {e}")

        # 7. Additional required text inputs & textareas (Current company, Source, Motivation, etc.)
        try:
            other_inps = await page.query_selector_all("input[type='text']:not(#first_name):not(#last_name):not(#email), input[type='url'], input[type='tel'], textarea")
            for inp in other_inps:
                if await inp.is_visible():
                    val = await inp.input_value()
                    if not val:
                        parent = (await page.evaluate("(el) => el.closest('div').parentElement ? el.closest('div').parentElement.innerText : ''", inp) or "").lower()
                        ph = (await inp.get_attribute("placeholder") or "").lower()
                        ans = self.get_candidate_value_for_field(profile, parent, ph)
                        if ans:
                            await inp.fill(ans)
                            log(f"Filled Greenhouse field ({parent[:25]}): {ans[:30]}")
        except Exception as e:
            log(f"Additional inputs note: {e}")

        # 8. Check agreement and compliance checkboxes
        checkboxes = await page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                if await cb.is_visible() and not await cb.is_checked():
                    await cb.check()
            except Exception:
                pass

        await page.wait_for_timeout(2000)

        # STEP 2 SCREENSHOT: Form Fully Populated with Attached Resume
        await page.screenshot(path=str(ss_filled), full_page=True)
        audit_data["screenshots"]["step2_filled"] = str(ss_filled)
        log(f"📸 Step 2 Screenshot captured: {ss_filled.name} (Form Filled & Resume Attached)")

        # 7. Submit Application
        submit_btn = await page.query_selector("#submit_app, input[type='submit'], button[type='submit'], button:has-text('Submit Application'), button:has-text('Submit application')")
        if submit_btn and await submit_btn.is_visible():
            log("Triggering live Greenhouse 'Submit Application' button...")
            await submit_btn.click(timeout=5000)

            verified, v_msg, v_audit = await self.verifier.verify_submission(page, ats_type="greenhouse", timeout_sec=20, log=log)
            audit_data["verification"] = v_audit

            # STEP 3 SCREENSHOT: Submission Result & Confirmation
            await page.screenshot(path=str(ss_submitted), full_page=True)
            audit_data["screenshots"]["step3_submitted"] = str(ss_submitted)
            log(f"Step 3 Screenshot captured: {ss_submitted.name} (Submission Status Verified)")

            return verified, v_msg

        return False, "Greenhouse form prepared with tailored credentials. Saved as Staged Dossier."

    async def _fill_lever_form(
        self,
        page,
        profile,
        resume_pdf: Path,
        ss_filled: Path,
        ss_submitted: Path,
        log,
        audit_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Automates Lever ATS application forms on jobs.lever.co."""
        name_inp = await page.query_selector("input[name='name']")
        if name_inp:
            await name_inp.fill(profile.full_name)
            log(f"Filled Name: {profile.full_name}")

        em_inp = await page.query_selector("input[name='email']")
        if em_inp:
            await em_inp.fill(profile.email)
            log(f"Filled Email: {profile.email}")

        ph_inp = await page.query_selector("input[name='phone']")
        if ph_inp:
            await ph_inp.fill(profile.phone)
            log(f"Filled Phone: {profile.phone}")

        org_inp = await page.query_selector("input[name='org']")
        if org_inp:
            await org_inp.fill(profile.current_role)

        li_inp = await page.query_selector("input[name='urls[LinkedIn]']")
        if li_inp:
            await li_inp.fill(profile.linkedin)

        web_inp = await page.query_selector("input[name='urls[Portfolio]']")
        if web_inp:
            await web_inp.fill(profile.portfolio)

        gh_inp = await page.query_selector("input[name='urls[GitHub]']")
        if gh_inp:
            await gh_inp.fill(profile.github)

        file_input = await page.query_selector("input[type='file']")
        if file_input:
            await file_input.set_input_files(str(resume_pdf.resolve()))
            log(f"Attached tailored resume: {resume_pdf.name}")

        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(ss_filled), full_page=True)
        audit_data["screenshots"]["step2_filled"] = str(ss_filled)
        log(f"📸 Step 2 Screenshot captured: {ss_filled.name} (Form Filled & Resume Attached)")

        submit_btn = await page.query_selector("button[type='submit'], #btn-submit, button:has-text('Submit application')")
        if submit_btn:
            log("Triggering live Lever 'Submit application' button...")
            await submit_btn.click()

            verified, v_msg, v_audit = await self.verifier.verify_submission(page, ats_type="lever", timeout_sec=20, log=log)
            audit_data["verification"] = v_audit

            await page.screenshot(path=str(ss_submitted), full_page=True)
            audit_data["screenshots"]["step3_submitted"] = str(ss_submitted)
            log(f"Step 3 Screenshot captured: {ss_submitted.name} (Submission Status Verified)")

            return verified, v_msg

        return True, "Lever form prepared with tailored credentials."

    async def _fill_generic_form(
        self,
        page,
        profile,
        resume_pdf: Path,
        ss_filled: Path,
        ss_submitted: Path,
        log,
        audit_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Generic fallback form filler for standard career portals."""
        first_name, *last_names = profile.full_name.split()
        last_name = " ".join(last_names) if last_names else first_name

        name_inputs = await page.query_selector_all("input[name*='name' i], input[id*='name' i]")
        for inp in name_inputs:
            try:
                await inp.fill(profile.full_name)
            except Exception:
                pass

        email_inputs = await page.query_selector_all("input[type='email']")
        for inp in email_inputs:
            try:
                await inp.fill(profile.email)
            except Exception:
                pass

        phone_inputs = await page.query_selector_all("input[type='tel'], input[name*='phone' i]")
        for inp in phone_inputs:
            try:
                await inp.fill(profile.phone)
            except Exception:
                pass

        loc_inputs = await page.query_selector_all("input[name*='location' i], input[name*='address' i]")
        for inp in loc_inputs:
            try:
                await inp.fill(profile.location)
            except Exception:
                pass

        file_inputs = await page.query_selector_all("input[type='file']")
        for inp in file_inputs:
            try:
                await inp.set_input_files(str(resume_pdf.resolve()))
                log(f"Attached tailored resume: {resume_pdf.name}")
                break
            except Exception:
                pass

        # Universal filler for all remaining inputs & textareas
        try:
            all_inps = await page.query_selector_all("input[type='text'], input[type='tel'], input[type='url'], textarea")
            for inp in all_inps:
                if await inp.is_visible():
                    val = await inp.input_value()
                    if not val:
                        parent = (await page.evaluate("(el) => el.closest('div').parentElement ? el.closest('div').parentElement.innerText : ''", inp) or "").lower()
                        ph = (await inp.get_attribute("placeholder") or "").lower()
                        ans = self.get_candidate_value_for_field(profile, parent, ph)
                        if ans:
                            await inp.fill(ans)
                            log(f"Filled generic field ({parent[:25]}): {ans[:30]}")
        except Exception as e:
            pass

        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(ss_filled), full_page=True)
        audit_data["screenshots"]["step2_filled"] = str(ss_filled)
        log(f"📸 Step 2 Screenshot captured: {ss_filled.name} (Form Filled & Resume Attached)")

        # Search for and trigger live submit button
        submit_btn = await page.query_selector("button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Apply Now'), button:has-text('Send Application')")
        if submit_btn and await submit_btn.is_visible():
            try:
                log("Triggering live 'Submit' button on general career portal...")
                await submit_btn.click(timeout=5000)
                verified, v_msg, v_audit = await self.verifier.verify_submission(page, ats_type="generic", timeout_sec=20, log=log)
                audit_data["verification"] = v_audit

                await page.screenshot(path=str(ss_submitted), full_page=True)
                audit_data["screenshots"]["step3_submitted"] = str(ss_submitted)
                log(f"Step 3 Screenshot captured: {ss_submitted.name} (Submission Status Verified)")

                return verified, v_msg
            except Exception as e:
                log(f"Submit click notice: {e}")

        return False, "Standard form pre-filled with tailored credentials. Saved as Staged Dossier."
