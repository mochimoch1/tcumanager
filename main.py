import os
import pandas as pd
import streamlit as st
import gspread
import time
import sys
import json
from datetime import datetime
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# LINE API 関連
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)

# 以前作成されたスクレイピングモジュール
from scraper import get_webclass_data

# .envファイルの読み込み（ローカル実行用）
load_dotenv()

class AssignmentManager:
    """
    Google Sheets と連携して課題データを管理するクラス。
    クラウド（st.secrets）とローカルを自動判別し、
    LINE通知フラグや優先度スコアを保持したまま高速に動作する。
    """
    def __init__(self, spreadsheet_name="to the top"):
        # カラム定義（オリジナルの構成を維持）
        self.cols = ["24h通知済", "3h通知済", "科目名", "課題内容", "締切日時", "成績重み(%)", "見積もり工数(h)", "ステータス", "優先スコア"]
        self.scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # --- 🛡️ ハイブリッド認証ロジック ---
        try:
            if "gcp_service_account" in st.secrets:
                # クラウド環境：Streamlit Secrets から読み込み
                creds_info = dict(st.secrets["gcp_service_account"])
                self.creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, self.scope)
            else:
                raise KeyError
        except (FileNotFoundError, KeyError, Exception):
            # ローカル環境：プロジェクト直下の json ファイルを使用
            json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service_account.json')
            if os.path.exists(json_path):
                self.creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, self.scope)
            else:
                self.creds = None
                print("❌ 認証ファイルが見つかりません。")

        if self.creds:
            self.client = gspread.authorize(self.creds)
            try:
                self.sheet = self.client.open(spreadsheet_name).get_worksheet(0)
                self._ensure_columns()
            except Exception as e:
                print(f"❌ スプレッドシート接続エラー: {e}")

    def _ensure_columns(self):
        """1行目のヘッダーが存在するか確認し、なければ作成する"""
        header = self.sheet.row_values(1)
        if not header:
            self.sheet.insert_row(self.cols, 1)

    def get_all_data(self):
        data = self.sheet.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            # 一旦文字列として保持し、変換に成功したものだけ上書きする
            raw_deadlines = df['締切日時'].copy()
            df['締切日時'] = pd.to_datetime(df['締切日時'], errors='coerce')
            # 解析失敗(NaT)した場所は、元の文字列を戻す
            df['締切日時'] = df['締切日時'].fillna(raw_deadlines)
            
            df['科目名'] = df['科目名'].astype(str).str.strip()
            df['課題内容'] = df['課題内容'].astype(str).str.strip()
            if 'ステータス' in df.columns:
                df['ステータス'] = df['ステータス'].astype(str).str.strip()
        return df

    def update_all_data(self, df):
        """全データを安全に一括上書き（データ消失防止版）"""
        temp_df = df.copy()
        # Google Sheets に送れる形式（文字列）に変換
        if '締切日時' in temp_df.columns:
            temp_df['締切日時'] = temp_df['締切日時'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # NaN や NaT を空文字に置換し、型を文字列に統一
        df_safe = temp_df[self.cols].fillna('').astype(str).replace('NaT', '')
        data_to_write = [self.cols] + df_safe.values.tolist()
        
        self.sheet.clear()
        try:
            self.sheet.update(values=data_to_write, range_name='A1')
        except TypeError:
            self.sheet.update('A1', data_to_write)

    def update_single_cell(self, row_index, column_name, new_value):
        """【高速版】特定のセルのみをピンポイントで更新する（完了ボタン等で使用）"""
        try:
            if column_name not in self.cols: return False
            col_idx = self.cols.index(column_name) + 1
            actual_row = int(row_index) + 2 # インデックス0始まり + ヘッダー分1
            self.sheet.update_cell(actual_row, col_idx, str(new_value))
            return True
        except Exception as e:
            print(f"⚠️ 高速更新失敗: {e}")
            return False

    def is_duplicate(self, new_item):
        """既存の課題と重複していないか確認"""
        df = self.get_all_data()
        if df.empty: return False
        new_subject = str(new_item.get('科目名', '')).strip()
        new_content = str(new_item.get('課題内容', '')).strip()
        match = df[(df['科目名'] == new_subject) & (df['課題内容'] == new_content)]
        return not match.empty

    def add_assignment(self, data_dict):
        row_data = []
        for col in self.cols:
            if col in data_dict:
                row_data.append(data_dict[col])
            elif "通知済" in col:
                row_data.append(False)
            elif any(x in col for x in ["重み", "工数", "スコア"]):
                row_data.append(0)
            elif col == "締切日時":
                row_data.append("") # 締切がない場合は空文字にする
            else:
                row_data.append("未着手")
        self.sheet.append_row([str(x) for x in row_data])

    def sync_with_latest_data(self, latest_assignments):
        """WebClassから消えた未着手課題を自動的に完了にする"""
        if not latest_assignments: return
        df = self.get_all_data()
        if df.empty: return
        
        latest_set = set((str(item['科目名']).strip(), str(item['課題内容']).strip()) for item in latest_assignments)
        updated = False
        for index, row in df.iterrows():
            if row['ステータス'] == '未着手':
                if (row['科目名'], row['課題内容']) not in latest_set:
                    df.at[index, 'ステータス'] = '完了'
                    updated = True
        if updated:
            self.update_all_data(df)

    def process_and_get_notifications(self):
        """スコア計算とLINE通知用メッセージの生成（一括更新を伴う）"""
        df = self.get_all_data()
        if df.empty: return pd.DataFrame(), []
        
        now = datetime.now()
        alerts = []

        def update_row(row):
            if row['ステータス'] != '未着手':
                row['優先スコア'] = 0
                return row
            
            if pd.isnull(row['締切日時']):
                row['優先スコア'] = 0
                return row
                
            rem_h = (row['締切日時'] - now).total_seconds() / 3600
            
            # 優先スコア計算ロジック（オリジナルのまま）
            row['優先スコア'] = (row['成績重み(%)'] * row['見積もり工数(h)']) / rem_h if rem_h > 0 else 999
            
            # 通知判定
            if 0 < rem_h <= 3 and not str(row['3h通知済']).upper() == 'TRUE':
                alerts.append(f"⏰ 残り3h: {row['課題内容']}")
                row['3h通知済'] = True
            elif 0 < rem_h <= 24 and not str(row['24h通知済']).upper() == 'TRUE':
                alerts.append(f"📅 残り24h: {row['課題内容']}")
                row['24h通知済'] = True
            return row

        df = df.apply(update_row, axis=1)
        self.update_all_data(df)
        
        incomplete = df[df['ステータス'] == '未着手'].copy()
        if not incomplete.empty:
            incomplete = incomplete.sort_values('優先スコア', ascending=False)
        
        return incomplete, alerts

def main():
    manager = AssignmentManager(spreadsheet_name="to the top")
    
    print("📡 WebClassから情報を取得中...")
    # scraper.py の get_webclass_data を実行
    new_assignments, course_list = get_webclass_data()
    
    # 既存課題との同期（消えた課題を完了にする）
    manager.sync_with_latest_data(new_assignments)

    added_count = 0
    for item in new_assignments:
        item['科目名'] = str(item.get('科目名', '')).strip()
        item['課題内容'] = str(item.get('課題内容', '')).strip()
        
        if not manager.is_duplicate(item):
            manager.add_assignment(item)
            added_count += 1
    
    print(f"✅ {added_count}件の新規課題を追加。スコア更新中...")
    incomplete_tasks, alert_messages = manager.process_and_get_notifications()

    # LINE メッセージ構築
    final_messages = []
    if alert_messages:
        final_messages.extend(alert_messages)

    if not incomplete_tasks.empty:
        task_list_text = "📝 未完了の課題リスト\n----------------------\n"
        for _, task in incomplete_tasks.iterrows():
            deadline_str = task['締切日時'].strftime('%m/%d %H:%M') if pd.notnull(task['締切日時']) else "不明"
            task_list_text += f"▼ {task['科目名']}\n   {task['課題内容']}\n   ({deadline_str})\n\n"
        task_list_text += f"合計: {len(incomplete_tasks)}件"
        final_messages.append(task_list_text)

    # LINE 送信
    line_token = os.getenv('LINE_ACCESS_TOKEN')
    line_user_id = os.getenv('LINE_USER_ID')
    
    if final_messages and line_token and line_user_id:
        config = Configuration(access_token=line_token)
        with ApiClient(config) as api_client:
            api = MessagingApi(api_client)
            for msg in final_messages:
                try:
                    api.push_message(PushMessageRequest(
                        to=line_user_id, 
                        messages=[TextMessage(text=msg)]
                    ))
                except Exception as e:
                    print(f"⚠️ LINE送信失敗: {e}")
        print(f"📢 {len(final_messages)}件の通知を送信しました。")
    else:
        print("📭 送信すべき通知はありません、または設定が不足しています。")

if __name__ == "__main__":
    main()