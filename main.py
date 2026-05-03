import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

class AssignmentManager:
    """
    Google Sheets と連携して課題データを管理するクラス。
    クラウド（st.secrets）とローカル（service_account.json）を自動判別する。
    """
    def __init__(self, spreadsheet_name="TCU-Mission-Control"):
        self.scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # --- 環境判別ロジック ---
        if "gcp_service_account" in st.secrets:
            # クラウド環境：Streamlit Secrets から読み込み
            creds_info = dict(st.secrets["gcp_service_account"])
            self.creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, self.scope)
        else:
            # ローカル環境：ローカルの JSON ファイルから読み込み
            json_path = os.path.join(os.path.dirname(__file__), 'service_account.json')
            self.creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, self.scope)
        
        self.client = gspread.authorize(self.creds)
        self.spreadsheet = self.client.open(spreadsheet_name)
        self.sheet = self.spreadsheet.get_worksheet(0)

    def get_all_data(self):
        """全データを取得して DataFrame で返す"""
        data = self.sheet.get_all_records()
        return pd.DataFrame(data)

    def update_all_data(self, df):
        """DataFrame でスプレッドシート全体を上書き更新する"""
        # NaNを空文字に変換
        df_filled = df.fillna("")
        # ヘッダーとデータをリスト形式に変換
        data_to_update = [df_filled.columns.values.tolist()] + df_filled.values.tolist()
        self.sheet.clear()
        self.sheet.update('A1', data_to_update)

    def update_row(self, row_index, updated_row_dict):
        """特定の行だけを更新（パフォーマンス向上用）"""
        # スプレッドシートは1始まりでヘッダーがあるため +2
        actual_row = row_index + 2 
        values = [list(updated_row_dict.values())]
        self.sheet.update(f'A{actual_row}', values)

# --- 💡 WebClass スクレイピング等のロジックがここに続く ---
# (以前作成したスクレイピング用の関数などをここに配置)