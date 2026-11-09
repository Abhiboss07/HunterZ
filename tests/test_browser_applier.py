import os
import socket
import threading
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone
import uvicorn
from hunterz.config import load_config
from hunterz.db.models import JobModel
from hunterz.applier.browser_applier import BrowserApplier
from tests.mock_ats_server import mock_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_server_port():
    port = find_free_port()
    config = uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait for server to bind
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except (OSError, ConnectionRefusedError):
            time.sleep(0.05)
    yield port


@pytest.fixture
def dummy_resume_pdf(tmp_path):
    pdf = tmp_path / "Abhishek_Yadav_Resume.pdf"
    # Minimal valid 1-page PDF header/trailer
    pdf_content = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n"
        b"0000000117 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n188\n%%EOF\n"
    )
    pdf.write_bytes(pdf_content)
    return pdf


@pytest.mark.asyncio
async def test_greenhouse_browser_application_flow(mock_server_port, dummy_resume_pdf):
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_gh_101",
        title="Software Engineer",
        company="MockAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/greenhouse/acme/jobs/101",
        source="greenhouse",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is True
    assert "confirmation" in msg.lower() or "submitted" in msg.lower()
    assert "step1_begin" in audit["screenshots"]
    assert "step2_filled" in audit["screenshots"]
    assert "step3_submitted" in audit["screenshots"]


@pytest.mark.asyncio
async def test_lever_browser_application_flow(mock_server_port, dummy_resume_pdf):
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_lever_202",
        title="Backend Engineer",
        company="MockLeverAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/lever/acme/202",
        source="lever",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is True
    assert "confirmation" in msg.lower() or "submitted" in msg.lower()
    assert "step3_submitted" in audit["screenshots"]


@pytest.mark.asyncio
async def test_ashby_browser_application_flow(mock_server_port, dummy_resume_pdf):
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_ashby_303",
        title="Software Engineer",
        company="MockAshbyAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/ashby/acme/job/303",
        source="ashby",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is True
    assert "confirmation" in msg.lower() or "submitted" in msg.lower()
    assert "step3_submitted" in audit["screenshots"]


@pytest.mark.asyncio
async def test_slow_submission_resilience_20s_polling(mock_server_port, dummy_resume_pdf):
    """Verifies that slow ATS processing (taking 7 seconds) is verified by our 20s polling verifier."""
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_slow_404",
        title="Software Engineer",
        company="MockSlowAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/mock/slow-submit",
        source="generic",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is True
    assert "submitted" in msg.lower() or "confirmed" in msg.lower()


@pytest.mark.asyncio
async def test_validation_error_immediate_detection(mock_server_port, dummy_resume_pdf):
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_val_505",
        title="Software Engineer",
        company="MockValAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/mock/validation-error",
        source="generic",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is False
    assert "validation" in msg.lower() or "phone number" in msg.lower()


@pytest.mark.asyncio
async def test_captcha_staging_without_crash(mock_server_port, dummy_resume_pdf):
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    job = JobModel(
        external_id="mock_cap_606",
        title="Software Engineer",
        company="MockCapAcme",
        location="Remote",
        url=f"http://127.0.0.1:{mock_server_port}/mock/captcha",
        source="generic",
        posted_at=datetime.now(timezone.utc)
    )

    success, msg, audit = await applier.apply(job, dummy_resume_pdf, return_audit=True)
    assert success is False
    assert "verification challenge" in msg.lower() or "recaptcha" in msg.lower()
    assert "step2_captcha_challenge" in audit["screenshots"]


@pytest.mark.asyncio
async def test_multi_step_form_navigation(mock_server_port):
    """Tests that navigate_multi_step_flow steps through wizard forms."""
    from playwright.async_api import async_playwright

    config = load_config()
    applier = BrowserApplier(config)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"http://127.0.0.1:{mock_server_port}/mock/multi-step")

        # Step 1 to Step 2
        stepped1 = await applier.navigate_multi_step_flow(page)
        assert stepped1 is True
        assert await page.is_visible("#step2")

        # Step 2 to Step 3
        stepped2 = await applier.navigate_multi_step_flow(page)
        assert stepped2 is True
        assert await page.is_visible("#step3")

        await browser.close()


@pytest.mark.asyncio
async def test_screening_question_integration_in_browser(mock_server_port, dummy_resume_pdf):
    """Verifies that custom screening questions are dynamically answered via the screening engine."""
    config = load_config()
    config.apply.dry_run = False
    applier = BrowserApplier(config)

    # Pre-seed cache with a specific answer
    applier.screening_engine._cache["preferred_work_arrangement"] = "100% Remote"

    ans = await applier.get_candidate_value_async(config.profile, "Preferred Work Arrangement")
    assert ans == "100% Remote"

    # Rule test: Years of Python experience
    yoe = await applier.get_candidate_value_async(config.profile, "How many years of Python experience do you have?")
    assert yoe in ["1", "2"]

