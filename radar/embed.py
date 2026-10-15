"""문단 임베딩.

기본(tfidf)은 외부 모델 없이 도는 문자 n-gram TF-IDF다. 실제 시연에서는 KURE-v1을 쓴다.
  RADAR_EMBEDDER=kure  → nlpai-lab/KURE-v1 (sentence-transformers 필요, 최초 실행 시 모델 다운로드)
  RADAR_EMBEDDER=qwen3 → Qwen/Qwen3-Embedding-0.6B (비교 실험용)

임베더마다 유사도 분포가 달라 정렬 임계값도 따로 둔다(config.ALIGN_THRESHOLDS).
"""
from __future__ import annotations

import os
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    name: str

    def fit(self, texts: list[str]) -> None: ...

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


class CharNgramEmbedder:
    """문자 2~4-gram TF-IDF. 한국어 어절 변화(조사·어미)에 비교적 강하고 의존성이 없다."""

    name = "tfidf-char(2-4)"

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=1)
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        self._vec.fit([t or " " for t in texts])
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            self.fit(texts)
        return _normalize(self._vec.transform([t or " " for t in texts]).toarray())


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, name: str):
        from sentence_transformers import SentenceTransformer  # 선택 의존성

        self.name = name
        self._model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:
        return None

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=True, batch_size=32))


def make_embedder(kind: str | None = None) -> Embedder:
    kind = (kind or os.getenv("RADAR_EMBEDDER", "tfidf")).lower()
    if kind == "kure":
        return SentenceTransformerEmbedder("nlpai-lab/KURE-v1", "KURE-v1")
    if kind == "qwen3":
        return SentenceTransformerEmbedder("Qwen/Qwen3-Embedding-0.6B", "Qwen3-Embedding-0.6B")
    return CharNgramEmbedder()


def kind_of(embedder: Embedder) -> str:
    if embedder.name.startswith("KURE"):
        return "kure"
    if embedder.name.startswith("Qwen3"):
        return "qwen3"
    return "tfidf"
