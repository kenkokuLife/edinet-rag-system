"""
RAG引擎模块
用于实现检索增强生成（Retrieval-Augmented Generation）功能
"""
from typing import List, Dict, Optional
from loguru import logger
import requests


class RAGEngine:
    """RAG引擎"""

    def __init__(self, vector_store, ollama_host: str, ollama_port: int, ollama_model: str):
        """
        初始化RAG引擎

        Args:
            vector_store: 向量存储管理器
            ollama_host: Ollama服务主机
            ollama_port: Ollama服务端口
            ollama_model: Ollama模型名称
        """
        self.vector_store = vector_store
        self.ollama_host = ollama_host
        self.ollama_port = ollama_port
        self.ollama_model = ollama_model
        self.ollama_url = f"http://{ollama_host}:{ollama_port}"
        logger.info(f"初始化RAG引擎 - 连接到 {ollama_host}:{ollama_port}")

    def retrieve(self, query: str, top_k: int = 5, company_filter: Optional[str] = None) -> List[Dict]:
        """
        检索相关文档

        Args:
            query: 查询文本
            top_k: 返回的最相关文档数量
            company_filter: 公司名称过滤器

        Returns:
            相关文档列表
        """
        try:
            logger.info(f"检索相关文档: {query}")

            # 构建过滤条件
            filter_conditions = None
            if company_filter:
                filter_conditions = {"company_name": {"$contains": company_filter}}

            # 使用向量存储搜索
            results = self.vector_store.search(
                query=query,
                n_results=top_k,
                filter_conditions=filter_conditions
            )

            # 格式化结果
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "text": r.get("text", ""),
                    "company": r.get("metadata", {}).get("company_name", "不明"),
                    "doc_id": r.get("metadata", {}).get("doc_id", ""),
                    "section": r.get("metadata", {}).get("section", ""),
                    "score": r.get("score", 0),
                })

            logger.info(f"检索到 {len(formatted_results)} 个相关文档块")
            return formatted_results

        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []

    def generate(self, query: str, context: List[Dict]) -> str:
        """
        生成回答

        Args:
            query: 查询文本
            context: 上下文文档

        Returns:
            生成的回答
        """
        try:
            logger.info(f"生成回答: {query}")

            # 如果没有上下文，返回提示信息
            if not context:
                return "申し訳ございませんが、関連する情報が見つかりませんでした。まず報告書を処理（STEP 2）してから質問してください。"

            # 构建上下文文本
            context_text = "\n\n".join([
                f"【{c.get('company', '不明')}】\n{c.get('text', '')}"
                for c in context[:5]  # 最多使用5个上下文
            ])

            # 构建提示
            prompt = f"""あなたは有価証券報告書の分析専門家です。以下の参照情報を基に、質問に日本語で回答してください。

【参照情報】
{context_text}

【質問】
{query}

【回答】
上記の参照情報に基づいて、簡潔かつ正確に回答してください。数値がある場合は具体的に示してください。"""

            # 调用Ollama API
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 1000,
                        }
                    },
                    timeout=120
                )

                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("response", "").strip()
                    if answer:
                        return answer

                logger.warning(f"Ollama API返回异常: {response.status_code}")

            except requests.exceptions.ConnectionError:
                logger.warning("Ollama服务未连接，使用简单回答模式")
            except requests.exceptions.Timeout:
                logger.warning("Ollama请求超时")
            except Exception as e:
                logger.warning(f"Ollama调用失败: {e}")

            # 如果Ollama不可用，返回基于上下文的简单回答
            return self._generate_simple_answer(query, context)

        except Exception as e:
            logger.error(f"生成失败: {e}")
            return "回答の生成中にエラーが発生しました。"

    def _generate_simple_answer(self, query: str, context: List[Dict]) -> str:
        """当Ollama不可用时，生成简单的基于上下文的回答"""
        if not context:
            return "関連する情報が見つかりませんでした。"

        # 提取关键信息
        companies = set()
        excerpts = []

        for c in context[:3]:
            company = c.get("company", "")
            if company:
                companies.add(company)
            text = c.get("text", "")[:500]
            if text:
                excerpts.append(text)

        company_list = "、".join(companies) if companies else "不明"

        answer = f"【検索結果】\n\n"
        answer += f"関連会社: {company_list}\n\n"
        answer += "【参照情報の抜粋】\n"
        for i, excerpt in enumerate(excerpts, 1):
            answer += f"\n{i}. {excerpt}...\n"

        answer += "\n※ LLM（Ollama）が利用できないため、検索結果のみを表示しています。"

        return answer

    def query(self, question: str, top_k: int = 5, company_filter: Optional[str] = None) -> Dict:
        """
        执行完整的RAG查询

        Args:
            question: 问题
            top_k: 返回的最相关文档数量
            company_filter: 公司名称过滤器

        Returns:
            查询结果
        """
        try:
            # 检索相关文档
            documents = self.retrieve(question, top_k, company_filter)

            # 生成回答
            answer = self.generate(question, documents)

            # 构建上下文预览
            context = "\n".join([d.get("text", "")[:200] for d in documents[:3]])

            return {
                "question": question,
                "answer": answer,
                "sources": documents,
                "context": context
            }
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return {
                "question": question,
                "answer": f"エラーが発生しました: {str(e)}",
                "sources": [],
                "context": ""
            }
