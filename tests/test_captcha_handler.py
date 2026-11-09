import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from hunterz.applier.captcha_handler import CaptchaHandler


@pytest.mark.asyncio
async def test_detect_captcha_with_valid_css_selectors():
    handler = CaptchaHandler()
    mock_page = MagicMock()

    mock_iframe = MagicMock()
    mock_iframe.is_visible = AsyncMock(return_value=True)

    async def mock_query(sel):
        if "recaptcha" in sel:
            return mock_iframe
        return None

    mock_page.query_selector = AsyncMock(side_effect=mock_query)

    result = await handler.detect_captcha(mock_page)
    assert result is not None
    assert result["type"] == "recaptcha"


@pytest.mark.asyncio
async def test_detect_captcha_returns_none_when_clean():
    handler = CaptchaHandler()
    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.locator = MagicMock()
    mock_page.locator.return_value.count = AsyncMock(return_value=0)

    result = await handler.detect_captcha(mock_page)
    assert result is None


@pytest.mark.asyncio
async def test_stage_handover_captures_screenshot_and_returns_prepared(tmp_path):
    handler = CaptchaHandler()
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()

    ss_path = tmp_path / "test_captcha_challenge.png"
    audit_data = {"screenshots": {}}

    success, msg = await handler.stage_handover(mock_page, ss_path, audit_data)
    assert success is False
    assert "verification challenge" in msg.lower()
    assert "step2_captcha_challenge" in audit_data["screenshots"]
    mock_page.screenshot.assert_awaited_once()
