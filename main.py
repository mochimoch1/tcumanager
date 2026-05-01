import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# --- 【重要】main.pyでも自分の居場所を特定する ---
base_dir = os.path.dirname(os.path.abspath(__file__))
# ---------------------------------------------

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)

from scraper import get_webclass_data
import gspread # 追加
from oauth2client.service_account import ServiceAccountCredentials # 追加

load_dotenv()
class AssignmentManager:
    def __init__(self, spreadsheet_name="TCU-Mission-Control"):
        # 認証設定
        self.scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        # 【重要】jsonファイル名をあなたのファイル名に合わせてください
        self.creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', self.scope)
        self.client = gspread.authorize(self.creds)
        
        try:
            self.sheet = self.client.open(spreadsheet_name).get_worksheet(0)
        except Exception as e:
            print(f"❌ シートが見つかりません。共有設定を確認してください: {e}")
            raise
            
        self.cols = ["24h通知済", "3h通知済", "科目名", "課題内容", "締切日時", "成績重み(%)", "見積もり工数(h)", "ステータス", "優先スコア"]
        self._ensure_columns()

    def _ensure_columns(self):
        header = self.sheet.row_values(1)
        if not header:
            self.sheet.insert_row(self.cols, 1)

    def get_all_data(self):
        data = self.sheet.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df['締切日時'] = pd.to_datetime(df['締切日時'])
            # 空白除去の徹底
            df['科目名'] = df['科目名'].astype(str).str.strip()
            df['課題内容'] = df['課題内容'].astype(str).str.strip()
        return df

    def update_all_data(self, df):
        temp_df = df.copy()
        if '締切日時' in temp_df.columns:
            temp_df['締切日時'] = temp_df['締切日時'].dt.strftime('%Y-%m-%d %H:%M:%S')
        data_to_write = [self.cols] + temp_df[self.cols].fillna('').values.tolist()
        self.sheet.update('A1', data_to_write)

    def is_duplicate(self, new_item):
        df = self.get_all_data()
        if df.empty: return False
        new_subject = str(new_item.get('科目名', '')).strip()
        new_content = str(new_item.get('課題内容', '')).strip()
        match = df[(df['科目名'] == new_subject) & (df['課題内容'] == new_content)]
        return not match.empty

    def add_assignment(self, data_dict):
        row_data = [data_dict.get(col, False if "通知済" in col else (0 if "重み" in col or "工数" in col or "スコア" in col else "未着手")) for col in self.cols]
        self.sheet.append_row([str(x) for x in row_data])

    def sync_with_latest_data(self, latest_assignments):
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
        if updated: self.update_all_data(df)

    def process_and_get_notifications(self):
        df = self.get_all_data()
        if df.empty: return pd.DataFrame(), []
        now = datetime.now()
        alerts = []
        def update_row(row):
            if row['ステータス'] != '未着手':
                row['優先スコア'] = 0
                return row
            rem_h = (row['締切日時'] - now).total_seconds() / 3600
            row['優先スコア'] = (row['成績重み(%)'] * row['見積もり工数(h)']) / rem_h if rem_h > 0 else 999
            if 0 < rem_h <= 3 and not row['3h通知済']:
                alerts.append(f"⏰ 残り3h: {row['課題内容']}"); row['3h通知済'] = True
            elif 0 < rem_h <= 24 and not row['24h通知済']:
                alerts.append(f"📅 残り24h: {row['課題内容']}"); row['24h通知済'] = True
            return row
        df = df.apply(update_row, axis=1)
        self.update_all_data(df)
        return df[df['ステータス'] == '未着手'].sort_values('優先スコア', ascending=False), alerts

def main():
    # あなたが作成したスプレッドシートの名前に書き換えてください
    manager = AssignmentManager(spreadsheet_name="to the top")
    
    print("WebClassから情報を取得中...")
    new_assignments, course_list = get_webclass_data()
    
    if course_list:
        pd.DataFrame(course_list).to_excel("timetable.xlsx", index=False)

    manager.sync_with_latest_data(new_assignments)

    added_count = 0
    for item in new_assignments:

        # ★ ここで「掃除（strip）」を実行します
        # これにより、エクセルに保存される文字自体が綺麗になります
        item['科目名'] = str(item.get('科目名', '')).strip()
        item['課題内容'] = str(item.get('課題内容', '')).strip()
        
        if not manager.is_duplicate(item):
            manager.add_assignment(item)
            added_count += 1
    
    print(f"{added_count}件追加。通知を生成します...")
    incomplete_tasks, alert_messages = manager.process_and_get_notifications()

    final_messages = []
    if alert_messages:
        final_messages.extend(alert_messages)

    if not incomplete_tasks.empty:
        task_list_text = "📝 未完了の課題リスト\n"
        task_list_text += "----------------------\n"
        for _, task in incomplete_tasks.iterrows():
            deadline_str = task['締切日時'].strftime('%m/%d %H:%M')
            task_list_text += f"▼ {task['科目名']}\n   {task['課題内容']}\n   ({deadline_str})\n\n"
        task_list_text += f"合計: {len(incomplete_tasks)}件"
        final_messages.append(task_list_text)
# 5. LINE送信
    if final_messages:
        config = Configuration(access_token=os.getenv('LINE_ACCESS_TOKEN'))
        with ApiClient(config) as api_client:
            api = MessagingApi(api_client)
            for msg in final_messages:
                try:
                    api.push_message(PushMessageRequest(
                        to=os.getenv('LINE_USER_ID'), 
                        messages=[TextMessage(text=msg)]
                    ))
                except Exception as e:
                    # 上限に達している場合などのエラーをキャッチ
                    print(f"⚠️ LINE送信失敗 (上限エラー等の可能性があります): {e}")
        print(f"{len(final_messages)}件の通知処理を終了しました。")
    else:
        print("通知する課題はありません。")

if __name__ == "__main__":
    main()