"""Формирование итогового текста для отправки в Telegram."""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

TELEGRAM_CHUNK_SIZE = 4000
DEVIATION_THRESHOLD_PP = 15  # процентных пунктов — порог расхождения с расчётом Пуассона

_WINNER_RE = re.compile(r"(ПОБЕДИТЕЛЬ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)
_TOTAL_RE = re.compile(r"(ТОТАЛ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)
_BTTS_RE = re.compile(r"(ОБЕ ЗАБЬЮТ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)

# Категории символов, которые модель иногда "выплёвывает" как битые токены
# (private-use area, неразмеченные кодпоинты, суррогаты) — в Telegram это рендерится
# квадратиком-плейсхолдером. Cf (форматирующие) не трогаем — там живут ZWJ/variation
# selector, на которых держатся составные эмодзи вроде 👨‍⚖️.
_JUNK_CATEGORIES = {"Co", "Cn", "Cs"}


def _strip_junk_chars(text: str) -> str:
    """Убирает нерендерящиеся символы-артефакты генерации AI (см. _JUNK_CATEGORIES)."""
    result = []
    for ch in text:
        if ch in ("\n", "\r", "\t"):
            result.append(ch)
            continue
        if ch == "�" or unicodedata.category(ch) in _JUNK_CATEGORIES or unicodedata.category(ch) == "Cc":
            continue
        result.append(ch)
    return "".join(result)


def format_report(ai_text: str) -> str:
    """Финальная обработка текста от AI перед отправкой пользователю."""
    return _strip_junk_chars(ai_text)


def format_verdict_footer(pick: dict) -> str:
    """Детерминированный вердикт модели в конце отчёта — не зависит от текста AI."""
    if not pick:
        return ""
    p = pick.get("prob", 0) * 100
    label = pick.get("label", "?")
    if pick.get("tier") == "confident":
        return (f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 ВЕРДИКТ МОДЕЛИ: ✅ {label} — {p:.0f}%\n"
                f"━━━━━━━━━━━━━━━━━━━━")
    if pick.get("tier") == "moderate":
        return (f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 ВЕРДИКТ МОДЕЛИ: ⚖️ {label} — {p:.0f}% (умеренная уверенность)\n"
                f"━━━━━━━━━━━━━━━━━━━━")
    return (f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 ВЕРДИКТ МОДЕЛИ: ⛔ уверенной ставки нет (максимум {p:.0f}%) — лучше пропустить\n"
            f"━━━━━━━━━━━━━━━━━━━━")


def split_for_telegram(text: str, chunk_size: int = TELEGRAM_CHUNK_SIZE) -> list[str]:
    """Разбивает длинный текст на части, укладывающиеся в лимит сообщения Telegram."""
    if len(text) <= chunk_size:
        return [text]
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def _replace_percent(match: re.Match, new_percent: float) -> str:
    prefix, label, sep = match.group(1), match.group(2), match.group(3)
    return f"{prefix}{label}{sep}{round(new_percent)}%"


def enforce_prediction_consistency(ai_text: str, probs: dict, home_name: str, away_name: str) -> str:
    """Сверяет проценты П1/Х/П2, тотала 2.5 и "обе забьют" в ответе AI с расчётом Пуассона
    (prediction.py). Если расхождение больше DEVIATION_THRESHOLD_PP п.п. — подставляет расчётное
    значение вместо того, что написала модель. Угловые/карточки не проверяются — для них нет
    расчётной модели. Строки, не распознанные по шаблону, оставляет без изменений."""
    if not probs:
        return ai_text
    home_low, away_low = home_name.lower(), away_name.lower()

    def fix_winner(m: re.Match) -> str:
        low = m.group(2).lower()
        if home_low and home_low in low:
            target = probs["home_win"] * 100
        elif away_low and away_low in low:
            target = probs["away_win"] * 100
        elif "ничь" in low or low.strip() in ("х", "x"):
            target = probs["draw"] * 100
        else:
            return m.group(0)
        stated = int(m.group(4))
        if abs(stated - target) > DEVIATION_THRESHOLD_PP:
            logger.info("Скорректирован процент ПОБЕДИТЕЛЬ: %s%% -> %.0f%%", stated, target)
            return _replace_percent(m, target)
        return m.group(0)

    def fix_total(m: re.Match) -> str:
        label = m.group(2)
        low = label.lower().strip()
        if "2.5" not in label and "2,5" not in label:
            return m.group(0)
        # AI пишет и "Больше 2.5", и коротко "Б 2.5"/"ТБ 2.5" — принимаем оба варианта
        if "больш" in low or low.startswith("б") or low.startswith("тб") or "over" in low:
            target = probs["over25"] * 100
        elif "меньш" in low or low.startswith("м") or low.startswith("тм") or "under" in low:
            target = probs["under25"] * 100
        else:
            return m.group(0)
        stated = int(m.group(4))
        if abs(stated - target) > DEVIATION_THRESHOLD_PP:
            logger.info("Скорректирован процент ТОТАЛ: %s%% -> %.0f%%", stated, target)
            return _replace_percent(m, target)
        return m.group(0)

    def fix_btts(m: re.Match) -> str:
        low = m.group(2).lower()
        if "да" in low:
            target = probs["btts_yes"] * 100
        elif "нет" in low:
            target = probs["btts_no"] * 100
        else:
            return m.group(0)
        stated = int(m.group(4))
        if abs(stated - target) > DEVIATION_THRESHOLD_PP:
            logger.info("Скорректирован процент ОБЕ ЗАБЬЮТ: %s%% -> %.0f%%", stated, target)
            return _replace_percent(m, target)
        return m.group(0)

    ai_text = _WINNER_RE.sub(fix_winner, ai_text)
    ai_text = _TOTAL_RE.sub(fix_total, ai_text)
    ai_text = _BTTS_RE.sub(fix_btts, ai_text)
    return ai_text
