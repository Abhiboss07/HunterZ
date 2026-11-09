import pytest
from unittest.mock import AsyncMock, MagicMock
from hunterz.config import load_config
from hunterz.applier.browser_applier import BrowserApplier


@pytest.mark.asyncio
async def test_set_react_input_dispatches_synthetic_events():
    config = load_config()
    applier = BrowserApplier(config)
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock()
    mock_el = MagicMock()
    mock_el.fill = AsyncMock()

    await applier.set_react_input(mock_page, mock_el, "Test Value")
    mock_el.fill.assert_awaited_once_with("Test Value")
    mock_page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_aria_combobox_traversal():
    config = load_config()
    applier = BrowserApplier(config)
    mock_page = MagicMock()
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    mock_cb = MagicMock()
    mock_cb.is_visible = AsyncMock(return_value=True)
    mock_cb.scroll_into_view_if_needed = AsyncMock()
    mock_cb.click = AsyncMock()
    mock_cb.fill = AsyncMock()

    res = await applier.handle_aria_combobox(mock_page, mock_cb, "India")
    assert res is True
    mock_cb.click.assert_awaited_once()
    mock_cb.fill.assert_awaited_once_with("India")
