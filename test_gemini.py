
from dotenv import load_dotenv
import os
import requests

load_dotenv()

api_key = os.getenv("AI_API_KEY")
model = os.getenv("GEMINI_PRIMARY_MODEL")

url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

try:
    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        },
        json={
            "contents": [
                {"parts": [{"text": "Reply exactly GEMINI_CONNECTED"}]}
            ]
        },
        timeout=30
    )

    print("HTTP Status:", response.status_code)
    print("Response:", response.text[:2000])

except Exception as error:
    print("Connection error:", str(error))

