from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import uvicorn
import os

from app.state import app_state, set_component
from app.api.endpoints import router as api_router
from app.core.config import settings
from app.core.edinet_client import EdinetClient
from app.core.xbrl_parser import XBRLParser
from app.utils.chunking import JapaneseTextChunker
from app.services.vector_store import VectorStoreManager
from app.services.document_processor import DocumentProcessor
from app.core.rag_engine import RAGEngine

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("启动EDINET RAG系统...")
    
    # 初始化组件
    try:
        # 1. 初始化EDINET客户端
        edinet_client = EdinetClient(
            api_key=settings.edinet_api_key,
            api_url=settings.edinet_api_url
        )
        
        # 2. 初始化XBRL解析器
        xbrl_parser = XBRLParser()
        
        # 3. 初始化文本分块器
        text_chunker = JapaneseTextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
        
        # 4. 初始化向量存储
        vector_store = VectorStoreManager(
            host=settings.chroma_host,
            port=settings.chroma_port,
            collection_name=settings.chroma_collection_name,
            embedding_model=settings.embedding_model,
            device=settings.embedding_device
        )
        
        # 5. 初始化文档处理器
        document_processor = DocumentProcessor(
            edinet_client=edinet_client,
            xbrl_parser=xbrl_parser,
            text_chunker=text_chunker,
            vector_store=vector_store,
            config={
                "raw_data_dir": settings.raw_data_dir,
                "processed_data_dir": settings.processed_data_dir
            }
        )
        
        # 6. 初始化RAG引擎
        rag_engine = RAGEngine(
            vector_store=vector_store,
            ollama_host=settings.ollama_host,
            ollama_port=settings.ollama_port,
            ollama_model=settings.ollama_model
        )
        
        # 保存到应用状态
        app_state.update({
            "edinet_client": edinet_client,
            "xbrl_parser": xbrl_parser,
            "text_chunker": text_chunker,
            "vector_store": vector_store,
            "document_processor": document_processor,
            "rag_engine": rag_engine,
            "settings": settings
        })
        
        logger.info("系统初始化完成")
        
    except Exception as e:
        logger.error(f"系统初始化失败: {e}")
        raise
    
    yield  # 应用运行中
    
    # 关闭时
    logger.info("关闭EDINET RAG系统...")
    document_processor = app_state.get("document_processor")
    if document_processor:
        document_processor.executor.shutdown(wait=True)

# 创建FastAPI应用
app = FastAPI(
    title="EDINET有价证券报告书RAG系统",
    description="轻量级有价证券报告书检索与生成系统",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加API路由
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    """根端点"""
    return {
        "message": "EDINET有价证券报告书RAG系统",
        "version": "1.0.0",
        "status": "运行中",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查向量存储连接
        vector_store = app_state.get("vector_store")
        if vector_store:
            stats = vector_store.get_collection_stats()
            vector_status = "healthy"
        else:
            vector_status = "unavailable"
        
        return {
            "status": "healthy",
            "components": {
                "vector_store": vector_status,
                "rag_engine": "healthy" if app_state.get("rag_engine") else "unavailable"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower()
    )