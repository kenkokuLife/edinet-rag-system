import chromadb
import os
import threading
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
import numpy as np
from loguru import logger
import time


class VectorStoreManager:
    """向量存储管理器（支持后台加载大模型以避免启动阻塞）。"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        collection_name: str = "edinet_reports",
        embedding_model: str = "intfloat/multilingual-e5-large-instruct",
        fallback_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "cpu",
        max_retries: int = 3,
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.device = device
        self.max_retries = max_retries
        self.primary_model = embedding_model
        self.fallback_model = fallback_model

        # 初始化 ChromaDB 客户端（优先 HTTP 客户端，失败则回退到内存客户端）
        try:
            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(
                    chroma_server_auth_provider="token",
                    chroma_server_auth_credentials="test-token",
                ),
            )
        except Exception as e:
            logger.warning(f"ChromaDB连接失败（带认证）: {e}，尝试不带认证...")
            try:
                self.client = chromadb.HttpClient(host=host, port=port)
            except Exception as e2:
                logger.error(f"ChromaDB连接失败（不带认证）: {e2}")
                logger.info("使用内存客户端")
                self.client = chromadb.EphemeralClient()

        # 先使用轻量简单模型，避免在启动时被大模型下载阻塞
        self.embedding_model = self._create_simple_embedding_model()

        # 在后台异步加载主模型与备用模型（成功后替换 self.embedding_model）
        threading.Thread(target=self._load_embedding_model_background, daemon=True).start()

        # 获取或创建集合
        self.collection = self._get_or_create_collection()

    def _load_embedding_model_with_retry(self):
        """带重试的模型加载函数（同步）。"""
        models_to_try = [(self.primary_model, "主要模型"), (self.fallback_model, "备用模型")]

        for model_name, description in models_to_try:
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"尝试加载{description}: {model_name} (尝试 {attempt + 1}/{self.max_retries})")

                    # 设置缓存目录
                    os.environ["TRANSFORMERS_CACHE"] = "/app/models"
                    os.environ["HF_HOME"] = "/app/models"

                    model = SentenceTransformer(model_name, device=self.device, cache_folder="/app/models")
                    logger.info(f"✅ 成功加载模型: {model_name}")
                    return model

                except Exception as e:
                    logger.warning(f"加载模型 {model_name} 失败 (尝试 {attempt + 1}): {e}")
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"无法加载模型 {model_name}，已重试 {self.max_retries} 次")

        logger.error("所有模型加载失败，使用简单嵌入模型作为退路")
        return None

    def _load_embedding_model_background(self):
        """在后台加载真实模型；加载成功后替换当前的简单模型。"""
        try:
            model = self._load_embedding_model_with_retry()
            if model:
                self.embedding_model = model
                logger.info("后台模型加载完成，已替换简单嵌入模型")
        except Exception as e:
            logger.error(f"后台加载嵌入模型失败: {e}")

    def _create_simple_embedding_model(self):
        """创建一个非常轻量的嵌入实现，接受与 SentenceTransformer 兼容的参数。"""
        import numpy as _np

        class SimpleEmbeddingModel:
            def __init__(self):
                self.embedding_dim = 384
                logger.warning("使用简单的嵌入模型（仅用于开发/快速启动）")

            def encode(self, texts, **kwargs):
                if isinstance(texts, str):
                    texts = [texts]
                batch_size = len(texts)
                emb = _np.random.randn(batch_size, self.embedding_dim).astype(_np.float32)
                norms = _np.linalg.norm(emb, axis=1, keepdims=True)
                emb = emb / (norms + 1e-12)
                return emb

        return SimpleEmbeddingModel()

    def _get_or_create_collection(self):
        try:
            collection = self.client.get_collection(self.collection_name)
            logger.info(f"使用现有集合: {self.collection_name}")
            return collection
        except Exception:
            logger.info(f"创建新集合: {self.collection_name}")
            return self.client.create_collection(name=self.collection_name, metadata={"description": "EDINET有价证券报告书"})

    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """创建文本嵌入，统一调用当前可用的 embedding_model.encode。"""
        prefixed_texts = [f"query: {t}" for t in texts]
        try:
            emb = self.embedding_model.encode(prefixed_texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
            return emb
        except TypeError:
            # SimpleEmbeddingModel 不支持这些关键字参数
            emb = self.embedding_model.encode(prefixed_texts)
            return np.asarray(emb)

    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        try:
            ids, texts, metadatas, embeddings = [], [], [], []
            for doc in documents:
                chunk_id = doc.get("chunk_id")
                text = doc.get("text", "")
                if not text or not chunk_id:
                    continue
                emb = self.create_embeddings([text])[0]
                ids.append(chunk_id)
                texts.append(text)
                embeddings.append(emb.tolist())
                metadatas.append({
                    "doc_id": doc.get("doc_id"),
                    "company_name": doc.get("company_name", ""),
                    "filing_date": doc.get("filing_date", ""),
                    "type": doc.get("type", "text"),
                    "section": doc.get("section", ""),
                    "chunk_size": len(text),
                })

            if not ids:
                logger.warning("没有有效的文档可添加")
                return False

            self.collection.add(embeddings=embeddings, documents=texts, metadatas=metadatas, ids=ids)
            logger.info(f"成功添加 {len(ids)} 个文档块")
            return True
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False

    def search(self, query: str, n_results: int = 5, filter_conditions: Optional[Dict] = None) -> List[Dict[str, Any]]:
        try:
            query_embedding = self.create_embeddings([query])[0]
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=n_results,
                where=filter_conditions,
                include=["documents", "metadatas", "distances", "ids"],
            )

            formatted = []
            docs = results.get("documents", [])
            if docs:
                for i in range(len(docs[0])):
                    formatted.append({
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "score": 1 - results["distances"][0][i] if results.get("distances") else None,
                        "id": results["ids"][0][i] if results.get("ids") else None,
                    })

            return formatted
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def delete_document(self, doc_id: str) -> bool:
        try:
            results = self.collection.get(where={"doc_id": doc_id}, include=["ids"])
            ids = results.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
                logger.info(f"删除文档 {doc_id} 的 {len(ids)} 个块")
            return True
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        try:
            count = self.collection.count()
            sample = self.collection.get(limit=1)
            return {"total_chunks": count, "collection_name": self.collection_name, "sample_metadata": (sample.get("metadatas") or [None])[0]}
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}