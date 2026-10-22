import hashlib
import logging
from typing import Protocol

import numpy as np

from agent.memory.negation_lexicon import tokenize

log = logging.getLogger("agent.embedder")
FASTEMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    name = "hash-v1"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                digest = hashlib.sha1(token.encode()).digest()
                matrix[row, int.from_bytes(digest[:4], "big") % self.dim] += 1.0
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)


class FastEmbedder:
    def __init__(self, cache_dir: str, model: str = FASTEMBED_MODEL):
        self.name = model
        self.cache_dir = cache_dir
        self.model = None

    def load(self):
        if self.model is None:
            from fastembed import TextEmbedding

            self.model = TextEmbedding(model_name=self.name, cache_dir=self.cache_dir)
        return self.model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(list(self.load().embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


class FallbackEmbedder:
    def __init__(self, primary: FastEmbedder):
        self.primary = primary
        self.backup = HashEmbedder()
        self.failed = False

    @property
    def name(self) -> str:
        return self.backup.name if self.failed else self.primary.name

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self.failed:
            try:
                return self.primary.embed(texts)
            except Exception as error:
                log.warning("fastembed unavailable, using hash embedder: %s", error)
                self.failed = True
        return self.backup.embed(texts)


def build_embedder(kind: str, cache_dir: str) -> Embedder:
    if kind == "fastembed":
        return FallbackEmbedder(FastEmbedder(cache_dir))
    return HashEmbedder()
