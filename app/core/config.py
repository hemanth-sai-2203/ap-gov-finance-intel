import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AP Government Finance Intelligence"
    
    DATABASE_URL: Optional[str] = None
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    
    WEAVIATE_URL: Optional[str] = None
    WEAVIATE_API_KEY: Optional[str] = None
    WEAVIATE_INDEX_NAME: str = "GovIntelDocument"
    
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIMENSION: int = 768
    HF_TOKEN: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None
    USE_LOCAL_EMBEDDER: bool = False
    USE_LOCAL_RERANKER: bool = False
    
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    LLM_PROVIDER: str = "gemini"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

settings = Settings()
