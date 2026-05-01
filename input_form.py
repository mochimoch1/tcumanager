import tkinter as tk
from tkinter import messagebox
from manager import AssignmentManager

def save_data():
    # 入力値を取得
    data = {
        "科目名": entry_subject.get(),
        "課題内容": entry_content.get(),
        "締切日時": entry_deadline.get(),
        "成績重み(%)": int(entry_weight.get() or 0),
        "見積もり工数(h)": float(entry_hours.get() or 0),
        "ステータス": "未着手",
        "優先スコア": ""
    }
    
    if not data["科目名"] or not data["締切日時"]:
        messagebox.showwarning("入力エラー", "科目名と締切日時は必須です")
        return

    # Excelに保存
    manager = AssignmentManager()
    manager.add_assignment(data)
    
    messagebox.showinfo("完了", "Excelに課題を追記しました！")
    # 入力欄をクリア
    entry_subject.delete(0, tk.END)
    entry_content.delete(0, tk.END)
    entry_deadline.delete(0, tk.END)
    entry_weight.delete(0, tk.END)
    entry_hours.delete(0, tk.END)

# GUI画面の構成
root = tk.Tk()
root.title("課題クイック登録")
root.geometry("300x400")

# 各入力ラベルとフィールド
labels = ["科目名", "課題内容", "締切日時(YYYY/MM/DD HH:MM)", "成績重み(%)", "見積もり工数(h)"]
entries = []

for label_text in labels:
    tk.Label(root, text=label_text).pack(pady=5)
    entry = tk.Entry(root, width=30)
    entry.pack()
    entries.append(entry)

entry_subject, entry_content, entry_deadline, entry_weight, entry_hours = entries

# デフォルト値のヒント（現在の年などを入れておくと楽）
entry_deadline.insert(0, "2026/  /   :  ")

tk.Button(root, text="Excelに保存", command=save_data, bg="#4CAF50", fg="white").pack(pady=20)

root.mainloop()