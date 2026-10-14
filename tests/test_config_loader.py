"""本地覆盖、环境变量优先级与错误配置验证。"""

import pytest
import os
import subprocess
import sys
from pathlib import Path

from utils.config_loader import load_config


@pytest.fixture(autouse=True)
def isolate_local_dotenv(monkeypatch):
    # 用户自己的 .env 不能改变测试预期，也不应进入失败输出。
    monkeypatch.setattr("utils.config_loader.dotenv_values", lambda *args, **kwargs: {})


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


def test_config_cli_works_with_non_chinese_console_encoding(tmp_path):
    config = tmp_path / "valid.yaml"
    config.write_text("{}", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--config", str(config), "--check-config"],
        capture_output=True, env=environment, check=False,
    )
    assert result.returncode == 0
    assert "配置校验通过" in result.stdout.decode("utf-8")


def test_dotenv_overrides_yaml_but_process_environment_wins(tmp_path, monkeypatch):
    path = tmp_path / "local.yaml"
    path.write_text("llm:\n  api_key: yaml-key\n  model: yaml-model\n", encoding="utf-8")
    monkeypatch.setattr("utils.config_loader.dotenv_values", lambda *args, **kwargs: {
        "FLOWGLOSS_API_KEY": "dotenv-key", "FLOWGLOSS_MODEL": "dotenv-model",
    })
    monkeypatch.delenv("FLOWGLOSS_API_KEY", raising=False)
    monkeypatch.delenv("FLOWGLOSS_MODEL", raising=False)
    assert load_config(path)["llm"]["api_key"] == "dotenv-key"
    monkeypatch.setenv("FLOWGLOSS_API_KEY", "process-key")
    assert load_config(path)["llm"]["api_key"] == "process-key"
    assert load_config(path)["llm"]["model"] == "dotenv-model"


def test_dotenv_resolved_from_project_not_working_directory(tmp_path, monkeypatch):
    import utils.config_loader as loader
    from dotenv import dotenv_values
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(
        (loader.PROJECT_ROOT / "config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8",
    )
    (root / ".env").write_text("FLOWGLOSS_API_KEY=test-dotenv-key\nFLOWGLOSS_MODEL=deepseek-flash\n", encoding="utf-8")
    monkeypatch.setattr(loader, "PROJECT_ROOT", root)
    monkeypatch.setattr(loader, "dotenv_values", dotenv_values)
    monkeypatch.delenv("FLOWGLOSS_API_KEY", raising=False)
    monkeypatch.delenv("FLOWGLOSS_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    assert loader.load_config()["llm"]["api_key"] == "test-dotenv-key"
    assert loader.load_config()["llm"]["model"] == "deepseek-flash"
