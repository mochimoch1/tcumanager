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
    /* 既存の style タグの最後に追加 */
    .mission-card-selected {
        border: 2px solid #fdcb6e !important; /* 黄金の枠線 */
        box-shadow: 0 0 20px rgba(253, 203, 110, 0.4) !important; /* 発光エフェクト */
        transform: scale(1.02); /* わずかに浮かび上がらせる */
    }
</style>
""", unsafe_allow_html=True)

# --- 2. データ初期化 ---
manager = AssignmentManager(spreadsheet_name="to the top")

def get_credit_type(course_name):
    spec_keywords = ["ヒューマン", "コンピュータ", "情報", "プログラミング", "計算", "アルゴリズム", "AI", "深層学習", "計算工学"]
    for word in spec_keywords:
        if word in str(course_name): return "専門 (2単位)"
    return "基礎/教養 (1単位)"
# 既存の 'master_df' 初期化付近に追加
if 'selected_ids' not in st.session_state:
    st.session_state.selected_ids = set() # 選択したカードの番号を記録する箱
if 'bulk_mode' not in st.session_state:
    st.session_state.bulk_mode = False # 一括選択モードがONかOFFか
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
    
    # 修正点：toggleの状態をセッションに直結
    st.session_state.bulk_mode = st.toggle("🛠️ 一括選択モード", value=st.session_state.bulk_mode)
    
    if st.session_state.bulk_mode:
        # ここで現在の選択数を直接計算して表示
        selected_count = len(st.session_state.selected_ids)
        if selected_count > 0:
            st.warning(f"🎯 {selected_count} 件選択中")
            if st.button("🔥 選択したミッションを全完了", type="primary", use_container_width=True):
                # 【重要】ここでの一括処理を確実に実行
                for idx in list(st.session_state.selected_ids):
                    st.session_state.master_df.at[idx, 'ステータス'] = '完了'
                    st.session_state.pending_indices.add(idx)
                
                # 状態をリセット
                st.session_state.selected_ids.clear()
                st.session_state.bulk_mode = False
                st.toast("一括完了処理を予約しました。クラウドへ保存してください。")
                st.rerun() # ここは全画面リロードして状態を確定させる
        else:
            st.info("カードの「➕ 選択」を押してください")
    # 保存ボタンの条件を「pending_indicesがある時」にする
    if len(st.session_state.pending_indices) > 0:
        st.error(f"⚠️ {len(st.session_state.pending_indices)} 件の未保存変更")
    if st.button("🚀 クラウドに保存", type="primary", use_container_width=True):
        with st.spinner("スプレッドシートを更新中..."):
            # master_df を丸ごと上書き保存
            manager.update_all_data(st.session_state.master_df)
            st.session_state.pending_indices.clear()
            st.success("クラウドとの同期が完了しました！")
            time.sleep(1)
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

    # --- 1. 達成度計算 ---
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

    # --- 2. フィルタリングとソート ---
    display_df = df[
        (df['ステータス'].isin(status_filter)) &
        (df['科目名'].isin(subject_filter))
    ]
    display_df = display_df.sort_values(by=sort_on, ascending=is_ascending)

    if display_df.empty:
        st.info("表示するミッションがありません。")
        return

    # --- 3. カード描画ループ ---
    chunks = [display_df.iloc[i:i + 6] for i in range(0, len(display_df), 6)]
    for chunk in chunks:
        cols = st.columns(6)
        for i, (idx, row) in enumerate(chunk.iterrows()):
            with cols[i % 6]: # 列の中に描画内容を収める
                # 先に変数を定義する（エラー防止）
                aura = "aura-specialized" if "専門" in str(row.get('単位種別', '')) else "aura-foundation"
                is_done = (row['ステータス'] == '完了')
                is_selected = idx in st.session_state.selected_ids
                selected_class = "mission-card-selected" if is_selected else ""
                
                # 難易度の星（⚡）
                try:
                    stars = "⚡" * int(row.get('難易度', 1))
                except:
                    stars = "⚡"

                # 💳 カードの見た目（HTML）を1回で出力
                st.markdown(f"""
                <div class="mission-card {aura if not is_done else ''} {selected_class}" 
                     style="{ 'opacity:0.4; filter:grayscale(1);' if is_done else '' }">
                    <div>
                        <div class="status-badge">{row['科目名']}</div>
                        <div style="color:white; font-weight:bold; margin-top:10px; font-size:0.95rem;">{row['課題内容']}</div>
                        <div class="difficulty-stars">Rank: {stars}</div>
                    </div>
                    <div style="font-size:0.75rem; color:#aaa; margin-top:auto;">
                        ⏰ {row['締切日時'].strftime('%m/%d %H:%M') if pd.notnull(row['締切日時']) else '未定'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 🖱️ ボタンの役割をモードによって切り替え
                if st.session_state.bulk_mode:
                    # 【一括選択モード】
                    label = "✅ 解除" if is_selected else "➕ 選択"
                    if st.button(label, key=f"sel_{idx}", use_container_width=True):
                        if is_selected:
                            st.session_state.selected_ids.remove(idx)
                        else:
                            st.session_state.selected_ids.add(idx)
                        st.rerun(scope="fragment")
                else:
                    # 【通常モード】
                    if not is_done:
                        if st.button("COMPLETE", key=f"btn_d_{idx}", use_container_width=True):
                            st.session_state.master_df.at[idx, 'ステータス'] = '完了'
                            st.session_state.pending_indices.add(idx)
                            st.rerun(scope="fragment")
                    else:
                        if st.button("↺ UNDO", key=f"btn_u_{idx}", use_container_width=True):
                            st.session_state.master_df.at[idx, 'ステータス'] = '未着手'
                            st.session_state.pending_indices.add(idx)
                            st.rerun(scope="fragment")

render_mission_board()