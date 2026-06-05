import requests
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(('0.0.0.0', 10000), Handler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction

# ============================================================
# НАСТРОЙКИ
# ============================================================
TELEGRAM_BOT_TOKEN = "8729311569:AAEtXuvaCxP-bzKBSfzcSyQtkD7GVY1bCZQ"
GROQ_API_KEY = "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"
RAPIDAPI_KEY = "70c3205990msh926b049e132b219p19b8f7jsnaab2ad4c5c3e"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
RAPIDAPI_BASE = f"https://{RAPIDAPI_HOST}"

RAPIDAPI_HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST
}

# ============================================================
# ПОИСК КОМАНД И СТАТИСТИКИ
# ============================================================

def search_team(team_name: str) -> dict:
    try:
        url = f"{RAPIDAPI_BASE}/football-search-all-players?search={requests.utils.quote(team_name)}"
        # Ищем команду через teams endpoint
        url2 = f"{RAPIDAPI_BASE}/football-get-all-leagues"
        r = requests.get(url2, headers=RAPIDAPI_HEADERS, timeout=10)
        
        # Прямой поиск команды
        search_url = f"{RAPIDAPI_BASE}/football-search-all-players?search={requests.utils.quote(team_name)}"
        r2 = requests.get(search_url, headers=RAPIDAPI_HEADERS, timeout=10)
        if r2.status_code == 200:
            data = r2.json()
            suggestions = data.get("response", {}).get("suggestions", [])
            for item in suggestions:
                if item.get("type") == "team":
                    return {"id": item.get("teamId"), "name": item.get("teamName", team_name)}
    except Exception:
        pass
    return {}

def get_team_recent_matches(team_id: int, team_name: str) -> str:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-all-fixtures-by-teamid?teamid={team_id}&page=1"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            matches = data.get("response", {}).get("fixtures", [])
            
            finished = [m for m in matches if m.get("status") == "FT"][-7:]
            
            if not finished:
                return f"\nДанные по {team_name} недоступны\n"
            
            result = f"\nПОСЛЕДНИЕ МАТЧИ {team_name.upper()}:\n"
            gs, gc, w, d, l = [], [], 0, 0, 0
            
            for m in finished:
                home = m.get("homeTeam", {}).get("name", "?")
                away = m.get("awayTeam", {}).get("name", "?")
                hs = m.get("homeGoals")
                as_ = m.get("awayGoals")
                date = m.get("date", "")[:10]
                
                if hs is not None and as_ is not None:
                    result += f"  {date}: {home} {hs}:{as_} {away}\n"
                    is_home = m.get("homeTeam", {}).get("id") == team_id
                    scored = hs if is_home else as_
                    conceded = as_ if is_home else hs
                    gs.append(scored); gc.append(conceded)
                    if scored > conceded: w += 1
                    elif scored == conceded: d += 1
                    else: l += 1
            
            if gs:
                avg_s = sum(gs)/len(gs)
                avg_c = sum(gc)/len(gc)
                result += f"  Форма: {w}П {d}Н {l}П\n"
                result += f"  Среднее: забито {avg_s:.1f} | пропущено {avg_c:.1f} | тотал {avg_s+avg_c:.1f}\n"
            
            return result
    except Exception as e:
        return f"\nОшибка загрузки {team_name}: {str(e)}\n"
    return f"\nДанные по {team_name} недоступны\n"

def get_h2h(team1_id: int, team2_id: int, team1_name: str, team2_name: str) -> str:
    try:
        url = f"{RAPIDAPI_BASE}/football-get-fixtures-between-teams?firstTeamId={team1_id}&secondTeamId={team2_id}"
        r = requests.get(url, headers=RAPIDAPI_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            matches = data.get("response", {}).get("fixtures", [])
            finished = [m for m in matches if m.get("status") == "FT"][:5]
            
            if finished:
                result = f"\nЛИЧНЫЕ ВСТРЕЧИ ({len(finished)} матчей):\n"
                for m in finished:
                    home = m.get("homeTeam", {}).get("name", "?")
                    away = m.get("awayTeam", {}).get("name", "?")
                    hs = m.get("homeGoals", "?")
                    as_ = m.get("awayGoals", "?")
                    date = m.get("date", "")[:10]
                    result += f"  {date}: {home} {hs}:{as_} {away}\n"
                return result
    except Exception:
        pass
    return "\nИстория встреч недоступна\n"

def get_all_stats(team1_name: str, team2_name: str) -> str:
    stats = "=== АКТУАЛЬНАЯ СТАТИСТИКА ===\n"
    
    team1 = search_team(team1_name)
    team2 = search_team(team2_name)
    
    if team1 and team1.get("id"):
        stats += get_team_recent_matches(team1["id"], team1.get("name", team1_name))
    else:
        stats += f"\n'{team1_name}' не найдена в базе\n"
    
    if team2 and team2.get("id"):
        stats += get_team_recent_matches(team2["id"], team2.get("name", team2_name))
    else:
        stats += f"\n'{team2_name}' не найдена в базе\n"
    
    if team1 and team2 and team1.get("id") and team2.get("id"):
        stats += get_h2h(team1["id"], team2["id"], team1_name, team2_name)
    
    return stats

# ============================================================
# СИСТЕМНЫЙ ПРОМПТ
# ============================================================
SYSTEM_PROMPT = """Ты профессиональный спортивный аналитик по футболу с 20-летним опытом.
Тебе предоставлена реальная свежая статистика. Используй её для точного анализа.
Отвечай на русском языке.

Давай ответ СТРОГО в этом формате:

МАТЧ: [Команда1] vs [Команда2]

АНАЛИЗ ФОРМЫ:
[5-6 предложений на основе реальной статистики]

РЕКОМЕНДАЦИИ ПО СТАВКАМ:
ПОБЕДИТЕЛЬ: [Команда или Ничья] | Уверенность: [%]
ФОРА: [Команда и значение] | Уверенность: [%]
ТОТАЛ ГОЛОВ: [Больше/Меньше X.5] | Уверенность: [%]
ГОЛЫ 2й ТАЙМ: [Больше/Меньше X.5] | Уверенность: [%]
ЖЕЛТЫЕ КАРТОЧКИ: [Больше/Меньше X.5] | Уверенность: [%]
УГЛОВЫЕ: [Больше/Меньше X.5] | Уверенность: [%]

ГЛАВНАЯ СТАВКА:
[ОДНА самая уверенная ставка]
Обоснование: [2-3 предложения]

РИСКИ: [Что может помешать прогнозу]

Прогноз носит аналитический характер. Играй ответственно."""

# ============================================================
# АНАЛИЗ ЧЕРЕЗ GROQ
# ============================================================
def analyze_sync(match_name: str) -> str:
    separators = [" vs ", " - ", " VS ", " v ", " против "]
    team1, team2 = match_name, ""
    for sep in separators:
        if sep in match_name:
            parts = match_name.split(sep, 1)
            team1, team2 = parts[0].strip(), parts[1].strip()
            break

    stats = get_all_stats(team1, team2) if team2 else "Укажи матч: Команда1 vs Команда2"

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Матч: {match_name}\n\nСТАТИСТИКА:\n{stats}\n\nДай полный прогноз."}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }

    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "Время истекло. Попробуй ещё раз."
    except requests.exceptions.HTTPError:
        if r.status_code == 429:
            return "Слишком много запросов. Подожди минуту."
        return f"Ошибка Groq: {r.status_code}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

async def analyze(match_name: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, analyze_sync, match_name)

# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AI Football Analyst\n\n"
        "Напиши матч:\n"
        "Manchester City vs Liverpool\n"
        "Real Madrid vs Barcelona\n"
        "Czechia vs Guatemala\n\n"
        "Ставки - это риск. Играй ответственно!"
    )

async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Примеры:\n\n"
        "Manchester City vs Liverpool\n"
        "Real Madrid vs Barcelona\n"
        "Juventus vs Milan\n"
        "Bayern Munich vs Borussia Dortmund\n"
        "France vs Brazil"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Напиши матч: Команда1 vs Команда2")

async def analyze_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match_name = update.message.text.strip()
    if match_name.startswith("/"): return
    if len(match_name) < 5:
        await update.message.reply_text("Напиши: Команда1 vs Команда2")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    loading = await update.message.reply_text(
        f"Анализирую: {match_name}\nЗагружаю статистику...\nПодожди 15-25 секунд."
    )

    result = await analyze(match_name)
    await loading.delete()

    if len(result) > 4000:
        for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(result)

    kb = [[InlineKeyboardButton("Другой матч", callback_data="new")]]
    await update.message.reply_text("Готово!", reply_markup=InlineKeyboardMarkup(kb))

# ============================================================
# ЗАПУСК
# ============================================================
async def main():
    print("Бот запускается...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("example", example_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    print("Бот работает!")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
