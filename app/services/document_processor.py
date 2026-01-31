"""
文档处理器模块
用于处理EDINET文档并将其转换为可索引的格式
"""
from typing import List, Dict, Optional
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import re
import os


class DocumentProcessor:
    """文档处理器"""

    def __init__(self, edinet_client, xbrl_parser, text_chunker, vector_store, config: Dict):
        """
        初始化文档处理器

        Args:
            edinet_client: EDINET API客户端
            xbrl_parser: XBRL解析器
            text_chunker: 文本分块器
            vector_store: 向量存储管理器
            config: 配置字典
        """
        self.edinet_client = edinet_client
        self.xbrl_parser = xbrl_parser
        self.text_chunker = text_chunker
        self.vector_store = vector_store
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._processed_count = 0
        self._failed_count = 0
        logger.info("初始化文档处理器")

    def process_document(self, doc_id: str, company_name: str = "") -> Dict:
        """
        处理单个文档

        Args:
            doc_id: 文档ID
            company_name: 公司名称（可选）

        Returns:
            处理结果
        """
        try:
            logger.info(f"处理文档: {doc_id}")

            # 1. 下载文档
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = self.edinet_client.download_document(
                    doc_id=doc_id,
                    save_dir=Path(temp_dir),
                    file_type="1"  # XBRL
                )

                if not file_path:
                    # XBRL不可用，尝试下载PDF并提取文本
                    logger.warning(f"XBRL下载失败，尝试获取文档概要")
                    text_content = self._get_document_summary(doc_id)
                else:
                    # 2. 读取XBRL内容
                    text_content = self._extract_text_from_xbrl(file_path)

                if not text_content:
                    logger.warning(f"文档 {doc_id} 无法提取文本内容")
                    self._failed_count += 1
                    return {
                        "doc_id": doc_id,
                        "status": "failed",
                        "error": "无法提取文本内容"
                    }

                # 3. 分块处理
                chunks = self._create_chunks(doc_id, company_name, text_content)

                if not chunks:
                    logger.warning(f"文档 {doc_id} 分块为空")
                    self._failed_count += 1
                    return {
                        "doc_id": doc_id,
                        "status": "failed",
                        "error": "分块为空"
                    }

                # 4. 存储到向量数据库
                success = self.vector_store.add_documents(chunks)

                if success:
                    self._processed_count += 1
                    logger.info(f"文档 {doc_id} 处理成功，创建了 {len(chunks)} 个块")
                    return {
                        "doc_id": doc_id,
                        "status": "success",
                        "chunks_created": len(chunks)
                    }
                else:
                    self._failed_count += 1
                    return {
                        "doc_id": doc_id,
                        "status": "failed",
                        "error": "向量存储失败"
                    }

        except Exception as e:
            logger.error(f"文档处理失败 {doc_id}: {e}")
            self._failed_count += 1
            return {
                "doc_id": doc_id,
                "status": "failed",
                "error": str(e)
            }

    def _extract_text_from_xbrl(self, file_path: Path) -> str:
        """从XBRL文件中提取文本内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 移除XML标签，保留文本
            text = re.sub(r'<[^>]+>', ' ', content)
            # 清理多余空白
            text = re.sub(r'\s+', ' ', text).strip()
            # 移除非文本内容
            text = re.sub(r'[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u0020-\u007E\u3000-\u303F\uFF00-\uFFEF\n。、]+', ' ', text)

            return text if len(text) > 100 else ""

        except Exception as e:
            logger.error(f"XBRL文本提取失败: {e}")
            return ""

    def _get_document_summary(self, doc_id: str) -> str:
        """获取文档概要信息（当XBRL不可用时）"""
        try:
            # 从EDINET搜索结果中获取基本信息
            # 这里返回一个占位符，实际应该从搜索结果缓存中获取
            return f"文書ID: {doc_id}"
        except Exception as e:
            logger.error(f"获取文档概要失败: {e}")
            return ""

    def _create_chunks(self, doc_id: str, company_name: str, text_content: str) -> List[Dict]:
        """创建文档块"""
        chunks = []

        # 按段落或固定长度分割
        chunk_size = 500
        overlap = 50

        # 首先尝试按段落分割
        paragraphs = re.split(r'\n\s*\n', text_content)

        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > chunk_size:
                if current_chunk:
                    chunks.append({
                        "chunk_id": f"{doc_id}_{chunk_index}",
                        "doc_id": doc_id,
                        "company_name": company_name,
                        "text": current_chunk,
                        "type": "text",
                        "section": "",
                        "filing_date": ""
                    })
                    chunk_index += 1

                    # 保留重叠部分
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                    current_chunk = overlap_text + " " + para
                else:
                    current_chunk = para
            else:
                current_chunk += " " + para if current_chunk else para

        # 处理最后一个块
        if current_chunk and len(current_chunk) > 50:
            chunks.append({
                "chunk_id": f"{doc_id}_{chunk_index}",
                "doc_id": doc_id,
                "company_name": company_name,
                "text": current_chunk,
                "type": "text",
                "section": "",
                "filing_date": ""
            })

        # 如果分块太少，使用固定长度分割
        if len(chunks) < 3 and len(text_content) > chunk_size:
            chunks = []
            for i in range(0, len(text_content), chunk_size - overlap):
                chunk_text = text_content[i:i + chunk_size]
                if len(chunk_text) > 50:
                    chunks.append({
                        "chunk_id": f"{doc_id}_{i // (chunk_size - overlap)}",
                        "doc_id": doc_id,
                        "company_name": company_name,
                        "text": chunk_text,
                        "type": "text",
                        "section": "",
                        "filing_date": ""
                    })

        return chunks

    def process_batch(self, doc_ids: List[str], company_names: Dict[str, str] = None) -> List[Dict]:
        """
        批量处理文档

        Args:
            doc_ids: 文档ID列表
            company_names: 文档ID到公司名的映射

        Returns:
            处理结果列表
        """
        company_names = company_names or {}
        results = []
        for doc_id in doc_ids:
            company_name = company_names.get(doc_id, "")
            result = self.process_document(doc_id, company_name)
            results.append(result)
        return results

    def get_processing_stats(self) -> Dict:
        """
        返回处理统计信息

        Returns:
            Dict: 包含已处理、失败和最近处理时间的统计信息
        """
        try:
            return {
                "processed_count": self._processed_count,
                "failed_count": self._failed_count,
                "pending_count": 0,
                "last_processed": None,
            }
        except Exception as e:
            logger.error(f"获取处理统计失败: {e}")
            return {"processed_count": 0, "failed_count": 0, "pending_count": 0, "last_processed": None}
