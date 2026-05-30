import csv
import os
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

AZURE_ENDPOINT = os.environ.get("AZURE_ENDPOINT")
AZURE_KEY      = os.environ.get("AZURE_KEY")

CSV_PATH = "gmail_data.csv"

FIELDNAMES = ["ID","date", "received_time", "from", "text","person", "event", "event_datetime", "location", "positive","keywords","processed","summary"]

def get_client():
    credential = AzureKeyCredential(AZURE_KEY)
    return TextAnalyticsClient(endpoint=AZURE_ENDPOINT, credential=credential)

def analyze_sentiment(text: str) -> str:
    """輸入文字，回傳 Positive / Neutral / Negative"""
    if not text or not text.strip():
        return "Neutral"

    client = get_client()
    text = text[:5120]

    response = client.analyze_sentiment(documents=[{"id": "1", "text": text}])
    result = response[0]

    if result.is_error:
        print(f"Azure 錯誤：{result.error}")
        return "Neutral"

    label_map = {
        "positive": "Positive",
        "neutral":  "Neutral",
        "negative": "Negative",
        "mixed":    "Neutral"
    }
    return label_map.get(result.sentiment, "Neutral")

def process_csv(csv_path=CSV_PATH):
    """讀取 CSV，分析每筆 text 的情緒，寫回 positive 欄位。"""

    if not os.path.isfile(csv_path):
        print(f"找不到 {csv_path}")
        return

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        if not row.get("positive"):
            text = row.get("text", "")
            row["positive"] = analyze_sentiment(text)
            print(f"{row['date']} | {text[:20]}... → {row['positive']}")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print("完成！結果已寫回 CSV")

if __name__ == "__main__":
    process_csv()
