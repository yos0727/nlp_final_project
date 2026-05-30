import os
import calendar
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, jsonify, request

from sentiment import process_csv
from Keywords.keywords import KeywordAnalyzer
from LLM.generator import NewsGenerator
from services.speech import text_to_speech
import importlib.util

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GMAIL_CSV_PATH = os.path.join(BASE_DIR, "gmail_data.csv")
RESOURCE_DIR = os.path.join(BASE_DIR, "static", "resource")
GMAIL_EXPORT_DIR = Path(BASE_DIR) / "get_data"
GMAIL_EXPORT_CSV_PATH = Path(GMAIL_CSV_PATH)

DEFAULT_GMAIL_EXPORT_DAYS = 30
DEFAULT_GMAIL_EXPORT_LIMIT = 50
DEFAULT_GMAIL_EXPORT_PRIMARY = True


def export_gmail_data(
    days: int = DEFAULT_GMAIL_EXPORT_DAYS,
    limit: int | None = DEFAULT_GMAIL_EXPORT_LIMIT,
    primary: bool = DEFAULT_GMAIL_EXPORT_PRIMARY,
) -> Path:
    """執行 Gmail 匯出並寫回主專案的 gmail_data.csv。"""
    # Dynamically load export_gmail_to_csv.py from the get_data folder so the
    # module works whether get_data is a package or plain folder.
    export_path = GMAIL_EXPORT_DIR / "export_gmail_to_csv.py"
    if not export_path.exists():
        raise FileNotFoundError(f"Export script not found: {export_path}")

    spec = importlib.util.spec_from_file_location("export_gmail_to_csv", str(export_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    return module.export_messages(
        days=days,
        output_path=GMAIL_EXPORT_CSV_PATH,
        credentials_path=GMAIL_EXPORT_DIR / "credentials.json",
        token_path=GMAIL_EXPORT_DIR / "token.json",
        limit=limit,
        primary=primary,
    )


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


@app.route("/api/export-gmail", methods=["POST"])
def api_export_gmail():
    payload = request.get_json(silent=True) or {}

    try:
        days = int(payload.get("days", DEFAULT_GMAIL_EXPORT_DAYS))
    except (TypeError, ValueError):
        return jsonify({"error": "days 必須是整數"}), 400

    limit_value = payload.get("limit")
    try:
        if limit_value in (None, ""):
            limit = DEFAULT_GMAIL_EXPORT_LIMIT
        else:
            limit = int(limit_value)
    except (TypeError, ValueError):
        return jsonify({"error": "limit 必須是整數"}), 400

    primary_value = payload.get("primary", DEFAULT_GMAIL_EXPORT_PRIMARY)
    if isinstance(primary_value, str):
        primary = primary_value.strip().lower() in {"1", "true", "yes", "on"}
    else:
        primary = bool(primary_value)

    try:
        output_path = export_gmail_data(days=days, limit=limit, primary=primary)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"匯出 Gmail 資料失敗：{exc}"}), 500

    return jsonify({
        "message": "Gmail 資料已更新",
        "output_path": str(output_path),
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
