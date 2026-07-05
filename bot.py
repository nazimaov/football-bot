import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction

import config
import report
from analysis_engine import run_analysis
from logger import setup_logging

logger = setup_logging()


# ============================================================
# KEEP-ALIVE СЕРВЕР (чтобы Render не усыплял)
# ============================================================
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - bot is alive")

    def log_message(self, format, *args):
        pass  # не засоряем логи


def run_keep_alive():
    server = HTTPServer(("0.0.0.0", config.PORT), PingHandler)
    logger.info("Keep-alive сервер на порту %s", config.PORT)
    server.serve_forever()


# ============================================================
# TELEGRAM ОБРАБОТЧИКИ
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ AI Football Analyst v7\n\n"
        "Просто напиши две команды любым способом:\n"
        "• Реал Мадрид vs Барселона\n"
        "• Ямайка - Южная Африка\n"
        "• Manchester City Liverpool\n"
        "• Бавария / Дортмунд\n\n"
        "📊 Форма | 👥 Составы | 🤕 Травмы\n"
        "👨‍⚖️ Судья | 🌦 Погода | 📈 H2H\n\n"
        "Лучше за 30-60 мин до матча."
    )


async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Реал Мадрид vs Барселона")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Напиши: Команда1 vs Команда2")


async def analyze_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_name = update.message.text.strip()
    if match_name.startswith("/"):
        return
    if len(match_name) < 5:
        await update.message.reply_text("Напиши: Команда1 vs Команда2")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    loading = await update.message.reply_text(
        f"🔍 {match_name}\n📊 Форма...\n👥 Составы...\n🌦 Погода...\n👨‍⚖️ Судья...\n⏱ 25-40 сек"
    )
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_analysis, match_name)
    try:
        await loading.delete()
    except Exception:
        pass
    for part in report.split_for_telegram(result):
        await update.message.reply_text(part)
    kb = [[InlineKeyboardButton("🔄 Другой матч", callback_data="new")]]
    await update.message.reply_text("Готово!", reply_markup=InlineKeyboardMarkup(kb))


def main():
    if not all([config.TELEGRAM_BOT_TOKEN, config.GROQ_API_KEY, config.RAPIDAPI_KEY]):
        logger.error("Нет ключей (TELEGRAM_BOT_TOKEN / GROQ_API_KEY / RAPIDAPI_KEY)")
        return
    if not config.OPENWEATHER_KEY:
        logger.warning("OPENWEATHER_KEY не задан")
    if not config.TAVILY_KEY:
        logger.warning("TAVILY_KEY не задан")

    # Запускаем keep-alive в отдельном потоке
    keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
    keep_alive_thread.start()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("example", example_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    logger.info("Бот работает!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
