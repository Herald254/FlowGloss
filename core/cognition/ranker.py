# e:\code\FlowGloss\core\cognition\ranker.py
"""
术语去重、已掌握过滤与数量限制。

保持 LLM 给出的重要性顺序，通过 KnowledgeDB 查询用户掌握记录。
复杂的多维评分、语义传播和频率统计留待后续实现。
"""

from __future__ import annotations

from typing import Callable

from core.models import Term


def normalize_term(term: str) -> str:
    return " ".join(term.split()).casefold()


def get_top_candidates(
    entities: list[Term], is_mastered: Callable[[str], bool], limit: int = 3,
) -> list[Term]:
    """保留模型的重要性顺序，过滤重复术语和已掌握词。"""
    candidates = []
    seen = set()
    for entity in entities:
        key = normalize_term(entity.text)
        if not key or key in seen or is_mastered(entity.text):
            continue
        seen.add(key)
        candidates.append(entity)
        if len(candidates) >= limit:
            break
    return candidates
