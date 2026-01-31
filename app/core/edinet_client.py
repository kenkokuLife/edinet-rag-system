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
        date: Optional[str] = None,
        doc_type: str = "120",
        days_back: int = 7
    ) -> List[Dict]:
        """搜索EDINET文档"""
        if not date:
            date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        url = f"{self.api_url}/v1/documents.json"
        params = {
            "date": date,
            "type": doc_type
        }
        
        if self.api_key:
            params["Subscription-Key"] = self.api_key
            
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            documents = []
            for item in data.get("results", []):
                if item.get("docTypeCode") == doc_type:  # 有价证券报告书
                    documents.append({
                        "doc_id": item.get("docID"),
                        "edinet_code": item.get("edinetCode"),
                        "company_name": item.get("filerName"),
                        "doc_description": item.get("docDescription"),
                        "submit_date": item.get("submitDateTime"),
                        "period_start": item.get("periodStart"),
                        "period_end": item.get("periodEnd"),
                        "xbrl_flag": item.get("xbrlFlag") == "1"
                    })
            
            logger.info(f"找到 {len(documents)} 份报告书")
            return documents
            
        except Exception as e:
            logger.error(f"搜索EDINET文档失败: {e}")
            return []
    
    def download_document(
        self,
        doc_id: str,
        save_dir: Optional[Path] = None,
        file_type: str = "1"  # 1: XBRL, 2: PDF, 3: 附件
    ) -> Optional[Path]:
        """下载文档文件"""
        url = f"{self.api_url}/v1/documents/{doc_id}"
        params = {"type": file_type}
        
        if self.api_key:
            params["Subscription-Key"] = self.api_key
            
        try:
            response = requests.get(url, params=params, timeout=60)
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