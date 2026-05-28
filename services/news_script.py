"""新聞稿產生（由接 GPT 的隊友實作，目前為測試用占位）。"""


def generate_news_script(year: int, month: int, day: int) -> str:
    """
    依日期產生當日新聞稿（字串）。

    隊友整合 GPT 時，請替換此函式內容，回傳完整新聞稿即可；
    下游會呼叫 services.speech.text_to_speech 轉成 MP3。
    """
    date_str = f"{year}年{month}月{day}日"
    return (
        f"各位觀眾晚安，歡迎收看今日郵件摘要新聞。"
        f"今天是{date_str}。"
        f"根據本日 Gmail 內容分析，整體情緒偏向正面，"
        f"關鍵議題包含專案進度與會議安排。"
        f"以上為今日摘要，感謝您的收看。"
    )
