import pytest
from tradesight.config import Config, ConfigError


def test_load_returns_config_with_required_keys():
    env = {"NIM_API_KEY": "nim123", "TAVILY_API_KEY": "tav456"}
    cfg = Config.load(env=env)
    assert cfg.nim_api_key == "nim123"
    assert cfg.tavily_api_key == "tav456"
    assert cfg.vision_model == "meta/llama-3.2-90b-vision-instruct"
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
