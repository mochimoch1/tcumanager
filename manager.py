import pandas as pd
import os
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))

class AssignmentManager:
    def __init__(self, file_path="assignments.xlsx"):
        self.file_path = file_path
        # ファイルがなければ初期テンプレート作成
        if not os.path.exists(self.file_path):
            self._create_initial_excel()

    def add_assignment(self, data_dict):
        df = pd.read_excel(self.file_path)
        # 新しい行を作成
        new_row = pd.DataFrame([data_dict])
        # 結合して保存
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(self.file_path, index=False)

    def _create_initial_excel(self):
        df = pd.DataFrame(columns=[
            "科目名", "課題内容", "締切日時", "成績重み(%)", 
            "見積もり工数(h)", "ステータス", "優先スコア",
            "24h通知済", "3h通知済" # 通知管理フラグを追加
        ])
        df.to_excel(self.file_path, index=False)

    def check_and_get_alert_tasks(self):
        df = pd.read_excel(self.file_path)
        if df.empty: return []

        df['締切日時'] = pd.to_datetime(df['締切日時'])
        now = datetime.now()
        alerts = []

        # 未完了の課題のみチェック
        for index, row in df.iterrows():
            if row['ステータス'] == '完了': continue

            remaining_hours = (row['締切日時'] - now).total_seconds() / 3600

            # 3時間前通知 (未送信かつ残り3時間以内)
            if remaining_hours <= 3 and row['3h通知済'] != True:
                alerts.append(f"⏰ 【残り3時間！】\n{row['科目名']}: {row['課題内容']}")
                df.at[index, '3h通知済'] = True
                df.at[index, '24h通知済'] = True # 24hも済扱いにする

            # 24時間前通知 (未送信かつ残り24時間以内)
            elif remaining_hours <= 24 and row['24h通知済'] != True:
                alerts.append(f"📅 【残り24時間！】\n{row['科目名']}: {row['課題内容']}")
                df.at[index, '24h通知済'] = True

        # フラグを更新して保存
        df.to_excel(self.file_path, index=False)
        return alerts
        
    def update_and_get_top_task(self):
        # Excel読み込み
        df = pd.read_excel(self.file_path)
        if df.empty: return None

        # 締切を日付型に変換
        df['締切日時'] = pd.to_datetime(df['締切日時'])
        now = datetime.now()

        # 優先スコアの計算ロジック
        def calculate(row):
            if row['ステータス'] == '完了': return 0
            remaining_hours = (row['締切日時'] - now).total_seconds() / 3600
            if remaining_hours <= 0: return 999  # 期限切れは最大値
            # スコア = (重み * 工数) / 残り時間
            return (row['成績重み(%)'] * row['見積もり工数(h)']) / remaining_hours

        df['優先スコア'] = df.apply(calculate, axis=1)

        # 計算結果をExcelに保存（Python上で完結）
        df.to_excel(self.file_path, index=False)

        # 未完了かつスコアが最も高いものを返す
        incomplete = df[df['ステータス'] != '完了'].sort_values(by='優先スコア', ascending=False)
        return incomplete.iloc[0] if not incomplete.empty else None