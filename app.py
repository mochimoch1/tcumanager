import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys
import subprocess
import time
from main import AssignmentManager

# ページ設定
st.set_page_config(page_title="TCU Mission Control", layout="wide")

# --- 1. デザイン定義（達成度ゲージ & 難易度バッジ追加） ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #1e1e2f 0%, #2d3436 100%); }
    
    /* 達成度プログレスバーの外枠 */
    .progress-container {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        height: 24px;
        width: 100%;
        margin-bottom: 25px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    /* 達成度プログレスバーの中身 */
    .progress-bar {
        background: linear-gradient(90deg, #6c5ce7, #a29bfe);
        height: 100%;
        transition: width 0.5s ease-in-out;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        font-size: 0.8rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    }

    .mission-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(15px);
        border-radius: 15px 15px 0 0;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-bottom: 2px dashed rgba(255, 255, 255, 0.2);
        height: 200px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .aura-specialized { border-left: 5px solid #6c5ce7; box-shadow: 0 0 15px rgba(108, 92, 231, 0.3); }
    .aura-foundation { border-left: 5px solid #55efc4; box-shadow: 0 0 15px rgba(85, 239, 196, 0.2); }
    .status-badge { font-size: 0.7rem; background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 10px; color: #fdcb6e; }
    .difficulty-stars { color: #fab1a0; font-size: 0.8rem; margin-top: 5px; }
    .stButton > button { border-radius: 0 0 15px 15px !important; height: 40px !important; font-weight: bold !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. データ初期化 ---
manager = AssignmentManager(spreadsheet_name="to the top")

def get_credit_type(course_name):
    spec_keywords = ["ヒューマン", "コンピュータ", "情報", "プログラミング", "計算", "アルゴリズム", "AI", "深層学習", "計算工学"]
    for word in spec_keywords:
        if word in str(course_name): return "専門 (2単位)"
    return "基礎/教養 (1単位)"

if 'master_df' not in st.session_state:
    with st.spinner("データをロード中..."):
        df = manager.get_all_data()
        if not df.empty:
            df['締切日時'] = pd.to_datetime(df['締切日時'], errors='coerce')
            df['単位種別'] = df['科目名'].apply(get_credit_type)
            # 難易度が未設定の場合は「1」にする
            if '難易度' not in df.columns: df['難易度'] = 1
            df['難易度'] = df['難易度'].fillna(1)
        st.session_state.master_df = df

if 'pending_indices' not in st.session_state:
    st.session_state.pending_indices = set()

# --- 3. サイドバー (Console) ---
with st.sidebar:
    st.title("⚙️ Tactical Console")
    
    # 保存ボタン
    if st.session_state.pending_indices:
        st.error(f"⚠️ {len(st.session_state.pending_indices)} 件を保存してください")
        if st.button("🚀 クラウドに保存", type="primary", use_container_width=True):
            manager.update_all_data(st.session_state.master_df)
            st.session_state.pending_indices.clear()
            st.toast("☁️ 同期完了")
            st.rerun()
    
    st.divider()

    # フィルタ
    all_subjects = sorted(st.session_state.master_df['科目名'].unique().tolist()) if not st.session_state.master_df.empty else []
    subject_filter = st.multiselect("科目名", all_subjects, default=all_subjects)
    status_filter = st.multiselect("ステータス", ["未着手", "着手", "完了"], default=["未着手", "着手"])
    
    st.divider()

    # 並び替え（ソート）機能強化
    sort_on = st.selectbox("並び替え基準", ["優先スコア", "締切日時", "難易度", "科目名"])
    sort_order = st.radio("順序", ["昇順 (低/近/A-Z)", "降順 (高/遠/Z-A)"], horizontal=True)
    is_ascending = (sort_order == "昇順 (低/近/A-Z)")

    st.divider()

    # WebClass同期ボタン
    is_cloud = False
    try:
        if "gcp_service_account" in st.secrets: is_cloud = True
    except: pass
    if not is_cloud:
        if st.button("📥 WebClass 同期 (Local)", use_container_width=True):
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "main.py")])
            del st.session_state.master_df
            st.rerun()

# --- 4. メインボード描画 (達成度表示含む) ---
st.title("🛡️ Mission Control")

@st.fragment
def render_mission_board():
    df = st.session_state.master_df
    if df.empty: return

    # --- 達成度計算 ---
    total_tasks = len(df)
    completed_tasks = len(df[df['ステータス'] == '完了'])
    achievement_rate = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    # 達成度ゲージの表示
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-weight: bold; color: #eee;">
        <span>🏆 Total Achievement</span>
        <span>{achievement_rate}% ({completed_tasks}/{total_tasks})</span>
    </div>
    <div class="progress-container">
        <div class="progress-bar" style="width: {achievement_rate}%;">{"DONE!" if achievement_rate == 100 else ""}</div>
    </div>
    """, unsafe_allow_html=True)

    # フィルタリング
    display_df = df[
        (df['ステータス'].isin(status_filter)) &
        (df['科目名'].isin(subject_filter))
    ]

    # 並び替え
    display_df = display_df.sort_values(by=sort_on, ascending=is_ascending)

    if display_df.empty:
        st.info("表示するミッションがありません。")
        return

    # 6列描画
    chunks = [display_df.iloc[i:i + 6] for i in range(0, len(display_df), 6)]
    for chunk in chunks:
        cols = st.columns(6)
        for i, (idx, row) in enumerate(chunk.iterrows()):
            with cols[i]:
                aura = "aura-specialized" if "専門" in str(row['単位種別']) else "aura-foundation"
                is_done = (row['ステータス'] == '完了')
                
                # 難易度を★で表示
                try:
                    diff_val = int(row['難易度'])
                    stars = "⚡" * diff_val
                except:
                    stars = "⚡"

                st.markdown(f"""
                <div class="mission-card {aura if not is_done else ''}" style="{ 'opacity:0.4; filter:grayscale(1);' if is_done else '' }">
                    <div>
                        <div class="status-badge">{row['科目名']}</div>
                        <div style="color:white; font-weight:bold; margin-top:10px; font-size:0.95rem;">{row['課題内容']}</div>
                        <div class="difficulty-stars">Rank: {stars}</div>
                    </div>
                    <div style="font-size:0.75rem; color:#aaa; margin-top:auto;">⏰ {row['締切日時'].strftime('%m/%d %H:%M') if pd.notnull(row['締切日時']) else '未定'}</div>
                </div>
                """, unsafe_allow_html=True)
                
                if not is_done:
                    if st.button("COMPLETE", key=f"btn_d_{idx}", use_container_width=True):
                        st.session_state.master_df.at[idx, 'ステータス'] = '完了'
                        st.session_state.pending_indices.add(idx)
                        st.rerun(scope="fragment") # バーとリストを即時更新
                else:
                    if st.button("↺ UNDO", key=f"btn_u_{idx}", use_container_width=True):
                        st.session_state.master_df.at[idx, 'ステータス'] = '未着手'
                        st.session_state.pending_indices.add(idx)
                        st.rerun(scope="fragment")

render_mission_board()