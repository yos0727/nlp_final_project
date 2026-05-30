import os
import calendar

import pandas as pd
from flask import Flask, render_template, jsonify

from sentiment import process_csv
from Keywords.keywords import KeywordAnalyzer
from LLM.generator import NewsGenerator
from services.speech import text_to_speech

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GMAIL_CSV_PATH = os.path.join(BASE_DIR, "gmail_data.csv")
RESOURCE_DIR = os.path.join(BASE_DIR, "static", "resource")


def get_daily_resource_paths(year, month, day):
    """回傳指定日期的文字雲與 MP3 路徑。"""
    date_key = f"{year}-{month:02d}-{day:02d}"

    wordcloud_filename = f"{date_key}.png"
    audio_filename = f"{date_key}.mp3"

    wordcloud_path = os.path.join(RESOURCE_DIR, wordcloud_filename)
    audio_path = os.path.join(RESOURCE_DIR, audio_filename)

    wordcloud_url = f"/static/resource/{wordcloud_filename}"
    audio_url = f"/static/resource/{audio_filename}"

    return wordcloud_path, audio_path, wordcloud_url, audio_url


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
    target_date = f"{year}/{month}/{day}"
    wordcloud_path, audio_path, wordcloud_url, audio_url = get_daily_resource_paths(
        year, month, day
    )

    df = pd.read_csv(GMAIL_CSV_PATH, encoding="utf-8-sig")
    selected_rows = df[df["date"] == target_date].fillna("")

    if selected_rows.empty:
        return jsonify({
            "error": "這一天沒有信件資料"
        }), 404

    positive_label = "Neutral"
    positive_list = selected_rows["positive"].tolist()
    if positive_list[0] != "":
        positive_label = positive_list[0]

    # 摘要與當天的圖片、音檔都存在時，才直接使用快取。
    if "summary" in selected_rows.columns:
        summary_list = selected_rows["summary"].tolist()
        summary_exists = summary_list[0] != ""
        resource_files_exist = os.path.isfile(wordcloud_path) and os.path.isfile(audio_path)

        if summary_exists and resource_files_exist:
            return jsonify({
                "summary": summary_list[0],
                "wordcloud_path": wordcloud_url,
                "audio_path": audio_url,
                "sentiment": positive_label
            })

    process_csv(GMAIL_CSV_PATH)

    df = pd.read_csv(GMAIL_CSV_PATH, encoding="utf-8-sig")
    selected_rows = df[df["date"] == target_date].fillna("")
    positive_list = selected_rows["positive"].tolist()
    if positive_list[0] != "":
        positive_label = positive_list[0]

    analyzer = KeywordAnalyzer(
        csv_path=GMAIL_CSV_PATH,
        wordcloud_path=wordcloud_path
    )
    analyzer.run(target_date=target_date)

    generator = NewsGenerator(csv_path=GMAIL_CSV_PATH)
    result = generator.run(target_date=target_date, ask_ai=True)

    try:
        text_to_speech(result["news"], audio_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "summary": result["summary"],
        "wordcloud_path": wordcloud_url,
        "audio_path": audio_url,
        "sentiment": positive_label
    })


if __name__ == "__main__":
    app.run(debug=True)
