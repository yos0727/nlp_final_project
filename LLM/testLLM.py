import os
from dotenv import load_dotenv
from google import genai

# 讀取 .env 檔案
load_dotenv()

# 從 .env 取得 API Key
api_key = os.getenv("GEMINI_API_KEY")

# 檢查有沒有成功讀到
if not api_key:
    raise ValueError("找不到 GEMINI_API_KEY，請確認 .env 檔案是否存在，且變數名稱是否正確。")

# 建立 Gemini client
client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents="請用三句話介紹人工智慧是什麼。"
)

print(response.text)