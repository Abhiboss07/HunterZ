import time
from typing import Any, Callable, Dict, Optional, Tuple


class SubmissionVerifier:
    """Verifies job application submissions using polling, URL evaluation,

    positive confirmation detection, and immediate validation error checks.
    """

    CONFIRMATION_PATTERNS = [
        "thank you",
        "application submitted",
        "received your application",
        "we have received your application",
        "your application was successfully submitted",
        "we'll contact you if there are next steps",
        "thanks for applying",
        "application received",
        "submission successful",
        "applied successfully",
    ]

    CONFIRMATION_URL_SUBSTRINGS = [
        "/confirmation",
        "/thanks",
        "/thank-you",
        "/thank_you",
        "application_received",
    ]

    AGGREGATOR_DOMAINS = [
        "jobicy.com",
        "arbeitnow.com",
        "arbeitnow.fr",
        "arbeitnow.de",
        "arbeitnow.nl",
        "arbeitnow.ch",
        "arbeitnow.co.uk",
        "remoteok.com",
        "weworkremotely.com",
        "linkedin.com",
        "news.ycombinator.com",
        "wellfound.com",
    ]

    CONFIRMATION_SELECTORS = [
        "#application_confirmation",
        ".ashby-application-submitted-page",
        ".lever-confirmation",
        "[data-qa='application-success']",
        "div[class*='confirmation' i]",
        "div[class*='submitted' i]",
    ]

    ERROR_SELECTORS = [
        ".artdeco-inline-feedback--error",
        "[aria-invalid='true']",
        "[aria-describedby*='error']",
        ".select__control--is-invalid",
        "div[class*='error' i]",
        "span[class*='error' i]",
        "p[class*='error' i]",
        ".ashby-form-error",
        ".field-error",
        ".has-error",
    ]

    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='challenges.cloudflare.com']",
        "[id*='recaptcha']",
        "[class*='captcha']",
        "div.g-recaptcha",
        "div.turnstile",
    ]

    async def verify_submission(
        self,
        page: Any,
        ats_type: str = "generic",
        timeout_sec: int = 20,
        poll_interval_sec: float = 1.0,
        log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Polls the page after submission click up to timeout_sec to verify confirmation or detect errors."""
        start_time = time.monotonic()
        audit_info: Dict[str, Any] = {
            "ats_type": ats_type,
            "timeout_sec": timeout_sec,
            "verification_duration_sec": 0.0,
            "confirmed_by": None,
        }

        while (time.monotonic() - start_time) < timeout_sec:
            current_url = getattr(page, "url", "").lower()

            # Prevent false-positive confirmation on aggregator websites (Jobicy, Arbeitnow, etc.)
            is_aggregator = any(d in current_url for d in self.AGGREGATOR_DOMAINS)

            # 1. URL pattern check (Must not be an aggregator)
            if not is_aggregator:
                for url_token in self.CONFIRMATION_URL_SUBSTRINGS:
                    if url_token in current_url:
                        audit_info["confirmed_by"] = f"url_token:{url_token}"
                        audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                        msg = f"Application submitted directly to {ats_type.capitalize()}! Confirmation recorded."
                        if log:
                            log(f"[SUCCESS] {msg} (URL confirmed: {current_url})")
                        return True, msg, audit_info

            # 2. Dedicated confirmation element check (High precision)
            if not is_aggregator:
                for selector in self.CONFIRMATION_SELECTORS:
                    try:
                        conf_el = await page.query_selector(selector)
                        if conf_el and await conf_el.is_visible():
                            audit_info["confirmed_by"] = f"selector:{selector}"
                            audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                            msg = f"Application submitted directly to {ats_type.capitalize()}! Confirmation recorded."
                            if log:
                                log(f"[SUCCESS] {msg} (Visible confirmation element: {selector})")
                            return True, msg, audit_info
                    except Exception:
                        pass

            # 3. Headings / Title Confirmation Check (Avoids matching random footers)
            if not is_aggregator:
                try:
                    headings = await page.query_selector_all("h1, h2, h3, [role='heading'], .title, div[class*='confirm' i], div[class*='success' i]")
                    for h in headings:
                        if await h.is_visible():
                            h_text = (await h.inner_text()).lower().strip()
                            for pattern in self.CONFIRMATION_PATTERNS:
                                if pattern in h_text:
                                    audit_info["confirmed_by"] = f"heading:{pattern}"
                                    audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                                    msg = f"Application submitted directly to {ats_type.capitalize()}! Confirmation recorded."
                                    if log:
                                        log(f"[SUCCESS] {msg} (Matched heading: '{h_text[:60]}')")
                                    return True, msg, audit_info
                except Exception:
                    pass

            # 4. Ashby specific URL shift
            if ats_type.lower() == "ashby" and "ashbyhq.com" in current_url and "/application" not in current_url:
                audit_info["confirmed_by"] = "ashby_url_shift"
                audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                msg = "Application form submitted directly to Ashby! Confirmation recorded."
                if log:
                    log(f"[SUCCESS] {msg} (Application path completed)")
                return True, msg, audit_info

            # 5. Immediate Validation Error Detection
            for err_selector in self.ERROR_SELECTORS:
                try:
                    err_el = await page.query_selector(err_selector)
                    if err_el and await err_el.is_visible():
                        err_text = (await err_el.inner_text()).strip()
                        if err_text:
                            audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                            msg = f"Form validation required: {err_text[:100]}"
                            if log:
                                log(f"[VALIDATION] {msg}")
                            return False, msg, audit_info
                except Exception:
                    pass

            # 6. CAPTCHA Detection
            for cap_selector in self.CAPTCHA_SELECTORS:
                try:
                    cap_el = await page.query_selector(cap_selector)
                    if cap_el and await cap_el.is_visible():
                        audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                        msg = "Application form populated with tailored resume. Verification challenge detected."
                        if log:
                            log(f"[SECURITY] {msg}")
                        return False, msg, audit_info
                except Exception:
                    pass

            # Also check text-based challenge via locator if available
            try:
                if hasattr(page, "locator"):
                    challenge_loc = page.locator("text='verification challenge'")
                    if await challenge_loc.count() > 0 and await challenge_loc.first.is_visible():
                        audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
                        msg = "Application form populated with tailored resume. Verification challenge detected."
                        if log:
                            log(f"[SECURITY] {msg}")
                        return False, msg, audit_info
            except Exception:
                pass

            await page.wait_for_timeout(int(poll_interval_sec * 1000))

        audit_info["verification_duration_sec"] = round(time.monotonic() - start_time, 2)
        msg = f"{ats_type.capitalize()} form submitted but awaiting confirmation screen. Staged for review."
        if log:
            log(f"[TIMEOUT] {msg}")
        return False, msg, audit_info
