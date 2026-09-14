import os
import logging
from typing import List, Any, Optional
import httpx
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = settings.EMBEDDING_MODEL_NAME or "BAAI/bge-base-en-v1.5"

_model_instance = None


def _get_hf_token() -> Optional[str]:
    return settings.HF_TOKEN or settings.HUGGINGFACE_API_KEY or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")


def _embed_via_hf_api(texts: List[str], model_name: str = DEFAULT_MODEL_NAME) -> Optional[List[List[float]]]:
    """
    Calls Hugging Face Serverless Inference API for fast, zero-RAM embedding generation.
    Returns 768-dim normalized embedding vectors.
    """
    token = _get_hf_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Standard HF Inference endpoints
    endpoints = [
        f"https://router.huggingface.co/hf-inference/models/{model_name}",
        f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}",
        f"https://api-inference.huggingface.co/models/{model_name}",
    ]

    for url in endpoints:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json={"inputs": texts if len(texts) > 1 else texts[0], "options": {"wait_for_model": True}}
                )
                if response.status_code == 200:
                    data = response.json()
                    # If single text, HF returns [float, ...], convert to [[float, ...]]
                    if isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], (int, float)):
                            data = [data]
                        return data
                else:
                    logger.debug(f"HF API endpoint {url} returned {response.status_code}: {response.text[:120]}")
        except Exception as e:
            logger.debug(f"HF API attempt at {url} failed: {e}")

    return None


def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
    """
    Direct SentenceTransformer singleton with CPU multi-threading.
    Loads lazily on first embedding request to prevent server startup blocking.
    """
    global _model_instance
    if _model_instance is None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            num_threads = min(4, os.cpu_count() or 1)
            torch.set_num_threads(num_threads)
            logger.info(f"Loading local embedding model: {model_name} (CPU threads={num_threads})...")
            try:
                _model_instance = SentenceTransformer(model_name, device="cpu", local_files_only=True)
            except Exception:
                _model_instance = SentenceTransformer(model_name, device="cpu")
            logger.info(f"[OK] Local embedding model '{model_name}' loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load local SentenceTransformer: {e}")
            return None
    return _model_instance


def embed_texts(texts: List[str], model_name: str = DEFAULT_MODEL_NAME) -> List[List[float]]:
    """
    Generates embeddings for texts.
    Prioritizes HuggingFace Serverless API (0 MB local RAM), with graceful local fallback.
    """
    if not texts:
        return []

    # 1. Try remote API first unless local is explicitly forced
    if not settings.USE_LOCAL_EMBEDDER:
        api_vectors = _embed_via_hf_api(texts, model_name)
        if api_vectors is not None and len(api_vectors) == len(texts):
            return api_vectors

    # 2. Fallback to local SentenceTransformer if installed and available
    model = get_embedding_model(model_name)
    if model is not None:
        logger.info(f"Generating local embeddings for {len(texts)} chunks...")
        vectors = model.encode(
            texts,
            batch_size=128,
            show_progress_bar=False,
            normalize_embeddings=True
        )
        return vectors.tolist()

    # 3. Emergency fallback if no model is available: return zero vector so query doesn't crash
    logger.error("No embedding backend available (Remote HF API and local model both failed). Returning placeholder vector.")
    return [[0.0] * settings.EMBEDDING_DIMENSION for _ in texts]


if __name__ == "__main__":
    test_texts = ["Andhra Pradesh state budget allocations for education and health."]
    vecs = embed_texts(test_texts)
    print(f"Test embedding vector length: {len(vecs[0])}")  # Expected: 768

