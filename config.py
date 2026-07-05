"""Настройки, ключи и константы проекта."""
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "")
TAVILY_KEY = os.getenv("TAVILY_KEY", "")
PORT = int(os.getenv("PORT", "10000"))

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_TIMEOUT = 60

SOFA_HOST = "sofascore.p.rapidapi.com"
SOFA_BASE = f"https://{SOFA_HOST}"
RAPIDAPI_HEADERS = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": SOFA_HOST}
REQUEST_TIMEOUT = 15

TAVILY_URL = "https://api.tavily.com/search"
