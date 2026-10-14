"""阅读链路的行为测试：过期任务、暂停、缓存与失败重试。"""

import asyncio
from unittest.mock import Mock

import numpy as np
import pytest

from core.models import Term, TextBlock
from core.pipeline import LatestTaskQueue, ReadingPipeline
from data.database import KnowledgeDB
from utils.config_loader import load_config


@pytest.fixture
def database(tmp_path):
    db = KnowledgeDB(tmp_path / "knowledge.db")
    yield db
    db.close()


class FakeLLM:
    signature = "test-model-profile-prompt"

    def __init__(self):
        self.extract_calls = 0
        self.explain_calls = 0
        self.fail = False

    async def extract_terms(self, text):
        self.extract_calls += 1
        return [Term("ONNX", "ONNX accelerates model inference.")]

    async def get_explanation(self, term, context):
        self.explain_calls += 1
        if self.fail:
            raise RuntimeError("service unavailable")
        return "ONNX 是用于表示机器学习模型的开放格式。"


@pytest.fixture
def pipeline(database):
    ocr = Mock()
    ocr.recognize.return_value = [TextBlock("ONNX accelerates model inference.", (), 0.99)]
    return ReadingPipeline(load_config(), ocr, FakeLLM(), database)


def frame(value=0):
    return np.full((40, 60, 3), value, dtype=np.uint8)


def test_only_latest_task_is_retained():
    queue = LatestTaskQueue(0)
    old = queue.request(True)
    newest = queue.request(True)
    assert queue.take() == newest
    assert not queue.is_current(old.number)
    queue.close()
    assert queue.take() is None


def test_pause_discards_pending_and_resume_requires_new_request():
    queue = LatestTaskQueue(0)
    old = queue.request(True)
    queue.set_paused(True)
    assert queue.request(True) is None
    assert not queue.is_current(old.number)
    queue.set_paused(False)
    new = queue.request(True)
    assert queue.take() == new
    queue.close()


def test_cooldown_does_not_invalidate_active_task():
    queue = LatestTaskQueue(60)
    task = queue.request()
    assert queue.request() is None
    assert queue.is_current(task.number)
    assert queue.request(True) is not None
    queue.close()


def test_static_frame_skips_ocr_and_requests(pipeline):
    message, results = asyncio.run(pipeline.process(frame()))
    assert results[0].term == "ONNX"
    asyncio.run(pipeline.process(frame()))
    assert pipeline.ocr.recognize.call_count == 1
    assert pipeline.llm.extract_calls == 1
    assert pipeline.llm.explain_calls == 1


def test_changed_image_with_same_text_skips_llm(pipeline):
    asyncio.run(pipeline.process(frame()))
    asyncio.run(pipeline.process(frame(255)))
    assert pipeline.ocr.recognize.call_count == 2
    assert pipeline.llm.extract_calls == 1


def test_manual_retry_uses_cache_and_respects_mastery(pipeline, database):
    asyncio.run(pipeline.process(frame()))
    _, repeated = asyncio.run(pipeline.process(frame(), manual=True))
    assert repeated[0].cached
    assert pipeline.llm.extract_calls == pipeline.llm.explain_calls == 1
    database.update_word("onnx")
    _, mastered = asyncio.run(pipeline.process(frame(), manual=True))
    assert mastered == []
    assert pipeline.llm.explain_calls == 1


def test_api_failure_allows_same_frame_retry(pipeline):
    pipeline.llm.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(pipeline.process(frame()))
    assert pipeline.detector.previous is None
    pipeline.llm.fail = False
    _, results = asyncio.run(pipeline.process(frame()))
    assert results


def test_stale_result_is_not_cached_or_accepted(pipeline, database):
    current = [True]

    async def delayed_answer(term, context):
        current[0] = False
        return "stale answer"

    pipeline.llm.get_explanation = delayed_answer
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pipeline.process(frame(), current=lambda: current[0]))
    key = database.cache_key("ONNX", "ONNX accelerates model inference.", pipeline.llm.signature)
    assert database.get_cached_explanation(key, 24) is None
    assert pipeline.detector.previous is None


def test_ocr_failure_does_not_become_empty_content(pipeline):
    pipeline.ocr.recognize.side_effect = RuntimeError("broken engine")
    with pytest.raises(RuntimeError):
        asyncio.run(pipeline.process(frame()))
    assert pipeline.llm.extract_calls == 0


def test_database_persists_and_context_cache_isolated(tmp_path):
    path = tmp_path / "knowledge.db"
    db = KnowledgeDB(path)
    db.update_word(" ONNX ")
    key = db.cache_key("ONNX", "first context", "model-A")
    db.cache_explanation(key, "first answer")
    db.close()
    db = KnowledgeDB(path)
    try:
        assert db.is_mastered("onnx")
        assert db.get_cached_explanation(key, 24) == "first answer"
        assert db.get_cached_explanation(db.cache_key("ONNX", "second context", "model-A"), 24) is None
        assert db.get_cached_explanation(db.cache_key("ONNX", "first context", "model-B"), 24) is None
        assert db.get_cached_explanation(key, 0) is None
    finally:
        db.close()
