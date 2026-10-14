# e:\code\FlowGloss\core\glossary\llm_client.py
"""
基于 httpx 的异步 OpenAI 兼容 API 客户端。

先提取原文候选术语，再为未掌握且无缓存的术语生成解释。
采用结构化 JSON、有限重试和整体请求期限，不在日志中输出原文或密钥。
缓存由 ReadingPipeline 与 KnowledgeDB 管理；V1.0 暂不启用流式输出。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from urllib.parse import urlparse

import httpx

from core.models import Term

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """面向用户的请求或响应错误，错误信息不含 API 密钥或屏幕文本。"""


class LLMClient:
    """OpenAI 兼容 HTTP 接口；后台事件循环运行，超时和重试都有上限。

    V1.0 使用完整 JSON 响应，暂不启用流式输出。
    """

    def __init__(self, config: dict, prompts: dict, transport=None) -> None:
        self.config = config
        self.prompts = prompts
        self.transport = transport
        self._deepseek = urlparse(config["base_url"]).hostname == "api.deepseek.com"
        signature_data = {k: config[k] for k in ("base_url", "model", "user_profile")}
        signature_data["prompts"] = prompts
        signature_data["request_mode"] = "deepseek-json-no-thinking-v1" if self._deepseek else "chat-v1"
        self.signature = hashlib.sha256(json.dumps(signature_data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    async def _request(self, prompt: str) -> dict:
        if not self.config["api_key"].strip():
            raise LLMError("请在本地配置或 FLOWGLOSS_API_KEY 中设置 API 密钥。")
        headers = {"Authorization": f"Bearer {self.config['api_key']}"}
        payload = {
            "model": self.config["model"],
            "messages": [
                {"role": "system", "content": self.prompts["system"]},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1200,
        }
        if self._deepseek:
            # 本任务只需短 JSON；避免默认思考消耗预算而没有最终回答。
            payload["thinking"] = {"type": "disabled"}
            payload["response_format"] = {"type": "json_object"}
        try:
            # 外层 deadline 覆盖重试与整个响应，避免仅有逐段网络超时。
            async with asyncio.timeout(self.config["timeout_seconds"]):
                async with httpx.AsyncClient(timeout=self.config["timeout_seconds"], transport=self.transport) as client:
                    for attempt in range(2):
                        try:
                            response = await client.post(self.config["base_url"].rstrip("/") + "/chat/completions", headers=headers, json=payload)
                            if response.status_code == 429 or response.status_code >= 500:
                                if attempt == 0:
                                    await asyncio.sleep(0.5)
                                    continue
                            if response.is_error:
                                raise LLMError(f"LLM 请求失败（HTTP {response.status_code}），请检查服务配置。")
                            break
                        except httpx.TransportError:
                            if attempt == 1:
                                raise
                            await asyncio.sleep(0.5)
            choice = response.json()["choices"][0]
            message = choice["message"]
            content = message.get("content")
            reason = choice.get("finish_reason")
            logger.debug(
                "LLM 响应：finish_reason=%s, content_chars=%s, reasoning_chars=%s",
                reason, len(content) if isinstance(content, str) else 0,
                len(message.get("reasoning_content") or ""),
            )
            if reason == "length":
                raise LLMError("LLM 回答达到长度上限被截断，请缩小识别区域后重试。")
            if reason == "content_filter":
                raise LLMError("LLM 服务未返回该内容的解释，请切换页面后重试。")
            if not isinstance(content, str):
                raise ValueError("响应没有文本")
            content = content.strip()
            if not content:
                raise LLMError("LLM 返回了空回答，请稍后手动重试。")
            if content.startswith("```") and content.endswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("JSON 不是映射")
            return result
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise LLMError("LLM 请求超时，可稍后手动重试。") from exc
        except httpx.TransportError as exc:
            raise LLMError("无法连接 LLM 服务，请检查网络和服务地址。") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM 返回格式不正确，可稍后重试。") from exc

    async def extract_terms(self, text: str) -> list[Term]:
        text = text[:self.config["max_context_chars"]]
        prompt = self.prompts["extract"].format(profile=self.config["user_profile"], max_terms=self.config["max_terms"], text=text)
        result = await self._request(prompt)
        raw_terms = result.get("terms")
        if not isinstance(raw_terms, list):
            raise LLMError("LLM 未返回术语列表。")
        terms = []
        for item in raw_terms[:self.config["max_terms"]]:
            if not isinstance(item, dict) or not isinstance(item.get("term"), str) or not isinstance(item.get("context"), str):
                raise LLMError("LLM 返回的术语格式不正确。")
            term, context = item["term"].strip(), item["context"].strip()
            if not term or len(term) > 120 or term.casefold() not in text.casefold():
                continue
            # 不接受模型编造的语境，退回原文片段。
            if not context or context not in text:
                index = text.casefold().find(term.casefold())
                context = text[max(0, index - 120):index + len(term) + 120]
            terms.append(Term(term, context[:self.config["max_context_chars"]]))
        return terms

    async def get_explanation(self, term: str, context: str) -> str:
        prompt = self.prompts["explain"].format(profile=self.config["user_profile"], term=term, context=context[:self.config["max_context_chars"]])
        result = await self._request(prompt)
        explanation = result.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 1000:
            raise LLMError("LLM 未返回有效解释。")
        return explanation.strip()
