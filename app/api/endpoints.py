from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

from app.state import app_state, get_component

router = APIRouter()

# 请求/响应模型
class QueryRequest(BaseModel):
    question: str
    company_filter: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    context_preview: str
    processing_time: float

class DocumentProcessRequest(BaseModel):
    doc_ids: List[str]
    date: Optional[str] = None
    limit: Optional[int] = 10

class DocumentProcessResponse(BaseModel):
    success: bool
    processed: int
    failed: int
    results: List[dict]

class SystemStatus(BaseModel):
    status: str
    vector_store_stats: dict
    processing_stats: dict
    timestamp: datetime

@router.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """查询文档"""
    try:
        rag_engine = app_state.get("rag_engine")
        if not rag_engine:
            raise HTTPException(status_code=503, detail="RAG引擎未初始化")
        
        import time
        start_time = time.time()
        
        result = rag_engine.query(
            question=request.question,
            company_filter=request.company_filter
        )
        
        processing_time = time.time() - start_time
        
        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            context_preview=result["context"],
            processing_time=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/process", response_model=DocumentProcessResponse)
async def process_documents(
    request: DocumentProcessRequest,
    background_tasks: BackgroundTasks
):
    """处理文档"""
    try:
        document_processor = app_state.get("document_processor")
        if not document_processor:
            raise HTTPException(status_code=503, detail="文档处理器未初始化")
        
        if request.doc_ids:
            # 处理特定文档ID
            doc_ids = request.doc_ids
        else:
            # 搜索并处理文档
            results = document_processor.search_and_process(
                date=request.date,
                limit=request.limit or 10
            )
            doc_ids = [r["doc_id"] for r in results if r.get("success")]
        
        # 在后台处理文档
        async def process_in_background():
            import asyncio
            results = await document_processor.process_multiple_documents(doc_ids)
            
            successful = sum(1 for r in results if r.get("success"))
            failed = len(results) - successful
            
            logger.info(f"后台处理完成: {successful}成功, {failed}失败")
        
        background_tasks.add_task(process_in_background)
        
        return DocumentProcessResponse(
            success=True,
            processed=len(doc_ids),
            failed=0,
            results=[]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{doc_id}/delete")
async def delete_document(doc_id: str):
    """删除文档"""
    try:
        vector_store = app_state.get("vector_store")
        if not vector_store:
            raise HTTPException(status_code=503, detail="向量存储未初始化")
        
        success = vector_store.delete_document(doc_id)
        
        if success:
            return {"success": True, "message": f"文档 {doc_id} 已删除"}
        else:
            raise HTTPException(status_code=500, detail="删除失败")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统状态"""
    try:
        vector_store = app_state.get("vector_store")
        document_processor = app_state.get("document_processor")
        
        vector_stats = vector_store.get_collection_stats() if vector_store else {}
        processing_stats = document_processor.get_processing_stats() if document_processor else {}
        
        return SystemStatus(
            status="running",
            vector_store_stats=vector_stats,
            processing_stats=processing_stats,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/edinet")
async def search_edinet(
    date: Optional[str] = None,
    doc_type: str = Query("120", description="文档类型代码"),
    limit: int = Query(20, ge=1, le=100)
):
    """搜索EDINET文档"""
    try:
        edinet_client = app_state.get("edinet_client")
        if not edinet_client:
            raise HTTPException(status_code=503, detail="EDINET客户端未初始化")
        
        documents = edinet_client.search_documents(
            date=date,
            doc_type=doc_type
        )
        
        return {
            "count": len(documents),
            "date": date or "latest",
            "documents": documents[:limit]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))