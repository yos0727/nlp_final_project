import csv
from pathlib import Path

from flask import Flask, render_template, jsonify
import calendar

from sentiment import process_csv
from services.news_script import generate_news_script
from services.speech import text_to_speech

app = Flask(__name__)

RESOURCE_DIR = Path(app.root_path) / "static" / "resource"
SUMMARY_MP3 = RESOURCE_DIR / "summary.mp3"
EMAILS_CSV = RESOURCE_DIR / "emails.csv"

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
    # 情緒分析：寫回 CSV（隊友 sentiment 分支）
    process_csv()

    date_str = f"{year}-{month:02d}-{day:02d}"
    sentiment_label = "Neutral"
    if EMAILS_CSV.is_file():
        with open(EMAILS_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date") == date_str:
                    sentiment_label = row.get("positive", "Neutral")
                    break

    # 新聞稿 + 語音（你的部分）
    # TODO: 文字雲 → static/resource/summary.png（隊友負責）
    try:
        script = generate_news_script(year, month, day)
        text_to_speech(script, SUMMARY_MP3)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 500

    summary = script.split("。")[0] + "。" if "。" in script else script[:80]

    return jsonify({
        "summary": summary,
        "script": script,
        "sentiment": sentiment_label,
    })


if __name__ == '__main__':
    app.run(debug=True)
