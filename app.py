import streamlit as st
import pandas as pd
import os
import sys
import subprocess
import time
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(page_title="TCU Mission Control", layout="wide")

# --- 1. デザイン定義 (シネマ演出 & 物理サイズ死守) ---
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #1e1e2f 0%, #2d3436 100%); }
    
    /* 物理サイズ固定 (320px * 200px 黄金比) */
    [data-testid="stHorizontalBlock"] { gap: 15px !important; margin-bottom: 25px; }
    [data-testid="column"] { min-width: 320px !important; max-width: 320px !important; flex: 0 0 320px !important; }

    /* チケット風カード本体 */
    .mission-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(15px);
        border-radius: 15px 15px 0 0;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-bottom: 2px dashed rgba(255, 255, 255, 0.2);
        height: 180px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
        transition: 0.4s;
    }

    /* 分断アニメーション */
    @keyframes ticket-tear-top {
        0% { transform: translateY(0) rotate(0deg); opacity: 1; }
        100% { transform: translateY(-150px) rotate(-8deg); opacity: 0; filter: blur(10px); }
    }
    .tear-top { animation: ticket-tear-top 0.7s forwards ease-in; }

    @keyframes ticket-tear-bottom {
        0% { transform: translateY(0) rotate(0deg); opacity: 1; }
        100% { transform: translateY(150px) rotate(8deg); opacity: 0; filter: blur(10px); }
    }
    .tear-bottom > div > button { animation: ticket-tear-bottom 0.7s forwards ease-in !important; pointer-events: none; }

    /* ボタン演出：シマー & プレス */
    @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
    .stButton > button {
        border-radius: 0 0 15px 15px !important;
        background: linear-gradient(90deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.05) 100%) !important;
        background-size: 200% 100% !important;
        height: 45px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        font-weight: bold !important;
        color: #eee !important;
        transition: 0.2s !important;
    }
    .stButton > button:hover { animation: shimmer 1.5s infinite; color: #55efc4 !important; border-color: rgba(85, 239, 196, 0.5) !important; }
    .stButton > button:active { transform: scale(0.96) translateY(2px) !important; background: rgba(85, 239, 196, 0.3) !important; }

    /* 単位数連動オーラ (専門2単位:紫 / 基礎1単位:緑) */
    .aura-specialized { box-shadow: 0 0 20px rgba(108, 92, 231, 0.4); border-left: 5px solid #6c5ce7; }
    .aura-foundation { box-shadow: 0 0 20px rgba(85, 239, 196, 0.3); border-left: 5px solid #55efc4; }

    /* 状態別カラー */
    .priority-high { border-top: 6px solid #ff7675; }
    .priority-mid { border-top: 6px solid #fdcb6e; }
    .priority-low { border-top: 6px solid #55efc4; }
    .priority-done { border-top: 6px solid #888; opacity: 0.4; filter: grayscale(1); }

    .mission-title { font-weight: bold; font-size: 1.1rem; color: #fff; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    .status-badge { font-size: 0.7rem; background: rgba(255,255,255,0.15); padding: 3px 10px; border-radius: 12px; color: #fdcb6e; }
</style>
""", unsafe_allow_html=True)

# --- 2. データロード & 単位ロジック ---
base_dir = os.path.dirname(os.path.abspath(__file__))
ASSIGNMENT_FILE = os.path.join(base_dir, "assignments.xlsx")
MAIN_SCRIPT = os.path.join(base_dir, "main.py")

def get_credit_type(course_name):
    # 専門科目は2単位、基礎・外国語は1単位
    spec_keywords = ["ヒューマン", "コンピュータ", "情報", "プログラミング", "計算", "アルゴリズム", "AI", "深層学習", "計算工学"]
    for word in spec_keywords:
        if word in course_name: return "専門 (2単位)"
    return "基礎/教養 (1単位)"

def load_data():
    if os.path.exists(ASSIGNMENT_FILE):
        df = pd.read_excel(ASSIGNMENT_FILE)
        df['締切日時'] = pd.to_datetime(df['締切日時'])
        if 'ステータス' in df.columns:
            df['ステータス'] = df['ステータス'].astype(str).str.strip()
        df['単位種別'] = df['科目名'].apply(get_credit_type)
        return df
    return pd.DataFrame()

df = load_data()

# --- 3. サイドバー：戦術フィルタリング & ソート ---
if "tear_id" not in st.session_state:
    st.session_state.tear_id = None

with st.sidebar:
    st.title("⚙️ Tactical Console")
    
    # 検索・絞り込み
    st.subheader("🔍 フィルタリング")
    
    # 追加: 科目名での絞り込み
    all_subjects = sorted(df['科目名'].unique().tolist()) if not df.empty else []
    subject_filter = st.multiselect("科目名で絞り込み", all_subjects, default=all_subjects)
    
    status_filter = st.multiselect("ステータス", ["未着手", "着手", "完了"], default=["未着手", "着手"])
    credit_filter = st.multiselect("単位種別", ["専門 (2単位)", "基礎/教養 (1単位)"], default=["専門 (2単位)", "基礎/教養 (1単位)"])
    
    st.divider()
    
    # 並び替え
    st.subheader("🔃 並び替え")
    sort_on = st.selectbox("ソート基準", ["優先スコア", "締切日時", "成績重み(%)", "科目名"])
    sort_order = st.radio("順序", ["降順 (高/遠)", "昇順 (低/近)"], horizontal=True)
    ascending = (sort_order == "昇順 (低/近)")

    st.divider()
    
    # Keep Gate & Sync
    st.subheader("📥 Keep Gate")
    keep_input = st.text_area("メモ追加", height=80, placeholder="例: 生チョコの材料を買う")
    if st.button("Add Mission", use_container_width=True):
        if keep_input:
            new_row = {"科目名": "Keep", "課題内容": keep_input, "締切日時": datetime.now(), "成績重み(%)": 0, "ステータス": "未着手", "優先スコア": 0}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(ASSIGNMENT_FILE, index=False); st.rerun()
    
    if st.button("WebClass同期", use_container_width=True):
        subprocess.run([sys.executable, MAIN_SCRIPT]); st.rerun()

# --- 4. メインボード ---
st.title("🛡️ Mission Control")
col_h1, col_h2 = st.columns([2, 1])
with col_h1:
    st.info(f"📍 竹原 洸希 隊員、バイト出撃（21:00〜01:00）お疲れ様でした。深夜の戦績を確認せよ。")

with col_h2:
    if not df.empty:
        done = len(df[df['ステータス'] == '完了'])
        total = len(df)
        progress = done / total if total > 0 else 0
        rank = 'S' if progress >= 0.9 else 'A' if progress >= 0.7 else 'B'
        st.markdown(f"<div style='text-align:center;'><small>RANK</small><br><b style='font-size:2.8rem; color:#fdcb6e; text-shadow: 0 0 15px #fdcb6e;'>{rank}</b><br><small>達成率: {progress*100:.1f}%</small></div>", unsafe_allow_html=True)
        st.progress(progress)

st.divider()

# --- 5. フィルタ・ソート適用後の描画 ---
if not df.empty:
    # フィルタ適用
    display_df = df[df['ステータス'].isin(status_filter)]
    display_df = display_df[display_df['単位種別'].isin(credit_filter)]
    display_df = display_df[display_df['科目名'].isin(subject_filter)] # 科目フィルタ
    
    # ソート適用
    display_df = display_df.sort_values(by=sort_on, ascending=ascending)

    # 1行6枚表示
    if not display_df.empty:
        chunks = [display_df.iloc[i:i + 6] for i in range(0, len(display_df), 6)]
        for chunk in chunks:
            cols = st.columns(6)
            for i, (idx, row) in enumerate(chunk.iterrows()):
                with cols[i]:
                    is_done = (row['ステータス'] == '完了')
                    is_tearing = (st.session_state.tear_id == idx)
                    
                    aura = "aura-specialized" if "専門" in row['単位種別'] else "aura-foundation"
                    p_class = "priority-done" if is_done else ("priority-high" if row['優先スコア'] > 100 else "priority-mid")
                    
                    st.markdown(f"""
                    <div class="mission-card {p_class} {aura if not is_done else ''} {'tear-top' if is_tearing else ''}">
                        <div>
                            <div style="display: flex; justify-content: space-between;">
                                <span class="status-badge">{row['科目名']}</span>
                                <span style="color: #fdcb6e; font-size: 0.8rem;">{int(row['成績重み(%)'])}%</span>
                            </div>
                            <div class="mission-title">{row['課題内容']}</div>
                        </div>
                        <div style="font-size: 0.8rem; opacity: 0.6; margin-top: auto;">⏰ {row['締切日時'].strftime('%m/%d %H:%M')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if is_done:
                        if st.button("↺ UNDO", key=f"u_{idx}", use_container_width=True):
                            df.at[idx, 'ステータス'] = '未着手'; df.to_excel(ASSIGNMENT_FILE, index=False); st.rerun()
                    else:
                        st.markdown(f'<div class="{"tear-bottom" if is_tearing else ""}">', unsafe_allow_html=True)
                        if st.button("COMPLETE", key=f"d_{idx}", use_container_width=True):
                            st.session_state.tear_id = idx; st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("指定されたフィルタに一致する任務はありません。")

# --- 6. アニメーション同期 ---
if st.session_state.tear_id is not None:
    target = st.session_state.tear_id
    df.at[target, 'ステータス'] = '完了'; df.to_excel(ASSIGNMENT_FILE, index=False)
    time.sleep(0.7); st.session_state.tear_id = None; st.balloons(); st.rerun()