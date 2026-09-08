import os
import logging
from typing import List, Any, Optional
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = settings.EMBEDDING_MODEL_NAME or "BAAI/bge-base-en-v1.5"

_model_instance = None

def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """
    Direct SentenceTransformer singleton with CPU multi-threading.
    Loads lazily on first embedding request to prevent server startup blocking.
    """
    global _model_instance
    if _model_instance is None:
        import torch
        from sentence_transformers import SentenceTransformer
        num_threads = min(4, os.cpu_count() or 1)
        torch.set_num_threads(num_threads)
        logger.info(f"Loading embedding model: {model_name} (CPU threads={num_threads})...")
        try:
            _model_instance = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        except Exception:
            _model_instance = SentenceTransformer(model_name, device="cpu")
        logger.info(f"[OK] Embedding model '{model_name}' loaded successfully.")
    return _model_instance


def embed_texts(texts: List[str], model_name: str = DEFAULT_MODEL_NAME) -> List[List[float]]:
    """
    Fast vectorized embedding generation using native SentenceTransformer.
    """
    if not texts:
        return []
    model = get_embedding_model(model_name)
    logger.info(f"Generating embeddings for {len(texts)} chunks (fast vectorized batch_size=128)...")
    vectors = model.encode(
        texts,
        batch_size=128,
        show_progress_bar=False,
        normalize_embeddings=True
    )
    logger.info(f"[OK] Generated {len(vectors)} embedding vectors (dim={len(vectors[0])}).")
    return vectors.tolist()


if __name__ == "__main__":
    test_texts = ["Andhra Pradesh state budget allocations for education and health."]
    vecs = embed_texts(test_texts)
    print(f"Test embedding vector length: {len(vecs[0])}")  # Expected: 768
