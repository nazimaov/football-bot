"""Формирование итогового текста для отправки в Telegram."""

TELEGRAM_CHUNK_SIZE = 4000


def format_report(ai_text: str) -> str:
    """Финальная обработка текста от AI перед отправкой пользователю."""
    return ai_text


def split_for_telegram(text: str, chunk_size: int = TELEGRAM_CHUNK_SIZE) -> list[str]:
    """Разбивает длинный текст на части, укладывающиеся в лимит сообщения Telegram."""
    if len(text) <= chunk_size:
        return [text]
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
