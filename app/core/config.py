import os
from typing import Optional
from pydantic_settings import BaseSettings
from loguru import logger

class Settings(BaseSettings):
    # 应用配置
    environment: str = "development"
    log_level: str = "INFO"
    
    # EDINET配置
    edinet_api_key: Optional[str] = None
    edinet_api_url: str = "https://disclosure.edinet-fsa.go.jp/api"
    
    # ChromaDB配置
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_auth_token: Optional[str] = None
    chroma_collection_name: str = "edinet_reports"
    
    # Ollama配置
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "qwen2.5:3b"
    
    # 嵌入模型配置 - 添加备用模型
    embedding_model: str = "intfloat/multilingual-e5-large-instruct"
    embedding_fallback_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"

    # 模型下载重试配置
    model_download_max_retries: int = 3
    model_download_timeout: int = 300
    
    # 文本处理配置
    chunk_size: int = 500
    chunk_overlap: int = 50
    max_chunks_per_document: int = 100
    
    # 路径配置
    data_dir: str = "data"
    raw_data_dir: str = "data/raw"
    processed_data_dir: str = "data/processed"
    models_dir: str = "models"
    
    class Config:
        env_file = ".env"
    
    @property
    def chroma_http_client(self):
        """获取ChromaDB HTTP客户端配置"""
        return {
            "host": self.chroma_host,
            "port": self.chroma_port,
            "ssl": False,
            "headers": {
                "Authorization": f"Bearer {self.chroma_auth_token}"
            } if self.chroma_auth_token else {}
        }

settings = Settings()