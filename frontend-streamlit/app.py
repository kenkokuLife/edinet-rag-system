import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

# 配置
BACKEND_URL = "http://rag-app:8000/api/v1"

# 页面设置
st.set_page_config(
    page_title="EDINET RAG システム",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"  # サイドバーを最初は閉じる
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        color: #1E3A8A;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .step-header {
        font-size: 1.3rem;
        color: #1E3A8A;
        margin: 1rem 0 0.5rem 0;
        padding: 0.5rem;
        background: linear-gradient(90deg, #EEF2FF 0%, transparent 100%);
        border-left: 4px solid #2563EB;
    }
    .help-box {
        background-color: #F0F9FF;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #BAE6FD;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #10B981;
    }
    .workflow-step {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        border-left: 4px solid #2563EB;
    }
    .workflow-step-inactive {
        background: #F9FAFB;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px dashed #D1D5DB;
        margin: 0.5rem 0;
        opacity: 0.7;
    }
    .current-step {
        background: #EEF2FF;
        padding: 0.5rem 1rem;
        border-radius: 2rem;
        display: inline-block;
        font-weight: bold;
        color: #2563EB;
    }
</style>
""", unsafe_allow_html=True)

# 初始化会话状态
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'processed_docs' not in st.session_state:
    st.session_state.processed_docs = []
if 'edinet_results' not in st.session_state:
    st.session_state.edinet_results = None
if 'current_step' not in st.session_state:
    st.session_state.current_step = 1

# ========== API関数 ==========
def check_backend():
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=5)
        return response.status_code == 200
    except:
        return False

def search_edinet(date_from=None, date_to=None, company_name=None, limit=100):
    try:
        params = {"limit": limit}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if company_name:
            params["company_name"] = company_name
        response = requests.get(f"{BACKEND_URL}/search/edinet", params=params, timeout=120)
        if response.status_code == 200:
            return response.json()
        return {"count": 0, "documents": [], "error": f"エラー: {response.status_code}"}
    except Exception as e:
        return {"count": 0, "documents": [], "error": str(e)}

def process_document(doc_id):
    try:
        response = requests.post(f"{BACKEND_URL}/documents/process", json={"doc_ids": [doc_id]}, timeout=60)
        return response.status_code == 200
    except:
        return False

def query_rag(question, company_filter=None):
    try:
        payload = {"question": question}
        if company_filter:
            payload["company_filter"] = company_filter
        response = requests.post(f"{BACKEND_URL}/query", json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()
        return {"answer": "エラーが発生しました", "sources": []}
    except Exception as e:
        return {"answer": f"接続エラー: {str(e)}", "sources": []}

def view_document(doc_id):
    try:
        response = requests.get(f"{BACKEND_URL}/documents/{doc_id}/view", timeout=60)
        if response.status_code == 200:
            return response.json()
        return {"status": "error", "error": f"エラー: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ========== ヘッダー ==========
st.markdown('<h1 class="main-header">📊 EDINET 有価証券報告書 RAG システム</h1>', unsafe_allow_html=True)

# 接続状態チェック
if not check_backend():
    st.error("⚠️ バックエンドに接続できません。システムが起動しているか確認してください。")
    st.stop()

# ========== ワークフローガイド ==========
st.markdown("---")

# 現在のステップを表示
step_names = ["① 報告書を検索", "② 処理（登録）", "③ 質問する"]
cols = st.columns(3)
for i, (col, name) in enumerate(zip(cols, step_names), 1):
    with col:
        if i == st.session_state.current_step:
            st.markdown(f'<div class="current-step">👉 {name}</div>', unsafe_allow_html=True)
        elif i < st.session_state.current_step:
            st.markdown(f"✅ {name}")
        else:
            st.markdown(f"⬜ {name}")

st.markdown("---")

# ========== STEP 1: 検索 ==========
st.markdown('<div class="step-header">STEP 1: 有価証券報告書を検索</div>', unsafe_allow_html=True)

with st.container():
    st.markdown("""
    <div class="help-box">
    💡 <b>使い方:</b> 会社名を入力して検索ボタンを押してください。日付での絞り込みも可能です。
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        company_name = st.text_input(
            "🏢 会社名（部分一致）",
            placeholder="例: トヨタ、ソニー、任天堂",
            key="search_company"
        )

    with col2:
        use_date = st.checkbox("📅 日付で絞り込む", value=False)

    with col3:
        search_limit = st.selectbox("表示件数", [20, 50, 100], index=1)

    if use_date:
        date_col1, date_col2 = st.columns(2)
        with date_col1:
            date_from = st.date_input("開始日", value=datetime.now() - timedelta(days=30))
        with date_col2:
            date_to = st.date_input("終了日", value=datetime.now())

        days_diff = (date_to - date_from).days
        if days_diff > 60:
            st.warning(f"⚠️ 日付範囲が{days_diff}日です。最大60日間のみ検索されます。")
    else:
        date_from = None
        date_to = None

    if st.button("🔍 検索する", type="primary", use_container_width=True):
        if not company_name and not use_date:
            st.warning("会社名か日付のどちらかを入力してください")
        else:
            with st.spinner("EDINETを検索中..."):
                results = search_edinet(
                    date_from=date_from.strftime("%Y-%m-%d") if date_from else None,
                    date_to=date_to.strftime("%Y-%m-%d") if date_to else None,
                    company_name=company_name if company_name else None,
                    limit=search_limit
                )
                st.session_state.edinet_results = results

                if results.get("documents"):
                    st.session_state.current_step = 2
                    st.success(f"✅ {len(results['documents'])}件の報告書が見つかりました！下の一覧から処理するものを選んでください。")
                elif results.get("error"):
                    st.error(f"エラー: {results['error']}")
                else:
                    st.warning("該当する報告書が見つかりませんでした。検索条件を変更してください。")

# ========== STEP 2: 処理（登録） ==========
st.markdown('<div class="step-header">STEP 2: 報告書を処理（RAGに登録）</div>', unsafe_allow_html=True)

if st.session_state.edinet_results and st.session_state.edinet_results.get("documents"):
    documents = st.session_state.edinet_results["documents"]

    st.markdown("""
    <div class="help-box">
    💡 <b>使い方:</b> 検索結果から報告書を選び、「処理する」ボタンで登録します。登録後に質問できます。
    </div>
    """, unsafe_allow_html=True)

    # 文档表格
    df_data = []
    for doc in documents:
        df_data.append({
            "選択": False,
            "会社名": doc.get('company_name', ''),
            "提出日": doc.get('submit_date', '')[:10] if doc.get('submit_date') else '',
            "文書ID": doc.get('doc_id', ''),
            "処理済": "✅" if doc.get('doc_id') in st.session_state.processed_docs else "❌"
        })

    df = pd.DataFrame(df_data)

    # インタラクティブテーブル
    st.dataframe(
        df[["会社名", "提出日", "文書ID", "処理済"]],
        use_container_width=True,
        hide_index=True,
        height=250
    )

    # 操作エリア
    col1, col2 = st.columns([3, 1])

    with col1:
        selected_doc_id = st.selectbox(
            "処理する報告書を選択",
            options=[doc.get('doc_id', '') for doc in documents],
            format_func=lambda x: next(
                (f"{d.get('company_name', '')} ({d.get('submit_date', '')[:10]})"
                 for d in documents if d.get('doc_id') == x), x
            )
        )

    with col2:
        st.write("")  # スペーサー
        st.write("")
        process_btn = st.button("📥 処理する", type="primary", use_container_width=True)

    if process_btn:
        if selected_doc_id in st.session_state.processed_docs:
            st.info("この報告書は既に処理済みです。STEP 3で質問できます。")
        else:
            with st.spinner(f"処理中... ({selected_doc_id})"):
                if process_document(selected_doc_id):
                    st.session_state.processed_docs.append(selected_doc_id)
                    st.session_state.current_step = 3
                    st.success("✅ 処理完了！STEP 3で質問してください。")
                else:
                    st.error("処理に失敗しました")

    # PDF確認リンク
    with st.expander("📄 報告書の内容を確認（PDF）"):
        if selected_doc_id:
            pdf_url = f"http://localhost:8000/api/v1/documents/{selected_doc_id}/pdf"
            st.markdown(f"[📥 PDFをダウンロード]({pdf_url})")

            if st.button("内容をプレビュー"):
                with st.spinner("取得中..."):
                    result = view_document(selected_doc_id)
                    if result.get('status') == 'success':
                        st.text_area("プレビュー", result.get('content_preview', '')[:3000], height=200, disabled=True)
                    else:
                        st.warning(result.get('message', result.get('error', 'プレビューできません')))

else:
    st.markdown("""
    <div class="workflow-step-inactive">
    ⬆️ まずSTEP 1で報告書を検索してください
    </div>
    """, unsafe_allow_html=True)

# ========== STEP 3: 質問 ==========
st.markdown('<div class="step-header">STEP 3: 報告書について質問する</div>', unsafe_allow_html=True)

if st.session_state.processed_docs:
    st.markdown(f"""
    <div class="help-box">
    💡 <b>使い方:</b> 処理済みの報告書（{len(st.session_state.processed_docs)}件）に対して質問できます。
    </div>
    """, unsafe_allow_html=True)

    # 質問入力
    question = st.text_area(
        "質問を入力",
        placeholder="例:\n・売上高はいくらですか？\n・主な事業リスクを教えてください\n・当期純利益の前期比は？",
        height=100
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        company_filter = st.text_input(
            "会社名で絞り込み（任意）",
            placeholder="特定の会社に限定する場合は入力"
        )
    with col2:
        st.write("")
        st.write("")
        ask_btn = st.button("🚀 質問する", type="primary", use_container_width=True)

    if ask_btn:
        if not question:
            st.warning("質問を入力してください")
        else:
            with st.spinner("回答を生成中..."):
                result = query_rag(question, company_filter if company_filter else None)

                # 回答表示
                st.markdown("### 📝 回答")
                st.markdown(f'<div class="success-box">{result.get("answer", "回答を取得できませんでした")}</div>', unsafe_allow_html=True)

                # ソース表示
                if result.get("sources"):
                    with st.expander(f"📚 参照元（{len(result['sources'])}件）"):
                        for i, source in enumerate(result['sources'], 1):
                            st.markdown(f"**{i}. {source.get('company', '不明')}** (類似度: {source.get('score', 0):.1%})")
                            st.caption(source.get('text', '')[:300] + "...")
                            st.markdown("---")

                # 履歴に追加
                st.session_state.chat_history.append({
                    "question": question,
                    "answer": result.get("answer", ""),
                    "timestamp": datetime.now().strftime("%H:%M")
                })

    # 履歴表示
    if st.session_state.chat_history:
        with st.expander(f"📜 質問履歴（{len(st.session_state.chat_history)}件）"):
            for chat in reversed(st.session_state.chat_history[-10:]):
                st.markdown(f"**Q ({chat['timestamp']}):** {chat['question']}")
                st.markdown(f"**A:** {chat['answer'][:200]}...")
                st.markdown("---")

else:
    st.markdown("""
    <div class="workflow-step-inactive">
    ⬆️ まずSTEP 2で報告書を処理してください
    </div>
    """, unsafe_allow_html=True)

# ========== サイドバー（詳細設定） ==========
with st.sidebar:
    st.markdown("## ⚙️ 詳細設定")

    st.markdown("### 処理状況")
    st.metric("処理済み報告書", len(st.session_state.processed_docs))
    st.metric("質問回数", len(st.session_state.chat_history))

    if st.session_state.processed_docs:
        st.markdown("**処理済みID:**")
        for doc_id in st.session_state.processed_docs[-5:]:
            st.code(doc_id[:15] + "...")

    st.markdown("---")

    if st.button("🗑️ 履歴をクリア"):
        st.session_state.chat_history = []
        st.session_state.processed_docs = []
        st.session_state.edinet_results = None
        st.session_state.current_step = 1
        st.rerun()

    st.markdown("---")
    st.caption("バージョン: 2.0.0")
    st.caption(f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ========== フッター ==========
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #6B7280; font-size: 0.9rem;">
    📊 EDINET RAG System | 有価証券報告書をAIで分析
</div>
""", unsafe_allow_html=True)
