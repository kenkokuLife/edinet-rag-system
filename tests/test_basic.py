import pytest
import asyncio
from pathlib import Path
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.xbrl_parser import XBRLParser
from app.utils.chunking import JapaneseTextChunker

def test_xbrl_parser():
    """测试XBRL解析器"""
    parser = XBRLParser()
    
    # 测试解析功能
    test_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <xbrl xmlns="http://www.xbrl.org/2003/instance">
        <jpdei:EntityNameJa contextRef="asOfInstant">テスト株式会社</jpdei:EntityNameJa>
        <jpdei:EDINETCodeDEI contextRef="asOfInstant">E00001</jpdei:EDINETCodeDEI>
        <jpcrp:NetSales contextRef="FY2023" unitRef="JPY">1000000</jpcrp:NetSales>
    </xbrl>"""
    
    # 创建测试文件
    test_file = Path("test.xbrl")
    test_file.write_text(test_xml, encoding="utf-8")
    
    try:
        result = parser.parse_xbrl_file(test_file)
        assert "company_info" in result
        print("✓ XBRL解析器测试通过")
    finally:
        test_file.unlink()

def test_text_chunker():
    """测试文本分块器"""
    chunker = JapaneseTextChunker(chunk_size=100, chunk_overlap=20)
    
    test_document = {
        "doc_id": "test001",
        "company_name": {"name": "テスト会社"},
        "text_content": {
            "BusinessRisks": "これはテスト文章です。" * 20
        }
    }
    
    chunks = chunker.chunk_document(test_document)
    assert len(chunks) > 0
    assert "text" in chunks[0]
    print(f"✓ 文本分块器测试通过，生成 {len(chunks)} 个块")

if __name__ == "__main__":
    test_xbrl_parser()
    test_text_chunker()
    print("所有测试通过！")