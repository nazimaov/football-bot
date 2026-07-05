"""Данные о судье матча (извлекаются из match/match_detail, полученных в match_data.py)."""
import logging

from utils import extract_referee

logger = logging.getLogger(__name__)


def get_referee_text(match: dict, detail: dict) -> tuple[str, str]:
    """Возвращает (имя_судьи, текст_для_промпта). Статистика судьи доступна не всегда."""
    ref_name, ref_data = extract_referee(match, detail)
    if not ref_name:
        logger.info("Судья не назначен или не указан в API")
        return "", "\n[!] Судья не назначен или не указан в API\n"

    text = f"\n=== СУДЬЯ: {ref_name} ===\n"
    if ref_data:
        yc = ref_data.get("yellowCards")
        rc = ref_data.get("redCards")
        games = ref_data.get("games")
        if games:
            text += f"  Матчей: {games}\n"
        if yc is not None and games:
            text += f"  Жёлтых: {yc} ({yc/games:.1f}/матч)\n"
        if rc is not None:
            text += f"  Красных: {rc}\n"
    return ref_name, text
