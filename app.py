from flask import Flask, render_template, jsonify
import calendar
from datetime import datetime
from sentiment import analyze_sentiment, process_csv

app = Flask(__name__)

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
    # 執行情緒分析，寫回 CSV
    process_csv()

    date_str = f"{year}-{month:02d}-{day:02d}"

    # 從 CSV 找對應日期的情緒結果
    import csv
    sentiment = "Neutral"
    with open("static/resource/emails.csv", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["date"] == date_str:
                sentiment = row["positive"]
                break

    summary = f"Summary for {date_str}: This is a sample summary of the day's events."

    return jsonify({
        "summary":   summary,
        "sentiment": sentiment
    })


if __name__ == '__main__':
    app.run(debug=True)