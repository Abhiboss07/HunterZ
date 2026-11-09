import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from datetime import datetime, timezone
from hunterz.config import load_config
from hunterz.db.models import JobModel
from hunterz.applier.dispatcher import ApplicationDispatcher


@pytest.mark.asyncio
async def test_dispatcher_escalates_to_browser_on_direct_ats_failure():
    config = load_config()
    dispatcher = ApplicationDispatcher(config)

    # Mock direct applier returning failure (e.g. 404 or custom question error)
    dispatcher.direct_applier.apply = AsyncMock(return_value=(False, "Greenhouse 404: Job not found"))
    # Mock browser applier returning success
    dispatcher.browser_applier.resolve_canonical_url = AsyncMock(return_value="https://boards.greenhouse.io/acme/jobs/123")
    dispatcher.browser_applier.apply = AsyncMock(return_value=(True, "Application submitted via Browser", {"screenshots": {}}))

    job = JobModel(
        external_id="greenhouse_acme_123",
        title="Software Engineer",
        company="Acme",
        location="Remote",
        url="https://boards.greenhouse.io/acme/jobs/123",
        source="greenhouse",
        posted_at=datetime.now(timezone.utc)
    )
    dummy_pdf = Path("/tmp/dummy.pdf")
    dummy_tex = Path("/tmp/dummy.tex")

    success, status, method, msg, audit = await dispatcher.apply_job(job, dummy_pdf, dummy_tex)

    assert success is True
    assert status == "SUBMITTED"
    assert method == "BROWSER_AUTOMATED"
    dispatcher.direct_applier.apply.assert_awaited_once()
    dispatcher.browser_applier.apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_uses_direct_rest_when_successful():
    config = load_config()
    dispatcher = ApplicationDispatcher(config)

    dispatcher.direct_applier.apply = AsyncMock(return_value=(True, "Direct REST application submitted successfully!"))
    dispatcher.browser_applier.resolve_canonical_url = AsyncMock(return_value="https://boards.greenhouse.io/acme/jobs/123")
    dispatcher.browser_applier.apply = AsyncMock()

    job = JobModel(
        external_id="greenhouse_acme_123",
        title="Software Engineer",
        company="Acme",
        location="Remote",
        url="https://boards.greenhouse.io/acme/jobs/123",
        source="greenhouse",
        posted_at=datetime.now(timezone.utc)
    )
    dummy_pdf = Path("/tmp/dummy.pdf")
    dummy_tex = Path("/tmp/dummy.tex")

    success, status, method, msg, audit = await dispatcher.apply_job(job, dummy_pdf, dummy_tex)

    assert success is True
    assert status == "SUBMITTED"
    assert method == "DIRECT_REST"
    dispatcher.direct_applier.apply.assert_awaited_once()
    dispatcher.browser_applier.apply.assert_not_awaited()
