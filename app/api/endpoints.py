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
        def process_in_background():
            results = document_processor.process_batch(doc_ids)

            successful = sum(1 for r in results if r.get("status") == "success")
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

@router.get("/documents/{doc_id}/view")
async def view_document(doc_id: str):
    """查看文档详情（从EDINET下载并解析）"""
    try:
        edinet_client = app_state.get("edinet_client")

        if not edinet_client:
            raise HTTPException(status_code=503, detail="EDINET客户端未初始化")

        # 下载文档
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = edinet_client.download_document(
                doc_id=doc_id,
                save_dir=Path(temp_dir),
                file_type="1"  # XBRL
            )

            # 本地API的PDF下载链接
            pdf_url = f"/api/v1/documents/{doc_id}/pdf"

            if not file_path:
                return {
                    "doc_id": doc_id,
                    "status": "pdf_only",
                    "pdf_url": pdf_url,
                    "message": "XBRLファイルが見つかりません。PDFで確認してください。"
                }

            # 读取XBRL内容
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 简单解析提取文本内容
                import re
                text_content = re.sub(r'<[^>]+>', ' ', content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()

                return {
                    "doc_id": doc_id,
                    "status": "success",
                    "content_preview": text_content[:5000],
                    "content_length": len(text_content),
                    "pdf_url": pdf_url
                }
            except Exception as e:
                return {
                    "doc_id": doc_id,
                    "status": "parse_error",
                    "error": str(e),
                    "pdf_url": pdf_url
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/pdf")
async def download_pdf(doc_id: str):
    """代理下载PDF文件"""
    from fastapi.responses import StreamingResponse
    import requests as req

    try:
        edinet_client = app_state.get("edinet_client")
        if not edinet_client:
            raise HTTPException(status_code=503, detail="EDINET客户端未初始化")

        url = f"{edinet_client.api_url}/v2/documents/{doc_id}"
        # API Key 在 URL 参数中传递
        params = {"type": "2"}
        if edinet_client.api_key:
            params["Subscription-Key"] = edinet_client.api_key

        response = req.get(url, params=params, stream=True, timeout=120)
        response.raise_for_status()

        return StreamingResponse(
            response.iter_content(chunk_size=8192),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={doc_id}.pdf"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/edinet")
async def search_edinet(
    date_from: Optional[str] = Query(None, description="開始日 (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="終了日 (YYYY-MM-DD)"),
    doc_type: str = Query("120", description="文档类型代码"),
    company_name: Optional[str] = Query(None, description="会社名（部分一致）"),
    limit: int = Query(100, ge=1, le=500)
):
    """搜索EDINET文档"""
    try:
        edinet_client = app_state.get("edinet_client")
        if not edinet_client:
            raise HTTPException(status_code=503, detail="EDINET客户端未初始化")

        documents = edinet_client.search_documents(
            date_from=date_from,
            date_to=date_to,
            doc_type=doc_type,
            company_name=company_name
        )

        return {
            "count": len(documents),
            "date_from": date_from,
            "date_to": date_to,
            "company_filter": company_name,
            "documents": documents[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))