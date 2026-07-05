"""Формирование промпта и обращение к Groq API."""
import logging

import requests

from config import GROQ_URL, GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты профессиональный футбольный аналитик. Работаешь СТРОГО с данными.

ПРИОРИТЕТЫ:
1. СОСТАВЫ — отсутствие лидеров меняет прогноз
2. ФОРМА (среднее голов, ОЗ, ТБ2.5)
3. H2H
4. ТУРНИРНАЯ СИТУАЦИЯ — место в таблице, отставание от лидера, мотивация (борьба за титул/еврокубки/выживание повышает интенсивность игры)
5. ПОГОДА — ветер >8 м/с снижает тотал
6. СУДЬЯ — если есть стата
7. ДОМ/ВЫЕЗД — +0.3 голу дома

ПРАВИЛА:
- [!] = данных нет → уверенность 40-50%
- НЕ выдумывай. Только данные
- 70%+ ТОЛЬКО при явном перевесе
- Угловые/карточки ≤55%

ФОРМАТ:

МАТЧ: [К1] vs [К2]
КАЧЕСТВО ДАННЫХ: [Высокое/Среднее/Низкое]

КЛЮЧЕВЫЕ ФАКТОРЫ:
- [3-5 пунктов]

АНАЛИЗ СОСТАВОВ: [Кто отсутствует]
ПОГОДА: [1-2 предл.]
СУДЬЯ: [Имя + стата]

ЦИФРЫ:
- Средний тотал: К1 X.X | К2 X.X
- Средний тотал по турниру: [X.X, если есть в данных, иначе "нет данных"]
- ОЗ: X/5 vs Y/5
- Форма: WDL vs WDL
- H2H тотал: X.X

РЕКОМЕНДАЦИИ:
ПОБЕДИТЕЛЬ: [...] | [%]
ФОРА: [...] | [%]
ТОТАЛ: [Б/М X.5] | [%]
ОБЕ ЗАБЬЮТ: [Да/Нет] | [%]
УГЛОВЫЕ: [Б/М X.5] | ≤55%
КАРТОЧКИ: [Б/М X.5] | ≤55%

ГЛАВНАЯ СТАВКА: [одна]
Обоснование: [конкретные цифры]
РИСКИ: [что может пойти не так]

Аналитика, не гарантия."""


def ask_groq(match_name: str, info: str, quality_summary: str) -> str:
    """Отправляет собранные данные матча в Groq и возвращает текстовый анализ."""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Матч: {match_name}\n\n{info}\n{quality_summary}\n\nДай прогноз СТРОГО по цифрам."}
        ],
        "temperature": 0.3,
        "max_tokens": 2500,
    }
    r = None
    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        logger.error("Groq: время истекло для матча '%s'", match_name)
        return "Время истекло."
    except requests.exceptions.HTTPError:
        status = r.status_code if r is not None else "?"
        if status == 429:
            logger.warning("Groq: превышен лимит запросов (429) для матча '%s'", match_name)
            return "Слишком много запросов."
        logger.error("Groq: HTTP ошибка %s для матча '%s'", status, match_name)
        return f"Ошибка Groq: {status}"
    except Exception as e:
        logger.exception("Groq: неожиданная ошибка для матча '%s'", match_name)
        return f"Ошибка: {e}"
