"""Kiểm tra danh sách model Gemini khả dụng với API key hiện tại."""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

print("Các model khả dụng:\n")
for m in client.models.list():
    print(m.name)
