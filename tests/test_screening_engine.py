import pytest
import json
from pathlib import Path
from hunterz.config import load_config
from hunterz.applier.screening_engine import ScreeningQuestionEngine


@pytest.fixture
def temp_cache_file(tmp_path):
    cache_path = tmp_path / "answers_cache.json"
    cache_data = {
        "preferred_work_arrangement": "Remote",
        "visa_status": "Citizen / Permanent Resident"
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f)
    return cache_path


@pytest.mark.asyncio
async def test_screening_engine_cache_hit(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    answer = await engine.get_answer("What is your preferred work arrangement?")
    assert answer == "Remote"


@pytest.mark.asyncio
async def test_screening_engine_no_zero_experience_rule(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    # Question about Python experience must return at least 1, never 0
    answer = await engine.get_answer("How many years of Python experience do you have?")
    assert answer in ["1", "2", "3"]
    assert answer != "0"


@pytest.mark.asyncio
async def test_screening_engine_affirmative_authorization(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    answer = await engine.get_answer("Are you legally authorized to work in India?")
    assert answer == "Yes"


@pytest.mark.asyncio
async def test_screening_engine_conflict_of_interest_negative(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    answer = await engine.get_answer("Do you have any conflict of interest with our current clients?")
    assert answer == "No"


@pytest.mark.asyncio
async def test_screening_engine_normalizes_novel_question(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    key = engine.normalize_question("Please specify: How many years of experience do you have with FastAPI?")
    assert "fastapi" in key


@pytest.mark.asyncio
async def test_screening_engine_saves_new_answers(temp_cache_file):
    config = load_config()
    engine = ScreeningQuestionEngine(config.profile, cache_file=temp_cache_file)
    answer = await engine.get_answer("Do you have experience leading open source initiatives?")
    assert answer is not None
    # Verify cached on disk
    with open(temp_cache_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert any("open source" in k or "initiatives" in k for k in saved.keys())
