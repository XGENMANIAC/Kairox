import pytest

from tradesight.api.settings import ApiSettings


def base_env():
    return {
        "nim_api_key": "nim", "tavily_api_key": "tav", "gemini_api_key": "gem",
    }


def test_defaults_and_required():
    s = ApiSettings(_env_file=None, **base_env())
    assert s.vision_model == "gemini-2.5-flash"
    assert s.reasoning_model == "moonshotai/kimi-k2.6"
    assert s.news_model == "meta/llama-3.3-70b-instruct"
    assert s.analyse_rate_limit == "10/minute"


def test_to_core_config_points_vision_at_gemini():
    s = ApiSettings(_env_file=None, **base_env())
    core = s.to_core_config()
    assert core.nim_api_key == "nim"
    assert core.tavily_api_key == "tav"
    assert core.vision_api_key == "gem"
    assert "generativelanguage.googleapis.com" in core.vision_base_url
    assert core.vision_on_separate_provider is True
    assert core.reasoning_model == "moonshotai/kimi-k2.6"


def test_missing_required_raises():
    with pytest.raises(Exception):
        ApiSettings(_env_file=None, nim_api_key="n", tavily_api_key="t")  # no GEMINI
