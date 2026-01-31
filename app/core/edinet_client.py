import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import zipfile
import io
import time
from loguru import logger

class EdinetClient:
    """EDINET API客户端"""
    
    def __init__(self, api_key: str = None, api_url: str = None):
        self.api_key = api_key
        self.api_url = api_url or "https://disclosure.edinet-fsa.go.jp/api"
        
    def search_documents(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        doc_type: str = "120",
        company_name: Optional[str] = None
    ) -> List[Dict]:
        """搜索EDINET文档

        Args:
            date_from: 开始日期 (YYYY-MM-DD)，可选
            date_to: 结束日期 (YYYY-MM-DD)，可选，默认今天
            doc_type: 文档类型代码 (120=有价证券报告书)
            company_name: 公司名筛选（部分匹配）

        Returns:
            文档列表
        """
        all_documents = []

        # 设置日期范围
        if date_to:
            end_date = datetime.strptime(date_to, "%Y-%m-%d")
        else:
            end_date = datetime.now()

        if date_from:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
        else:
            # 默认搜索最近7天
            start_date = end_date - timedelta(days=7)

        # 生成日期列表（限制最大60天，避免搜索过慢）
        max_days = 60
        dates_to_search = []
        current = start_date
        while current <= end_date:
            dates_to_search.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
            if len(dates_to_search) >= max_days:
                logger.warning(f"日期范围超过{max_days}天，只搜索最近{max_days}天")
                break

        logger.info(f"搜索日期范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (实际搜索{len(dates_to_search)}天)")

        for search_date in dates_to_search:
            url = f"{self.api_url}/v2/documents.json"
            params = {
                "date": search_date,
                "type": 2  # 提出書類一覧及びメタデータを取得
            }

            if self.api_key:
                params["Subscription-Key"] = self.api_key

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    # 筛选文档类型
                    if doc_type and item.get("docTypeCode") != doc_type:
                        continue

                    # 筛选公司名（部分匹配）
                    filer_name = item.get("filerName", "")
                    if company_name and company_name not in filer_name:
                        continue

                    all_documents.append({
                        "doc_id": item.get("docID"),
                        "edinet_code": item.get("edinetCode"),
                        "company_name": filer_name,
                        "doc_description": item.get("docDescription"),
                        "submit_date": item.get("submitDateTime"),
                        "period_start": item.get("periodStart"),
                        "period_end": item.get("periodEnd"),
                        "xbrl_flag": item.get("xbrlFlag") == "1",
                        "sec_code": item.get("secCode"),
                    })

            except Exception as e:
                logger.warning(f"搜索日期 {search_date} 失败: {e}")
                continue

        logger.info(f"找到 {len(all_documents)} 份报告书")
        return all_documents
    
    def download_document(
        self,
        doc_id: str,
        save_dir: Optional[Path] = None,
        file_type: str = "1"  # 1: XBRL, 2: PDF, 3: 附件, 5: CSV
    ) -> Optional[Path]:
        """下载文档文件"""
        url = f"{self.api_url}/v2/documents/{doc_id}"
        params = {"type": file_type}

        # API Key 在 URL 参数中传递
        if self.api_key:
            params["Subscription-Key"] = self.api_key

        logger.info(f"下载文档: {doc_id}, type={file_type}")

        try:
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            
            # 处理ZIP文件
            if response.headers.get("Content-Type") == "application/zip":
                zip_content = io.BytesIO(response.content)
                
                with zipfile.ZipFile(zip_content, 'r') as zip_ref:
                    # 查找XBRL文件
                    xbrl_files = [f for f in zip_ref.namelist() 
                                if f.endswith('.xbrl') or f.endswith('.xml')]
                    
                    if not xbrl_files:
                        logger.warning(f"文档 {doc_id} 中没有找到XBRL文件")
                        return None
                    
                    # 解压第一个XBRL文件
                    xbrl_file = xbrl_files[0]
                    xbrl_content = zip_ref.read(xbrl_file)
                    
                    if save_dir:
                        save_path = save_dir / f"{doc_id}.xbrl"
                        save_path.write_bytes(xbrl_content)
                        logger.info(f"已保存: {save_path}")
                        return save_path
                    else:
                        # 返回临时文件路径
                        temp_path = Path(f"/tmp/{doc_id}.xbrl")
                        temp_path.write_bytes(xbrl_content)
                        return temp_path
            else:
                logger.warning(f"文档 {doc_id} 不是ZIP格式")
                return None
                
        except Exception as e:
            logger.error(f"下载文档 {doc_id} 失败: {e}")
            return None
    
    def get_company_info(self, edinet_code: str) -> Optional[Dict]:
        """获取公司信息"""
        url = f"{self.api_url}/v1/companies/{edinet_code}.json"
        params = {}
        
        if self.api_key:
            params["Subscription-Key"] = self.api_key
            
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取公司信息失败: {e}")
            return None