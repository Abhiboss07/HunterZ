import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


class CaptchaHandler:
    """Detects, handles, and stages CAPTCHA and anti-bot verification challenges

    such as Google reCAPTCHA, Cloudflare Turnstile, and hCaptcha without crashing.
    """

    CAPTCHA_DEFINITIONS = [
        ("recaptcha", ["iframe[src*='recaptcha']", "[id*='recaptcha']", "div.g-recaptcha"]),
        ("turnstile", ["iframe[src*='challenges.cloudflare.com']", "div.turnstile", "[name='cf-turnstile-response']"]),
        ("hcaptcha", ["iframe[src*='hcaptcha']", "div.h-captcha", "[name='h-captcha-response']"]),
        ("generic", ["[class*='captcha']"]),
    ]

    async def detect_captcha(self, page: Any) -> Optional[Dict[str, Any]]:
        """Scans page for visible CAPTCHA elements using valid CSS selectors and locators."""
        for c_type, selectors in self.CAPTCHA_DEFINITIONS:
            for selector in selectors:
                try:
                    el = await page.query_selector(selector)
                    if el and await el.is_visible():
                        return {"type": c_type, "selector": selector}
                except Exception:
                    pass

        # Text-based verification locator
        try:
            if hasattr(page, "locator"):
                loc = page.locator(":has-text('verification challenge')")
                if await loc.count() > 0 and await loc.first.is_visible():
                    return {"type": "verification_challenge", "selector": ":has-text('verification challenge')"}
        except Exception:
            pass

        return None

    async def attempt_passive_solve(self, page: Any, log: Optional[Callable[[str], None]] = None) -> bool:
        """Attempts passive resolution for checkbox-based challenges (Turnstile or reCAPTCHA v2)."""
        detected = await self.detect_captcha(page)
        if not detected:
            return True

        if log:
            log(f"[SECURITY] Attempting passive solve for {detected['type']}...")

        # For Turnstile: wait up to 5 seconds for automatic clearance token
        if detected["type"] == "turnstile":
            try:
                for _ in range(5):
                    await page.wait_for_timeout(1000)
                    token_el = await page.query_selector("[name='cf-turnstile-response']")
                    if token_el:
                        val = await token_el.input_value()
                        if val and len(val) > 10:
                            if log:
                                log("[SUCCESS] Cloudflare Turnstile clearance token acquired passively.")
                            return True
            except Exception:
                pass

        # For reCAPTCHA checkbox: attempt focus and humanized click if inside iframe
        if detected["type"] == "recaptcha":
            try:
                anchor_frame = None
                for frame in getattr(page, "frames", []):
                    if "recaptcha" in frame.url:
                        anchor_frame = frame
                        break

                if anchor_frame:
                    checkbox = await anchor_frame.query_selector("#recaptcha-anchor")
                    if checkbox and await checkbox.is_visible():
                        await checkbox.scroll_into_view_if_needed()
                        await checkbox.click()
                        await page.wait_for_timeout(3000)
                        # Check if solved
                        is_checked = await checkbox.get_attribute("aria-checked")
                        if is_checked == "true":
                            if log:
                                log("[SUCCESS] reCAPTCHA checkbox verified passively.")
                            return True
            except Exception:
                pass

        return False

    async def stage_handover(
        self,
        page: Any,
        ss_path: Path,
        audit_data: Dict[str, Any],
        log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Captures a verification challenge screenshot and stages the application for 1-click human completion."""
        ss_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(ss_path), full_page=True)
            audit_data["screenshots"]["step2_captcha_challenge"] = str(ss_path)
            if log:
                log(f"Verification screenshot captured: {ss_path.name}")
        except Exception as e:
            if log:
                log(f"Screenshot capture notice: {e}")

        msg = "Application form populated with tailored resume. Verification challenge detected."
        if log:
            log(f"[STAGED] {msg}")
        return False, msg
