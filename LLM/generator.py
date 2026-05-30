import os
import random
from collections import defaultdict

import pandas as pd
from dotenv import load_dotenv
from google import genai


class NewsGenerator:
    """
    負責把 keywords.py 已經填好的 CSV 轉成新聞稿 prompt。

    注意：
    - keywords.py 會先把 person/event/event_datetime/location/keywords 寫回 CSV。
    - generator.py 再讀同一份 CSV，根據這些欄位組出 prompt。
    """

    def __init__(
        self,
        csv_path="gmail_data.csv",
        main_prompt_path="LLM/templates/evening_news_prompt.txt",
        mapping_path="LLM/templates/mapping_templates.txt",
        output_dir="."
    ):
        load_dotenv()

        self.csv_path = csv_path
        self.main_prompt_path = main_prompt_path
        self.mapping_path = mapping_path
        self.output_dir = output_dir

        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.client = genai.Client(api_key=self.api_key)

        self.main_prompt = self.read_txt(self.main_prompt_path)
        self.mapping = self.read_mapping_txt(self.mapping_path)

    def clean(self, value):
        """把 NaN 轉成空字串，其他值轉成去除前後空白的字串"""
        if pd.isna(value):
            return ""
        return str(value).strip()

    def read_txt(self, path):
        """讀取文字模板檔"""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def read_mapping_txt(self, path):
        """
        讀取 mapping_templates.txt
        """
        data = defaultdict(list)
        title = ""

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if line == "":
                    continue

                if line.startswith("[") and line.endswith("]"):
                    title = line[1:-1]
                else:
                    data[title].append(line)

        return data

    def choose(self, key):
        """從某個分類中隨機選一個模板。"""
        options = self.mapping.get(key, [""])
        return random.choice(options)

    def fill(self, template, row):
        """把模板中的 {person}、{event} 等欄位換成 CSV 裡的值。"""
        values = {
            "person": self.clean(row.get("person", "")),
            "event": self.clean(row.get("event", "")),
            "event_datetime": self.clean(row.get("event_datetime", "")),
            "location": self.clean(row.get("location", "")),
            "text": self.clean(row.get("text", "")),
            "from": self.clean(row.get("from", "")),
            "received_time": self.clean(row.get("received_time", ""))
        }

        result = template

        for key, value in values.items():
            result = result.replace("{" + key + "}", value)

        return result

    def get_rows_by_date(self, df, target_date):
        """
        取出指定日期的資料。
        例如 target_date 可以是：2026/1/30、2026-01-30。
        """
        if target_date is None:
            return df

        date_series = pd.to_datetime(df["date"], errors="coerce")
        target = pd.to_datetime(target_date, errors="coerce")

        if pd.isna(target):
            return df[df["date"].astype(str) == str(target_date)]

        return df[date_series.dt.date == target.date()]

    def get_tone_key(self, row):
        """根據 positive 欄位決定新聞語氣。"""
        positive = self.clean(row.get("positive", ""))

        if positive == "1" or positive == "Positive":
            return "tone.1"
        if positive == "0" or positive == "Neutral" or positive == "Negative":
            return "tone.0"
        return "tone.default"

    def get_lead_key(self, row):
        """根據資料完整度決定導語模板。"""
        person = self.clean(row.get("person", ""))
        event = self.clean(row.get("event", ""))
        time = self.clean(row.get("event_datetime", ""))
        location = self.clean(row.get("location", ""))

        if person and event and time and location:
            return "lead.full"

        if person and event and time:
            return "lead.no_location"

        if person and event and location:
            return "lead.no_time"

        if event:
            return "lead.only_event"

        return "lead.default"

    def get_category(self, row):
        """根據文字內容判斷新聞類型。"""
        text = self.clean(row.get("text", "")) + self.clean(row.get("event", ""))
        categories = ["family", "school", "work", "money", "travel", "activity"]

        for category in categories:
            keyword_line = self.mapping.get("keywords." + category, [""])[0]
            keywords = keyword_line.split(",")

            for word in keywords:
                word = word.strip()

                if word != "" and word in text:
                    return category

        return "default"

    def make_news_item(self, row):
        """把單一封信件整理成一則新聞 prompt 區塊。"""
        tone_key = self.get_tone_key(row)
        lead_key = self.get_lead_key(row)
        category = self.get_category(row)

        tone = self.fill(self.choose(tone_key), row)
        lead = self.fill(self.choose(lead_key), row)
        transition = self.choose("transition")
        news_type = self.choose("category." + category)

        news_item = f"""
{transition}

新聞類型：
{news_type}

新聞導語：
{lead}

語氣要求：
{tone}

原始信件內容：
{self.clean(row.get("text", ""))}
""".strip()

        return news_item, lead, tone, news_type

    def make_prompt(self, target_date):
        """根據指定日期的 CSV 資料產生完整 prompt。"""
        df = pd.read_csv(self.csv_path, encoding="utf-8-sig")
        df = self.get_rows_by_date(df, target_date)

        items = []

        for _, row in df.iterrows():
            news_item, lead, tone, news_type = self.make_news_item(row)
            items.append(f"第{len(items) + 1}則：\n{news_item}")

        all_items = "\n\n".join(items)
        prompt = self.main_prompt.replace("{date}", str(target_date))
        prompt = prompt.replace("{news_items}", all_items)

        return prompt

    def make_summary_prompt(self, target_date, news_text):
        """把新聞稿整理成當日摘要的提示詞。"""
        return f"""
        請根據以下「{target_date}」的新聞稿內容，產生 1 段給一般使用者看的當日摘要。
        要求：
        1. 使用繁體中文
        2. 長度 20~30 字
        3. 語氣自然、容易閱讀
        4. 不要使用條列

        新聞稿內容：
        {news_text}
        """.strip()

    def ask_gemini(self, prompt):
        """如果需要真的請 Gemini 生成新聞稿，可以呼叫這個方法。"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        return response.text

    def save_daily_summary(self, target_date, summary_text):
        """把指定日期的摘要寫回 gmail_data.csv 的 summary 欄位。"""
        df = pd.read_csv(self.csv_path, encoding="utf-8-sig")

        if "summary" not in df.columns:
            df["summary"] = ""

        date_series = pd.to_datetime(df["date"], errors="coerce")
        target = pd.to_datetime(target_date, errors="coerce")

        if pd.isna(target):
            mask = df["date"].astype(str) == str(target_date)
        else:
            mask = date_series.dt.date == target.date()

        df.loc[mask, "summary"] = summary_text
        df.to_csv(self.csv_path, index=False, encoding="utf-8-sig")

    def run(self, target_date, ask_ai=True):
        """
        給 app.py 呼叫的流程
        """
        prompt = self.make_prompt(target_date)

        if not ask_ai:
            return prompt

        news = self.ask_gemini(prompt)
        summary_prompt = self.make_summary_prompt(target_date, news)
        summary = self.ask_gemini(summary_prompt)
        self.save_daily_summary(target_date, summary)

        return {
            "news": news,
            "summary": summary
        }


if __name__ == "__main__":
    generator = NewsGenerator(csv_path="../gmail_data.csv")
    generator.run(target_date="2026/1/30")
