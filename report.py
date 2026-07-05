"""Формирование итогового текста для отправки в Telegram."""
import logging
import re

logger = logging.getLogger(__name__)

TELEGRAM_CHUNK_SIZE = 4000
DEVIATION_THRESHOLD_PP = 15  # процентных пунктов — порог расхождения с расчётом Пуассона

_WINNER_RE = re.compile(r"(ПОБЕДИТЕЛЬ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)
_TOTAL_RE = re.compile(r"(ТОТАЛ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)
_BTTS_RE = re.compile(r"(ОБЕ ЗАБЬЮТ\s*:\s*)(.*?)(\|\s*)(\d+)\s*%", re.IGNORECASE)


def format_report(ai_text: str) -> str:
    """Финальная обработка текста от AI перед отправкой пользователю."""
    return ai_text


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
        low = label.lower()
        if "2.5" not in label and "2,5" not in label:
            return m.group(0)
        if "больш" in low:
            target = probs["over25"] * 100
        elif "меньш" in low:
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
