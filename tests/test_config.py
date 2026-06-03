import pytest
from tradesight.config import Config, ConfigError


def test_load_returns_config_with_required_keys():
    env = {"NIM_API_KEY": "nim123", "TAVILY_API_KEY": "tav456"}
    cfg = Config.load(env=env)
    assert cfg.nim_api_key == "nim123"
    assert cfg.tavily_api_key == "tav456"
    assert cfg.vision_model == "nvidia/nemotron-nano-12b-v2-vl"
    assert cfg.reasoning_model == "moonshotai/kimi-k2.6"
    assert cfg.news_model == "meta/llama-3.3-70b-instruct"
    assert cfg.capture_interval == 30


def test_load_raises_when_key_missing():
    with pytest.raises(ConfigError) as exc:
        Config.load(env={"NIM_API_KEY": "only-one"})
    assert "TAVILY_API_KEY" in str(exc.value)


def test_load_reads_overrides_from_env():
    env = {
        "NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
        "CAPTURE_INTERVAL": "15", "CAPTURE_REGION": "full",
        "VISION_MODEL": "custom/vision", "NEWS_MODEL": "custom/news",
    }
    cfg = Config.load(env=env)
    assert cfg.capture_interval == 15
    assert cfg.vision_model == "custom/vision"
    assert cfg.news_model == "custom/news"


def test_load_reads_tuning_overrides():
    env = {
        "NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
        "PIXEL_DIFF_THRESHOLD": "5.5", "NEWS_CACHE_TTL": "60",
    }
    cfg = Config.load(env=env)
    assert cfg.pixel_diff_threshold == 5.5
    assert cfg.news_cache_ttl == 60


def test_tuning_defaults_when_absent():
    cfg = Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})
    assert cfg.pixel_diff_threshold == 2.0
    assert cfg.news_cache_ttl == 300


def test_vision_stays_on_nim_without_vision_api_key():
    cfg = Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})
    assert cfg.vision_api_key == "n"
    assert cfg.vision_base_url == cfg.base_url
    assert cfg.vision_on_separate_provider is False


def test_vision_api_key_activates_gemini_endpoint_by_default():
    cfg = Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
                           "VISION_API_KEY": "g", "VISION_MODEL": "gemini-2.5-flash"})
    assert cfg.vision_api_key == "g"
    assert "generativelanguage.googleapis.com" in cfg.vision_base_url
    assert cfg.vision_model == "gemini-2.5-flash"
    assert cfg.vision_on_separate_provider is True


def test_vision_key_with_nim_model_raises():
    with pytest.raises(ConfigError) as exc:
        Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
                         "VISION_API_KEY": "g",
                         "VISION_MODEL": "nvidia/nemotron-nano-12b-v2-vl"})
    assert "VISION_MODEL" in str(exc.value)


def test_explicit_vision_base_url_overrides_default():
    cfg = Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t",
                           "VISION_API_KEY": "g",
                           "VISION_BASE_URL": "https://api.groq.com/openai/v1"})
    assert cfg.vision_base_url == "https://api.groq.com/openai/v1"
    assert cfg.vision_on_separate_provider is True
