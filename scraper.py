import os
import time
import re
from playwright.sync_api import sync_playwright

def get_webclass_data():
    """
    WebClassから課題情報と講義リスト（時間割）を取得します。
    """
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "browser_data")
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,  # 動作確認のため表示（安定したらTrueへ）
            slow_mo=500
        )
        
        page = context.new_page()
        page.goto("https://webclass.tcu.ac.jp/")

        # 1. ログイン処理（ポップアップ対応）
        try:
            tcu_button = page.get_by_text("TCUアカウントで利用")
            if tcu_button.is_visible():
                with context.expect_page() as new_page_info:
                    tcu_button.click()
                page = new_page_info.value
                page.wait_for_selector("text=ダッシュボード", timeout=120000)
        except:
            pass

        # 2. ダッシュボードへ移動
        try:
            page.click("text=ダッシュボード")
            page.wait_for_load_state("networkidle")
        except:
            pass

        print("WebClassのデータを解析中...")
        frame = page.frame(url=lambda u: "score_summary_table/dashboard" in u)
        
        assignments = []
        course_list = []

        if frame:
            try:
                frame.wait_for_selector("h3", timeout=20000)
                time.sleep(5) # データの完全な読み込みを待機

                date_pattern = re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}')
                # 曜日・時限を抽出する正規表現 (例: 月1・木2)
                schedule_pattern = re.compile(r'([月火水木金土日][1-7](?:・[月火水木金土日][1-7])*)')

                sections = frame.query_selector_all("section.mt-2")
                for section in sections:
                    category_header = section.query_selector("h3")
                    if not category_header: continue
                    category_text = category_header.inner_text().strip()
                    
                    # 不要なカテゴリのみスキップ（複数学科は「情報社会と職業」があるので残す）
                    if any(kw in category_text for kw in ["学科未設定", "全学科・専攻"]):
                        continue
                    
                    course_blocks = section.query_selector_all("div.mt-2")
                    for block in course_blocks:
                        course_link = block.query_selector("a.text-base.font-semibold")
                        if not course_link: continue
                        
                        raw_name = course_link.inner_text().strip()
                        
                        # 【講義名のクレンジングと時間割抽出】
                        # 講義名部分のみ取得
                        clean_course_name = re.sub(r'^»\s*', '', raw_name).split('(')[0].strip()
                        # スケジュール部分を取得
                        schedule_match = schedule_pattern.search(raw_name)
                        schedule_text = schedule_match.group(1) if schedule_match else "設定なし"

                        # 講義リストに追加
                        course_list.append({
                            "講義名": clean_course_name,
                            "曜日・時限": schedule_text,
                            "フルネーム": raw_name
                        })

                        # --- 課題抽出ロジック ---
                        # 特定の不要な講義は課題解析から除外
                        if "2026年度3年生" in raw_name: continue

                        table = block.query_selector("table")
                        if not table: continue
                        
                        rows = table.query_selector_all("tbody tr")
                        for row in rows:
                            cells = row.query_selector_all("td")
                            if len(cells) < 5: continue
                            
                            task_name = cells[0].inner_text().strip()
                            deadline_text = cells[1].inner_text().strip()
                            exec_date_text = cells[2].inner_text().strip()
                            status_text = cells[4].inner_text().strip()

                            # 研究室関連の不要な課題を除外
                            if "研究室仮配属" in task_name: continue

                            is_target = False
                            final_date = ""

                            if date_pattern.search(deadline_text):
                                is_target = True
                                final_date = deadline_text
                            elif status_text in ["-", "未回答"]:
                                is_target = True
                                # 締切がない場合は実施日を、それもなければ遠い未来を仮設定
                                final_date = exec_date_text if date_pattern.search(exec_date_text) else "2027/03/31 23:59"

                            if is_target:
                                assignments.append({
                                    "24h通知済": False,
                                    "3h通知済": False,
                                    "科目名": clean_course_name,
                                    "課題内容": task_name,
                                    "締切日時": final_date.replace("-", "/"),
                                    "成績重み(%)": 10,
                                    "見積もり工数(h)": 2,
                                    "ステータス": "未着手",
                                    "優先スコア": 0
                                })
            except Exception as e:
                print(f"解析中にエラーが発生しました: {e}")
        else:
            print("エラー: iframeが見つかりませんでした。")

        context.close()
        return assignments, course_list