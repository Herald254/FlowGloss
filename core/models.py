"""模块间的结构化数据；不依赖 UI 或模型运行时。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextBlock:
    text: str
    bbox: tuple[tuple[float, float], ...]
    confidence: float


@dataclass(frozen=True)
class Term:
    text: str
    context: str


@dataclass(frozen=True)
class Explanation:
    term: str
    context: str
    text: str
    cached: bool = False
