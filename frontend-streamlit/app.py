import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import time

# 配置
BACKEND_URL = "http://rag-app:8000/api/v1"  # Docker内部网络
# 本地开发用: "http://localhost:8000/api/v1"

# 页面设置
st.set_page_config(
    page_title="EDINET 有価証券報告書 RAG システム",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #374151;
        margin-bottom: 1rem;
    }
    .info-box {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #10B981;
    }
    .warning-box {
        background-color: #FEF3C7;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #F59E0B;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .stButton button {
        background-color: #2563EB;
        color: white;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 初始化会话状态
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'processed_docs' not in st.session_state:
    st.session_state.processed_docs = []
if 'system_status' not in st.session_state:
    st.session_state.system_status = {}

def check_backend_connection():
    """检查后端连接"""
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, {}
    except:
        return False, {}

def search_edinet_documents(date=None, limit=10):
    """搜索EDINET文档"""
    try:
        params = {"limit": limit}
        if date:
            params["date"] = date
        
        response = requests.get(f"{BACKEND_URL}/search/edinet", params=params)
        if response.status_code == 200:
            return response.json()
        return {"count": 0, "documents": []}
    except:
        return {"count": 0, "documents": []}

def process_document(doc_id):
    """处理单个文档"""
    try:
        payload = {"doc_ids": [doc_id]}
        response = requests.post(f"{BACKEND_URL}/documents/process", json=payload)
        return response.status_code == 200
    except:
        return False

def query_rag(question, company_filter=None):
    """查询RAG系统"""
    try:
        payload = {"question": question}
        if company_filter:
            payload["company_filter"] = company_filter
        
        response = requests.post(f"{BACKEND_URL}/query", json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()
        return {"answer": "エラーが発生しました", "sources": []}
    except Exception as e:
        return {"answer": f"接続エラー: {str(e)}", "sources": []}

def delete_document(doc_id):
    """删除文档"""
    try:
        response = requests.get(f"{BACKEND_URL}/documents/{doc_id}/delete")
        return response.status_code == 200
    except:
        return False

# 侧边栏
with st.sidebar:
    st.markdown("## 🔧 システム設定")
    
    # 后端连接状态
    st.markdown("### 接続状態")
    connected, status = check_backend_connection()
    
    if connected:
        st.success("✅ バックエンドに接続済み")
        if status.get('vector_store_stats'):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("ドキュメント数", 
                         status['vector_store_stats'].get('total_chunks', 0))
            with col2:
                st.metric("会社数", 
                         len(set(st.session_state.processed_docs)) if st.session_state.processed_docs else 0)
    else:
        st.error("❌ バックエンド未接続")
    
    st.markdown("---")
    
    # EDINET搜索
    st.markdown("### 📁 EDINET検索")
    search_date = st.date_input(
        "報告書提出日",
        value=datetime.now() - timedelta(days=7)
    )
    search_limit = st.slider("表示件数", 5, 50, 10)
    
    if st.button("🔍 EDINETを検索", use_container_width=True):
        with st.spinner("検索中..."):
            results = search_edinet_documents(
                date=search_date.strftime("%Y-%m-%d"),
                limit=search_limit
            )
            st.session_state.edinet_results = results
    
    # 系统操作
    st.markdown("---")
    st.markdown("### ⚙️ システム操作")
    
    if st.button("🔄 ステータス更新", use_container_width=True):
        st.session_state.system_status = status
        st.rerun()
    
    if st.button("🗑️ チャット履歴削除", use_container_width=True):
        st.session_state.chat_history = []
        st.success("チャット履歴を削除しました")
        st.rerun()

# 主界面
st.markdown('<h1 class="main-header">📊 EDINET 有価証券報告書 RAG システム</h1>', unsafe_allow_html=True)

# 创建标签页
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 チャット検索", 
    "📁 ドキュメント管理", 
    "📊 システム状態",
    "⚙️ 設定"
])

# 标签页1: 聊天搜索
with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown('<h3 class="sub-header">質問を入力してください</h3>', unsafe_allow_html=True)
        
        # 问题输入
        question = st.text_area(
            "質問内容",
            height=100,
            placeholder="例: この会社の売上高は？\n例: 主要な事業リスクを教えて\n例: 当期純利益の推移は？"
        )
        
        # 公司筛选
        company_filter = st.text_input(
            "会社名でフィルター（任意）",
            placeholder="例: トヨタ自動車"
        )
        
        col1_1, col1_2 = st.columns(2)
        with col1_1:
            ask_button = st.button("🚀 質問する", type="primary", use_container_width=True)
        with col1_2:
            example_button = st.button("💡 例文を試す", use_container_width=True)
        
        if example_button:
            examples = [
                "この会社の売上高と営業利益率は？",
                "主要な事業リスクを3つ挙げてください",
                "直近3期の売上高推移を教えて",
                "当期純利益と前期比の増減率は？"
            ]
            question = st.selectbox("例文を選択", examples)
            st.rerun()
        
        if ask_button and question:
            with st.spinner("検索中..."):
                result = query_rag(question, company_filter)
                
                # 添加到聊天历史
                st.session_state.chat_history.append({
                    "question": question,
                    "answer": result.get("answer", ""),
                    "sources": result.get("sources", []),
                    "company": company_filter,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                st.rerun()
    
    with col2:
        st.markdown('<h3 class="sub-header">💡 検索ヒント</h3>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
        <b>効果的な検索例:</b><br>
        1. 財務数値: "売上高 2023年"<br>
        2. リスク: "事業リスク 要因"<br>
        3. 比較: "前期比 増減率"<br>
        4. 概要: "事業内容 概要"<br><br>
        <b>ヒント:</b><br>
        • 具体的な会社名でフィルター<br>
        • 期間を指定して検索<br>
        • 数値と％を組み合わせ
        </div>
        """, unsafe_allow_html=True)
    
    # 显示聊天历史
    st.markdown("---")
    st.markdown('<h3 class="sub-header">🗣️ チャット履歴</h3>', unsafe_allow_html=True)
    
    if st.session_state.chat_history:
        for i, chat in enumerate(reversed(st.session_state.chat_history)):
            with st.expander(f"Q: {chat['question'][:50]}... ({chat['timestamp']})"):
                st.markdown(f"**質問:** {chat['question']}")
                if chat['company']:
                    st.markdown(f"**会社フィルター:** {chat['company']}")
                
                st.markdown("**回答:**")
                st.markdown(f'<div class="success-box">{chat["answer"]}</div>', unsafe_allow_html=True)
                
                if chat['sources']:
                    st.markdown("**参照元:**")
                    for j, source in enumerate(chat['sources'], 1):
                        with st.expander(f"参照元 {j} (類似度: {source['score']:.2%})"):
                            st.markdown(f"**会社:** {source.get('company', '不明')}")
                            if source.get('section'):
                                st.markdown(f"**セクション:** {source['section']}")
                            st.markdown(f"**内容:** {source['text']}")
    else:
        st.info("まだ質問がありません。上のフォームから質問を入力してください。")

# 标签页2: 文档管理
with tab2:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<h3 class="sub-header">📋 ドキュメント一覧</h3>', unsafe_allow_html=True)
        
        if 'edinet_results' in st.session_state:
            results = st.session_state.edinet_results
            documents = results.get('documents', [])
            
            if documents:
                # 创建文档表格
                df_data = []
                for doc in documents:
                    df_data.append({
                        "文書ID": doc.get('doc_id', ''),
                        "会社名": doc.get('company_name', ''),
                        "提出日時": doc.get('submit_date', ''),
                        "XBRL": "✅" if doc.get('xbrl_flag') else "❌",
                        "処理状態": "✅" if doc.get('doc_id') in st.session_state.processed_docs else "❌"
                    })
                
                if df_data:
                    df = pd.DataFrame(df_data)
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # 文档操作
                    selected_doc_id = st.selectbox(
                        "操作するドキュメントを選択",
                        [doc.get('doc_id', '') for doc in documents]
                    )
                    
                    col2_1, col2_2, col2_3 = st.columns(3)
                    with col2_1:
                        if st.button("📥 処理開始", use_container_width=True):
                            with st.spinner("処理中..."):
                                if process_document(selected_doc_id):
                                    st.session_state.processed_docs.append(selected_doc_id)
                                    st.success(f"ドキュメント {selected_doc_id} を処理しました")
                                    st.rerun()
                                else:
                                    st.error("処理に失敗しました")
                    
                    with col2_2:
                        if st.button("🗑️ 削除", use_container_width=True, type="secondary"):
                            if delete_document(selected_doc_id):
                                if selected_doc_id in st.session_state.processed_docs:
                                    st.session_state.processed_docs.remove(selected_doc_id)
                                st.success(f"ドキュメント {selected_doc_id} を削除しました")
                                st.rerun()
                            else:
                                st.error("削除に失敗しました")
                    
                    with col2_3:
                        if st.button("🔄 一括処理", use_container_width=True):
                            with st.spinner("一括処理中..."):
                                success_count = 0
                                for doc in documents[:5]:  # 限制前5个
                                    if process_document(doc.get('doc_id')):
                                        st.session_state.processed_docs.append(doc.get('doc_id'))
                                        success_count += 1
                                        time.sleep(1)  # 避免API限制
                                st.success(f"{success_count}件のドキュメントを処理しました")
                                st.rerun()
            else:
                st.info("ドキュメントが見つかりませんでした。サイドバーから検索してください。")
        else:
            st.info("サイドバーの「EDINETを検索」ボタンをクリックしてドキュメントを取得してください。")
    
    with col2:
        st.markdown('<h3 class="sub-header">📊 処理状況</h3>', unsafe_allow_html=True)
        
        processed_count = len(st.session_state.processed_docs)
        total_count = len(st.session_state.get('edinet_results', {}).get('documents', []))
        
        if total_count > 0:
            progress = processed_count / total_count
            
            # 进度条
            st.progress(progress)
            st.metric("処理済み", f"{processed_count}/{total_count}")
            
            # 处理历史
            if st.session_state.processed_docs:
                st.markdown("**処理履歴:**")
                for doc_id in st.session_state.processed_docs[-5:]:  # 显示最近5个
                    st.markdown(f"• `{doc_id[:10]}...`")
        else:
            st.metric("処理済み", "0")

# 标签页3: 系统状态
with tab3:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<h3 class="sub-header">📈 システム統計</h3>', unsafe_allow_html=True)
        
        if st.button("🔄 統計を更新", key="refresh_stats"):
            connected, status = check_backend_connection()
            if connected:
                st.session_state.system_status = status
        
        if st.session_state.system_status:
            status = st.session_state.system_status
            
            # 指标卡片
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            
            with metric_col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    "ベクトル数",
                    status.get('vector_store_stats', {}).get('total_chunks', 0),
                    delta="+" + str(len(st.session_state.processed_docs)) if st.session_state.processed_docs else None
                )
                st.markdown('</div>', unsafe_allow_html=True)
            
            with metric_col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    "チャット履歴",
                    len(st.session_state.chat_history),
                    delta="+" + str(len(st.session_state.chat_history)) if st.session_state.chat_history else None
                )
                st.markdown('</div>', unsafe_allow_html=True)
            
            with metric_col3:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric(
                    "処理済み",
                    len(st.session_state.processed_docs),
                    delta="+" + str(len(st.session_state.processed_docs)) if st.session_state.processed_docs else None
                )
                st.markdown('</div>', unsafe_allow_html=True)
            
            # 向量存储信息
            st.markdown("**ベクトルストア情報:**")
            if status.get('vector_store_stats'):
                vector_stats = status['vector_store_stats']
                st.json(vector_stats, expanded=False)
            
            # 处理统计
            st.markdown("**処理統計:**")
            if status.get('processing_stats'):
                process_stats = status['processing_stats']
                st.json(process_stats, expanded=False)
    
    with col2:
        st.markdown('<h3 class="sub-header">📊 使用状況グラフ</h3>', unsafe_allow_html=True)
        
        # 示例图表
        if st.session_state.chat_history:
            # 创建查询时间分布图
            times = [chat['timestamp'] for chat in st.session_state.chat_history]
            time_counts = pd.Series(times).value_counts().sort_index()
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=time_counts.index,
                y=time_counts.values,
                mode='lines+markers',
                name='質問数',
                line=dict(color='#2563EB', width=3),
                marker=dict(size=8)
            ))
            
            fig.update_layout(
                title='質問時間分布',
                xaxis_title='時間',
                yaxis_title='質問数',
                template='plotly_white',
                height=300
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # 系统健康状态
        st.markdown("**システム健康状態:**")
        connected, _ = check_backend_connection()
        
        if connected:
            st.markdown('<div class="success-box">✅ すべてのシステムは正常に動作しています</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-box">⚠️ バックエンドへの接続に問題があります</div>', unsafe_allow_html=True)

# 标签页4: 设置
with tab4:
    st.markdown('<h3 class="sub-header">⚙️ システム設定</h3>', unsafe_allow_html=True)
    
    with st.form("settings_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**API設定**")
            api_url = st.text_input(
                "バックエンドURL",
                value=BACKEND_URL,
                help="FastAPIバックエンドのURL"
            )
            
            edinet_api_key = st.text_input(
                "EDINET APIキー",
                type="password",
                help="EDINET APIにアクセスするためのキー"
            )
            
            chunk_size = st.slider(
                "チャンクサイズ",
                min_value=100,
                max_value=1000,
                value=500,
                step=50,
                help="テキスト分割時のチャンクサイズ"
            )
        
        with col2:
            st.markdown("**表示設定**")
            
            theme = st.selectbox(
                "テーマ",
                ["Light", "Dark", "System Default"]
            )
            
            page_size = st.selectbox(
                "ページサイズ",
                [10, 25, 50, 100],
                index=1,
                help="一度に表示するアイテム数"
            )
            
            auto_refresh = st.checkbox(
                "自動更新",
                value=True,
                help="定期的にシステム状態を自動更新"
            )
            
            if auto_refresh:
                refresh_interval = st.slider(
                    "更新間隔（秒）",
                    min_value=10,
                    max_value=300,
                    value=60,
                    step=10
                )
        
        if st.form_submit_button("💾 設定を保存", use_container_width=True):
            # 这里可以添加保存设置的逻辑
            st.success("設定を保存しました（デモモード）")
            st.info("実際の実装では、設定をデータベースまたは設定ファイルに保存します。")

# 页脚
st.markdown("---")
footer_col1, footer_col2, footer_col3 = st.columns(3)
with footer_col1:
    st.markdown("**バージョン:** 1.0.0")
with footer_col2:
    st.markdown("**最終更新:** " + datetime.now().strftime("%Y-%m-%d %H:%M"))
with footer_col3:
    st.markdown("**ステータス:** " + ("🟢 オンライン" if connected else "🔴 オフライン"))