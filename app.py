import os
import calendar

import pandas as pd
from flask import Flask, render_template, jsonify

from Keywords.keywords import KeywordAnalyzer
from LLM.generator import NewsGenerator


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 依照你原本程式的預設：gmail_data.csv 放在專案資料夾的上一層
GMAIL_CSV_PATH = os.path.join(BASE_DIR, "gmail_data.csv")

# 文字雲固定輸出到網站會讀取的位置
WORDCLOUD_PATH = os.path.join(BASE_DIR, "static", "resource", "summary.png")

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/calendar/<int:year>/<int:month>")
def api_calendar(year, month):
    cal = calendar.Calendar(firstweekday=6)
    cal_data = cal.monthdayscalendar(year, month)

    return jsonify({
        "year": year,
        "month": month,
        "cal_data": cal_data
    })


@app.route("/api/summary/<int:year>/<int:month>/<int:day>")
def api_summary(year, month, day):
    """
    點日期後執行：
    1. 先看該日期是否都已 processed=1
    2. 若已處理，直接回傳
    3. 若未處理，才執行 keywords 分析與文字雲
    """
    target_date = f"{year}/{month}/{day}"
    df = pd.read_csv(GMAIL_CSV_PATH, encoding="utf-8-sig")
    selected_rows = df[df["date"] == target_date].fillna("")

    if len(selected_rows) > 0 and "summary" in selected_rows.columns:
        summary_list = selected_rows["summary"].tolist()
        summary_text = summary_list[0]
        if summary_text != "":
            return jsonify({
                "summary": summary_text,
                "wordcloud_path": "static/resource/summary.png"
            })

    if len(selected_rows) > 0 and "processed" in selected_rows.columns:
        processed_list = selected_rows["processed"].tolist()
        processed_value = processed_list[0]
        if processed_value == 1:
            return jsonify({
                "summary": "這一天已經處理過，直接顯示既有文字雲。",
                "wordcloud_path": "static/resource/summary.png"
            })

    analyzer = KeywordAnalyzer(
        csv_path=GMAIL_CSV_PATH,
        wordcloud_path=WORDCLOUD_PATH
    )
    analyzer.run(target_date=target_date)

    generator = NewsGenerator(csv_path=GMAIL_CSV_PATH)
    result = generator.run(target_date=target_date, ask_ai=True)

    return jsonify({
        "summary": result["summary"],
        "wordcloud_path": "static/resource/summary.png"
    })


if __name__ == "__main__":
    app.run(debug=True)
