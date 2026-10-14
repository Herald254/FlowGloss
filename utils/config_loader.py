"""YAML 配置加载与校验，供入口、工作线程和 LLM 客户端共享。

默认配置纳入版本控制，.env 与本地配置不提交。
所有相对文件路径都基于项目目录，避免从其他目录启动时失效。
"""

from __future__ import annotations

import math
import os
from copy import deepcopy
from pathlib import Path

import yaml
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _merge(base: dict, overrides: dict) -> dict:
    result = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as file:
            result = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 格式错误：{path.name}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"配置必须是 YAML 映射：{path.name}")
    return result


def load_config(path: str | Path | None = None) -> dict:
    """合并 YAML、项目 .env 和进程环境变量；环境变量优先。"""
    config = _read_yaml(PROJECT_ROOT / "config/settings.yaml")
    local = Path(path) if path else PROJECT_ROOT / "config/settings.local.yaml"
    if path or local.exists():
        config = _merge(config, _read_yaml(local))
    validate_config(config)
    file_env = dotenv_values(PROJECT_ROOT / ".env", encoding="utf-8-sig")
    for env, key in (("FLOWGLOSS_API_KEY", "api_key"), ("FLOWGLOSS_BASE_URL", "base_url"), ("FLOWGLOSS_MODEL", "model")):
        value = os.environ.get(env, file_env.get(env))
        if value is not None:
            config["llm"][key] = value
    validate_config(config)
    database = Path(config["storage"]["database_path"])
    if not database.is_absolute():
        database = PROJECT_ROOT / database
    config["storage"]["database_path"] = str(database)
    return config


def validate_config(config: dict) -> None:
    """对可修改参数提供具体错误，避免工作线程启动后才失败。"""
    for section in ("capture", "ocr", "llm", "storage", "ui"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"配置节 {section} 必须是映射")
    bounds = {
        ("capture", "debounce_seconds"): (0.05, 60),
        ("capture", "cooldown_seconds"): (0, 3600),
        ("capture", "change_threshold"): (0, 1),
        ("ocr", "confidence_threshold"): (0, 1),
        ("ocr", "min_text_length"): (1, 10000),
        ("llm", "timeout_seconds"): (1, 120),
        ("llm", "max_context_chars"): (100, 20000),
        ("llm", "max_terms"): (1, 3),
        ("storage", "cache_hours"): (0, 8760),
        ("ui", "opacity"): (0.2, 1),
    }
    integer_keys = {"min_text_length", "max_context_chars", "max_terms"}
    for (section, key), (low, high) in bounds.items():
        value = config[section].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{section}.{key} 必须在 {low}～{high} 之间")
        if key in integer_keys and not isinstance(value, int):
            raise ValueError(f"{section}.{key} 必须是整数")
    monitor = config["capture"].get("monitor_index")
    if isinstance(monitor, bool) or not isinstance(monitor, int) or monitor < 0:
        raise ValueError("capture.monitor_index 必须是非负整数")
    region = config["capture"].get("region")
    if region is not None:
        if not isinstance(region, list) or len(region) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in region) or region[2] <= 0 or region[3] <= 0:
            raise ValueError("capture.region 必须为 null 或 [left, top, width, height]，宽高须大于 0")
    for key in ("base_url", "model", "user_profile"):
        if not isinstance(config["llm"].get(key), str) or not config["llm"][key].strip():
            raise ValueError(f"llm.{key} 不能为空")
    if not config["llm"]["base_url"].startswith(("https://", "http://")):
        raise ValueError("llm.base_url 必须是 HTTP 或 HTTPS 地址")
    if not isinstance(config["llm"].get("api_key"), str):
        raise ValueError("llm.api_key 必须是字符串")
    if not isinstance(config["storage"].get("database_path"), str) or not config["storage"]["database_path"].strip():
        raise ValueError("storage.database_path 不能为空")
    if not isinstance(config["ui"].get("auto_start"), bool):
        raise ValueError("ui.auto_start 必须为 true 或 false")


def load_prompts() -> dict:
    prompts = _read_yaml(PROJECT_ROOT / "config/prompts.yaml")
    for key in ("system", "extract", "explain"):
        if not isinstance(prompts.get(key), str) or not prompts[key].strip():
            raise ValueError(f"prompts.{key} 不能为空")
    try:
        for key in ("extract", "explain"):
            prompts[key].format(profile="", max_terms=3, text="", term="", context="")
    except (KeyError, ValueError) as exc:
        raise ValueError("提示词模板包含无效的占位符。") from exc
    return prompts
