"""使用模拟 HTTP 验证响应、重试与整体超时，不调用付费服务。"""

import asyncio
import json

import httpx
import pytest

from core.glossary.llm_client import LLMClient, LLMError
from utils.config_loader import load_config, load_prompts


def response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})


def client(handler):
    config = load_config()["llm"]
    config["api_key"] = "test-key"
    config["base_url"] = "https://example.test/v1"
    return LLMClient(config, load_prompts(), httpx.MockTransport(handler))


def test_structured_terms_reject_hallucinations_and_repair_context():
    llm = client(lambda request: response({"terms": [
        {"term": "ONNX", "context": "invented context"},
        {"term": "not in screen", "context": "invented context"},
    ]}))
    terms = asyncio.run(llm.extract_terms("ONNX accelerates model inference."))
    assert len(terms) == 1
    assert terms[0].context == "ONNX accelerates model inference."


def test_explanation_request_uses_configured_endpoint():
    def handler(request):
        assert str(request.url).endswith("/v1/chat/completions")
        payload = json.loads(request.content)
        assert payload["messages"][0]["role"] == "system"
        assert request.headers["Authorization"] == "Bearer test-key"
        return response({"explanation": "模型格式"})
    assert asyncio.run(client(handler).get_explanation("ONNX", "ONNX models")) == "模型格式"


def test_transient_error_retried_once():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else response({"terms": []})

    assert asyncio.run(client(handler).extract_terms("ONNX")) == []
    assert len(calls) == 2


def test_auth_error_not_retried_or_leaked():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="secret service detail")

    with pytest.raises(LLMError, match="401") as error:
        asyncio.run(client(handler).extract_terms("ONNX"))
    assert "secret" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("content", [[], {"terms": "wrong"}, {"terms": [None]}])
def test_malformed_response_is_an_error(content):
    with pytest.raises(LLMError):
        asyncio.run(client(lambda request: response(content)).extract_terms("ONNX"))


def test_total_deadline_bounds_request():
    async def handler(request):
        await asyncio.sleep(1)
        return response({"terms": []})

    llm = client(handler)
    llm.config["timeout_seconds"] = 0.02
    with pytest.raises(LLMError, match="超时"):
        asyncio.run(llm.extract_terms("ONNX"))


def test_missing_key_does_not_send_request():
    def handler(request):
        pytest.fail("No request should be sent")

    llm = client(handler)
    llm.config["api_key"] = ""
    with pytest.raises(LLMError, match="密钥"):
        asyncio.run(llm.extract_terms("ONNX"))


def test_deepseek_disables_thinking_and_enforces_json():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_tokens"] == 1200
        return response({"terms": []})

    config = load_config()["llm"]
    config.update(api_key="test-key", base_url="https://api.deepseek.com/v1")
    llm = LLMClient(config, load_prompts(), httpx.MockTransport(handler))
    assert asyncio.run(llm.extract_terms("ONNX")) == []


@pytest.mark.parametrize("url", ["https://example.test/v1", "https://api.deepseek.com.example.test/v1"])
def test_other_services_do_not_receive_deepseek_parameters(url):
    def handler(request):
        payload = json.loads(request.content)
        assert "thinking" not in payload
        assert "response_format" not in payload
        return response({"terms": []})

    config = load_config()["llm"]
    config.update(api_key="test-key", base_url=url)
    llm = LLMClient(config, load_prompts(), httpx.MockTransport(handler))
    assert asyncio.run(llm.extract_terms("ONNX")) == []


@pytest.mark.parametrize("content", ["", '{"terms": ['])
def test_truncated_response_has_specific_error_without_leaking_content(content):
    llm = client(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "length",
        "message": {"content": content, "reasoning_content": "private reasoning"},
    }]}))
    with pytest.raises(LLMError, match="截断") as error:
        asyncio.run(llm.extract_terms("ONNX"))
    assert "private reasoning" not in str(error.value)


def test_empty_answer_distinguished_from_invalid_json():
    llm = client(lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": ""},
    }]}))
    with pytest.raises(LLMError, match="空回答"):
        asyncio.run(llm.extract_terms("ONNX"))
