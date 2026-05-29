import os
import re
from collections import Counter

import jieba
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient


class KeywordAnalyzer:
    """
    負責兩件事：
    1. 讀取指定日期的 gmail_data.csv 文字，找出 person/event/time/location/keywords，並寫回 CSV。
    2. 用指定日期的 text 產生文字雲，存到指定圖片位置。
    """

    def __init__(
        self,
        csv_path="../gmail_data.csv",
        wordcloud_path="static/resource/summary.png",
        keyword_csv_path=None,
        font_path="C:/Windows/Fonts/msjh.ttc"
    ):
        load_dotenv(override=True)

        self.csv_path = csv_path
        self.wordcloud_path = wordcloud_path
        self.keyword_csv_path = keyword_csv_path
        self.font_path = font_path

        self.endpoint = os.getenv("AZURE_LANGUAGE_ENDPOINT")
        self.key = os.getenv("AZURE_LANGUAGE_KEY")

        if not self.endpoint or not self.key:
            raise ValueError("請先在 .env 設定 AZURE_LANGUAGE_ENDPOINT 和 AZURE_LANGUAGE_KEY")

        self.client = TextAnalyticsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.key)
        )

        self.stop_words = {
            "的", "了", "是", "在", "我", "你", "他", "她", "它",
            "和", "與", "及", "也", "都", "就", "很", "有", "沒有",
            "嗎", "呢", "啊", "喔", "哦", "啦", "吧", "這", "那",
            "一個", "我們", "你們", "他們", "自己", "可以", "不是",
            "因為", "所以", "如果", "但是", "然後", "還有", "就是",
            "今天", "明天", "昨天", "現在", "等等", "一下",
            "gmail", "email", "mail", "subject", "from", "to",
            "cc", "bcc", "http", "https", "www", "com"
        }

    def clean(self, value):
        """把空值轉成空字串，其他值轉成字串。"""
        if value is None:
            return ""
        text = str(value)
        return text.strip()

    def read_csv(self):
        """讀取 Gmail CSV。"""
        return pd.read_csv(self.csv_path, encoding="utf-8-sig")

    def save_csv(self, df):
        """把分析結果寫回原本的 Gmail CSV，讓 generator.py 可以接著使用。"""
        df.to_csv(self.csv_path, index=False, encoding="utf-8-sig")

    def get_rows_by_date(self, df, target_date):
        """
        取出指定日期的資料（初學者版：直接字串比對）。
        """
        if target_date is None:
            return df
        return df[df["date"] == target_date]

    def ensure_columns(self, df):
        """確保 CSV 有需要的欄位。"""
        needed_columns = ["person", "event", "event_datetime", "location", "keywords", "processed", "summary"]

        for col in needed_columns:
            if col not in df.columns:
                df[col] = ""

        return df

    def get_entities(self, text):
        """用 Azure 找出人名、地點、時間。"""
        person = ""
        location = ""
        event_datetime = ""

        docs = list(self.client.recognize_entities([text], language="zh"))
        if len(docs) == 0:
            return person, location, event_datetime
        doc = docs[0]
        if doc.is_error:
            return person, location, event_datetime

        for entity in doc.entities:
            if entity.category == "Person" and person == "":
                person = entity.text

            if entity.category == "Location" and location == "":
                location = entity.text

            if entity.category == "DateTime" and event_datetime == "":
                event_datetime = entity.text

        return person, location, event_datetime

    def get_key_phrases(self, text):
        """用 Azure 抽出關鍵片語。"""
        docs = list(self.client.extract_key_phrases([text], language="zh"))
        if len(docs) == 0:
            return []
        doc = docs[0]
        if doc.is_error:
            return []

        return doc.key_phrases

    def get_event(self, text, key_phrases, person, location, event_datetime):
        """從文字或關鍵片語中猜出事件。"""
        event_words = [
            "上課", "開會", "考試", "繳交", "面試", "停水",
            "過生日", "聚餐", "講座", "活動", "付款", "繳費",
            "退款", "出貨", "報告", "作業"
        ]

        for word in event_words:
            if word in text:
                return word

        ignore_words = [person, location, event_datetime]

        for phrase in key_phrases:
            phrase = self.clean(phrase)

            if phrase == "":
                continue

            if phrase in ignore_words:
                continue

            return phrase

        return ""

    def fill_keyword_columns(self, target_date=None):
        """
        分析指定日期的 text，並把結果填回 gmail_data.csv。
        回傳值是「指定日期的資料」。
        """
        df = self.read_csv()
        df = self.ensure_columns(df)

        selected_rows = self.get_rows_by_date(df, target_date)

        for index, row in selected_rows.iterrows():
            text = self.clean(row.get("text", ""))

            if text == "":
                continue

            print("正在分析：", text)

            person, location, event_datetime = self.get_entities(text)
            key_phrases = self.get_key_phrases(text)
            event = self.get_event(text, key_phrases, person, location, event_datetime)

            df.loc[index, "person"] = person
            df.loc[index, "location"] = location
            df.loc[index, "event_datetime"] = event_datetime
            df.loc[index, "event"] = event
            df.loc[index, "keywords"] = ",".join(key_phrases)
            df.loc[index, "processed"] = 1

        self.save_csv(df)

        return self.get_rows_by_date(df, target_date)

    def get_word_list(self, texts):
        """把文字切詞，並移除停用詞、數字、太短的詞。"""
        text_list = []
        for item in texts:
            clean_text = self.clean(item)
            if clean_text != "":
                text_list.append(clean_text)

        all_text = " ".join(text_list)
        words = jieba.lcut(all_text)

        clean_words = []

        for word in words:
            word = word.strip().lower()

            if word == "":
                continue

            if word in self.stop_words:
                continue

            if word.isdigit():
                continue

            if len(word) < 2:
                continue

            if not re.search(r"[\u4e00-\u9fffA-Za-z]", word):
                continue

            clean_words.append(word)

        return clean_words

    def make_wordcloud(self, target_date=None):
        """根據指定日期的 text 產生文字雲，存到 self.wordcloud_path。"""
        df = self.read_csv()
        selected_rows = self.get_rows_by_date(df, target_date)

        words = self.get_word_list(selected_rows["text"])
        word_freq = Counter(words)

        output_dir = os.path.dirname(self.wordcloud_path)
        if output_dir != "":
            os.makedirs(output_dir, exist_ok=True)

        font_path = self.font_path if os.path.exists(self.font_path) else None

        if len(word_freq) == 0:
            plt.figure(figsize=(10, 5))
            plt.text(0.5, 0.5, "No keywords", ha="center", va="center", fontsize=24)
            plt.axis("off")
            plt.tight_layout()
            plt.savefig(self.wordcloud_path, dpi=150)
            plt.close()
        else:
            wc = WordCloud(
                font_path=font_path,
                width=800,
                height=400,
                background_color="white"
            ).generate_from_frequencies(word_freq)

            plt.figure(figsize=(10, 5))
            plt.imshow(wc, interpolation="bilinear")
            plt.axis("off")
            plt.title("Word Cloud")
            plt.tight_layout()
            plt.savefig(self.wordcloud_path, dpi=150)
            plt.close()

        print("文字雲已輸出：", self.wordcloud_path)

        return self.wordcloud_path

    def run(self, target_date=None):
        """
        依指定日期更新欄位並產生文字雲。
        """
        self.fill_keyword_columns(target_date)
        wordcloud_path = self.make_wordcloud(target_date)

        return {
            "wordcloud_path": wordcloud_path
        }


if __name__ == "__main__":
    analyzer = KeywordAnalyzer(
        csv_path="../gmail_data.csv",
        wordcloud_path="static/resource/summary.png"
    )
    analyzer.run(target_date="2026/1/30")
