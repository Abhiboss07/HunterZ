import pytest
from unittest.mock import AsyncMock, MagicMock
from hunterz.applier.verifier import SubmissionVerifier


@pytest.mark.asyncio
async def test_verifier_detects_confirmation_text():
    verifier = SubmissionVerifier()
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/acme/jobs/123/confirmation"
    mock_page.text_content = AsyncMock(return_value="Thank you for applying to Acme!")
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    success, msg, audit = await verifier.verify_submission(mock_page, ats_type="greenhouse", timeout_sec=2)
    assert success is True
    assert "confirmation" in msg.lower() or "thank you" in msg.lower()


@pytest.mark.asyncio
async def test_verifier_detects_validation_error_immediately():
    verifier = SubmissionVerifier()
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/acme/jobs/123"
    mock_page.text_content = AsyncMock(return_value="Application Form")

    mock_err_el = MagicMock()
    mock_err_el.is_visible = AsyncMock(return_value=True)
    mock_err_el.inner_text = AsyncMock(return_value="Please enter a valid email address")

    async def mock_query_selector(selector):
        if "error" in selector.lower():
            return mock_err_el
        return None

    mock_page.query_selector = AsyncMock(side_effect=mock_query_selector)
    mock_page.wait_for_timeout = AsyncMock()

    success, msg, audit = await verifier.verify_submission(mock_page, ats_type="greenhouse", timeout_sec=5)
    assert success is False
    assert "validation" in msg.lower()
    assert "email address" in msg.lower()


@pytest.mark.asyncio
async def test_verifier_times_out_gracefully():
    verifier = SubmissionVerifier()
    mock_page = MagicMock()
    mock_page.url = "https://boards.greenhouse.io/acme/jobs/123"
    mock_page.text_content = AsyncMock(return_value="Still loading form...")
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock()

    success, msg, audit = await verifier.verify_submission(mock_page, ats_type="generic", timeout_sec=1, poll_interval_sec=0.2)
    assert success is False
    assert "awaiting confirmation" in msg.lower() or "staged" in msg.lower()
