"""Коэффициенты букмекеров через RapidAPI (SofaScore).

Конвертирует кэфы в имплайд-вероятности и убирает маржу букмекера нормировкой.
Рынок — самый сильный доступный предиктор исхода: в коэффициентах уже учтены
составы, травмы, мотивация и всё, что знает рынок.
"""
import logging

import requests

from config import SOFA_BASE, RAPIDAPI_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def _to_decimal(value) -> float | None:
    """'13/10' -> 2.3 (фракционный кэф), '2.30' -> 2.3. None если распарсить нельзя."""
    if value is None:
        return None
    s = str(value).strip()
    try:
        if "/" in s:
            num, den = s.split("/", 1)
            return 1.0 + float(num) / float(den)
        d = float(s)
        return d if d > 1.0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _implied(decimals: dict[str, float]) -> dict[str, float]:
    """Декимал-кэфы -> вероятности, нормированные к 1 (маржа букмекера убрана)."""
    inv = {k: 1.0 / v for k, v in decimals.items() if v and v > 1.0}
    total = sum(inv.values())
    if not inv or total <= 0:
        return {}
    return {k: p / total for k, p in inv.items()}


def _market_decimals(market: dict) -> dict[str, float]:
    decimals = {}
    for c in market.get("choices", []):
        cname = (c.get("name") or "").strip().lower()
        dec = _to_decimal(c.get("fractionalValue") or c.get("decimalValue") or c.get("initialFractionalValue"))
        if cname and dec:
            decimals[cname] = dec
    return decimals


def get_odds(match_id: int | None) -> dict:
    """Вероятности по рынку букмекеров: 1X2, тотал 2.5, обе забьют.
    Возвращает {} если matchId нет или коэффициенты недоступны."""
    if not match_id:
        return {}
    try:
        url = f"{SOFA_BASE}/matches/get-all-odds"
        params = {"matchId": str(match_id)}
        r = requests.get(url, headers=RAPIDAPI_HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.info("get_odds(%s): статус %s", match_id, r.status_code)
            return {}
        markets = r.json().get("markets", [])
        result = {}
        for market in markets:
            name = (market.get("marketName") or "").lower()
            group = str(market.get("choiceGroup") or "").strip()
            probs = _implied(_market_decimals(market))
            if not probs:
                continue
            if "full time" in name and not group and {"1", "x", "2"} <= set(probs):
                result["1x2"] = {"home": probs["1"], "draw": probs["x"], "away": probs["2"]}
            elif "both teams" in name and {"yes", "no"} <= set(probs):
                result["btts"] = {"yes": probs["yes"], "no": probs["no"]}
            elif ("match goals" in name or "total" in name) and group == "2.5" and {"over", "under"} <= set(probs):
                result["total25"] = {"over": probs["over"], "under": probs["under"]}
        return result
    except Exception:
        logger.exception("Ошибка get_odds(%s)", match_id)
        return {}


def format_odds_text(odds: dict, home_name: str, away_name: str) -> str:
    """Текстовый блок с рыночными вероятностями для контекста AI."""
    if not odds:
        return "\n[!] Коэффициенты букмекеров недоступны\n"
    text = "\n=== РЫНОК БУКМЕКЕРОВ (вероятности без маржи) ===\n"
    m = odds.get("1x2")
    if m:
        text += (f"  П1 ({home_name}): {m['home']*100:.0f}% | Х: {m['draw']*100:.0f}% "
                 f"| П2 ({away_name}): {m['away']*100:.0f}%\n")
    t = odds.get("total25")
    if t:
        text += f"  Тотал 2.5: Б {t['over']*100:.0f}% / М {t['under']*100:.0f}%\n"
    b = odds.get("btts")
    if b:
        text += f"  Обе забьют: Да {b['yes']*100:.0f}% / Нет {b['no']*100:.0f}%\n"
    return text
