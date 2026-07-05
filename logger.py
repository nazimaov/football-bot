"""Логирование в stdout (Render автоматически подхватывает вывод в свои логи)."""
import logging
import sys


def setup_logging() -> logging.Logger:
    """Настраивает базовое логирование и возвращает логгер проекта."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger("football_bot")
