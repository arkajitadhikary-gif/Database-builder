from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import get_settings


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    version: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class LocalSentenceTransformerProvider:
    model_name: str
    expected_dimension: int
    device: str = "cpu"

    provider: str = "local-sentence-transformers"
    version: str = "runtime"

    @property
    def model(self) -> str:
        return self.model_name

    def __post_init__(self) -> None:
        self._model = None
        self.dimension = self.expected_dimension

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed; configure an embedding provider "
                    "before embedding"
                ) from exc
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
            dimension_method = getattr(
                self._model,
                "get_embedding_dimension",
                self._model.get_sentence_embedding_dimension,
            )
            actual = int(dimension_method())
            if actual != self.expected_dimension:
                raise RuntimeError(
                    "embedding dimension mismatch: "
                    f"configured={self.expected_dimension}, model={actual}"
                )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim != 2 or array.shape[1] != self.expected_dimension:
            raise RuntimeError(f"embedding runtime returned invalid shape {array.shape}")
        return array.tolist()


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider != "local":
        raise RuntimeError(f"unsupported embedding provider: {settings.embedding_provider}")
    return LocalSentenceTransformerProvider(
        model_name=settings.embedding_model,
        expected_dimension=settings.embedding_dimension,
        device=settings.embedding_device,
    )


def check_embedding_provider() -> tuple[bool, str]:
    try:
        provider = get_embedding_provider()
        model_path = Path(provider.model)
        if model_path.is_dir():
            available = (model_path / "modules.json").is_file()
        else:
            from huggingface_hub import try_to_load_from_cache

            available = isinstance(
                try_to_load_from_cache(provider.model, "modules.json"), str
            )
        if not available:
            return False, f"model not available locally: {provider.model}"
        return True, f"{provider.provider}/{provider.model}/{provider.dimension}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
