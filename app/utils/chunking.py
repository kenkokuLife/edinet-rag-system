import re
from typing import List, Dict, Any
from loguru import logger
import os

class JapaneseTextChunker:
    """日语文本分块器"""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tagger = None
        self._init_mecab()
    
    def _init_mecab(self):
        """初始化MeCab，处理不同环境的配置"""
        try:
            import MeCab
            # 尝试使用默认配置
            try:
                self.tagger = MeCab.Tagger("-Owakati")
                logger.info("MeCab初始化成功（默认配置）")
            except RuntimeError as e:
                logger.warning(f"MeCab默认配置失败，尝试自定义配置: {e}")
                # 尝试指定mecabrc路径
                mecab_rc_paths = [
                    "/usr/local/etc/mecabrc",
                    "/etc/mecabrc",
                    "/usr/etc/mecabrc"
                ]
                
                tagger_created = False
                for rc_path in mecab_rc_paths:
                    if os.path.exists(rc_path):
                        try:
                            self.tagger = MeCab.Tagger(f"-r {rc_path} -Owakati")
                            logger.info(f"MeCab初始化成功（使用配置: {rc_path}）")
                            tagger_created = True
                            break
                        except RuntimeError:
                            continue
                
                if not tagger_created:
                    logger.warning("无法初始化MeCab，将使用简单的文本分块")
                    self.tagger = None
        except ImportError:
            logger.warning("MeCab未安装，将使用简单的文本分块")
            self.tagger = None
        
    def chunk_document(self, document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将文档分块"""
        chunks = []
        
        # 处理财务数据
        financial_chunks = self._chunk_financial_data(
            document.get("financial_data", [])
        )
        chunks.extend(financial_chunks)
        
        # 处理文本内容
        for section, content in document.get("text_content", {}).items():
            text_chunks = self._chunk_text(
                content, 
                metadata={
                    "section": section,
                    "doc_id": document.get("doc_id"),
                    "company_name": document.get("company_name", {}).get("name", "")
                }
            )
            chunks.extend(text_chunks)
        
        # 添加元数据
        for i, chunk in enumerate(chunks):
            chunk["chunk_id"] = f"{document.get('doc_id', 'unknown')}_{i}"
            chunk["doc_id"] = document.get("doc_id")
            chunk["company_name"] = document.get("company_name", {}).get("name", "")
            chunk["filing_date"] = document.get("company_name", {}).get("filing_date", "")
        
        logger.info(f"文档 {document.get('doc_id')} 分块为 {len(chunks)} 个块")
        return chunks
    
    def _chunk_financial_data(self, financial_data: List[Dict]) -> List[Dict]:
        """财务数据分块"""
        chunks = []
        current_chunk = []
        current_size = 0
        
        for item in financial_data:
            item_text = self._format_financial_item(item)
            item_size = len(item_text)
            
            if current_size + item_size > self.chunk_size and current_chunk:
                # 保存当前块
                chunk_text = "\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "type": "financial",
                    "items": len(current_chunk)
                })
                
                # 保留重叠部分
                overlap_items = current_chunk[-min(len(current_chunk), 2):]
                current_chunk = overlap_items
                current_size = sum(len(item) for item in overlap_items)
            
            current_chunk.append(item_text)
            current_size += item_size
        
        # 处理最后一块
        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "type": "financial",
                "items": len(current_chunk)
            })
        
        return chunks
    
    def _chunk_text(self, text: str, metadata: Dict) -> List[Dict]:
        """文本内容分块"""
        # 使用Mecab进行句子分割
        sentences = self._split_sentences(text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            if current_size + sentence_size > self.chunk_size and current_chunk:
                # 保存当前块
                chunk_text = "".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "type": "text",
                    "section": metadata.get("section"),
                    **metadata
                })
                
                # 保留重叠部分
                overlap_sentences = current_chunk[-min(len(current_chunk), 3):]
                current_chunk = overlap_sentences
                current_size = sum(len(s) for s in overlap_sentences)
            
            current_chunk.append(sentence)
            current_size += sentence_size
        
        # 处理最后一块
        if current_chunk:
            chunk_text = "".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "type": "text",
                "section": metadata.get("section"),
                **metadata
            })
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        """分割日语句子"""
        if self.tagger:
            try:
                # 使用MeCab进行分词
                words = self.tagger.parse(text).split()
                # 按照句子边界重新组织
                sentences = []
                current_sentence = []
                for word in words:
                    current_sentence.append(word)
                    if word.endswith(('。', '！', '？')):
                        sentences.append(''.join(current_sentence))
                        current_sentence = []
                if current_sentence:
                    sentences.append(''.join(current_sentence))
                return sentences
            except Exception as e:
                logger.warning(f"MeCab分词失败，使用简单分割: {e}")
        
        # 如果MeCab不可用或出错，使用简单的正则分割
        sentence_endings = r'[。．！？!?]|\n\n'
        sentences = re.split(sentence_endings, text)
        
        # 清理空句子
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 进一步分割过长的句子
        final_sentences = []
        for sentence in sentences:
            if len(sentence) > 200:
                # 使用Mecab分词后按长度分割
                words = self.tagger.parse(sentence).split()
                current_phrase = []
                current_length = 0
                
                for word in words:
                    if current_length + len(word) > 150 and current_phrase:
                        final_sentences.append("".join(current_phrase))
                        current_phrase = [word]
                        current_length = len(word)
                    else:
                        current_phrase.append(word)
                        current_length += len(word)
                
                if current_phrase:
                    final_sentences.append("".join(current_phrase))
            else:
                final_sentences.append(sentence)
        
        return final_sentences
    
    def _format_financial_item(self, item: Dict) -> str:
        """格式化财务数据项"""
        if item.get("value") is not None:
            return f"{item['japanese_label']}: {item['value']:,} {item.get('unit', '')}"
        else:
            return f"{item['japanese_label']}: {item.get('text_summary', '')}"