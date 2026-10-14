"""本地覆盖、环境变量优先级与错误配置验证。"""

import pytest

from utils.config_loader import load_config


def test_environment_overrides_local_without_changing_defaults(tmp_path, monkeypatch):
    path = tmp_path / "local.yaml"
    path.write_text("llm:\n  api_key: local-key\n  model: local-model\n", encoding="utf-8")
    monkeypatch.setenv("FLOWGLOSS_API_KEY", "environment-key")
    config = load_config(path)
    assert config["llm"]["api_key"] == "environment-key"
    assert config["llm"]["model"] == "local-model"
    assert config["capture"]["monitor_index"] == 1


@pytest.mark.parametrize("text", [
    "capture:\n  region: [0, 0, -1, 10]\n",
    "capture:\n  monitor_index: -1\n",
    "llm:\n  max_terms: 20\n",
    "llm:\n  timeout_seconds: .nan\n",
    "llm:\n  api_key: 123\n",
    "ui:\n  auto_start: yes-please\n",
])
def test_invalid_config_fails_before_startup(tmp_path, text):
    path = tmp_path / "invalid.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)
