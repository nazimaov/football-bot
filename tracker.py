"""Журнал прогнозов и подсчёт реальной точности.

Каждый прогноз сохраняется в JSON-файл; когда матч завершается, результат
подтягивается и сравнивается с прогнозом. Команда /stats показывает реальный
процент попаданий — без этого "точность" бота нельзя ни измерить, ни улучшить.

Ограничение: на бесплатном Render файловая система эфемерная — журнал
обнуляется при редеплое/рестарте сервиса.
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions_log.json")
MIN_SECONDS_AFTER_START = 3 * 3600  # проверяем результат не раньше чем через 3 часа после начала


def _load() -> list:
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        logger.exception("Не удалось прочитать журнал прогнозов")
    return []


def _save(entries: list) -> None:
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
    except Exception:
        logger.exception("Не удалось сохранить журнал прогнозов")


def log_prediction(match_id: int, start_ts: int, home: str, away: str, probs: dict, pick: dict) -> None:
    """Сохраняет/обновляет прогноз по матчу (повторный запрос того же матча перезаписывает)."""
    if not match_id or not probs:
        return
    entries = _load()
    entries = [e for e in entries if e.get("match_id") != match_id]
    entries.append({
        "match_id": match_id,
        "start_ts": start_ts,
        "home": home,
        "away": away,
        "probs": {k: round(v, 4) for k, v in probs.items() if isinstance(v, (int, float))},
        "pick": pick or {},
        "created_at": int(time.time()),
        "result": None,
    })
    _save(entries)


def _outcome_hit(code: str, hs: int, as_: int) -> bool:
    """Сбылась ли ставка с данным кодом при счёте hs:as_."""
    total = hs + as_
    return {
        "home": hs > as_,
        "away": as_ > hs,
        "dc_1x": hs >= as_,
        "dc_x2": as_ >= hs,
        "over25": total > 2,
        "under25": total <= 2,
        "btts_yes": hs > 0 and as_ > 0,
        "btts_no": hs == 0 or as_ == 0,
    }.get(code, False)


def _winner_pred_code(probs: dict) -> str:
    trio = {"home": probs.get("home_win", 0), "draw": probs.get("draw", 0), "away": probs.get("away_win", 0)}
    return max(trio, key=trio.get)


def evaluate_pending(get_match_detail) -> None:
    """Подтягивает результаты завершённых матчей и записывает попадания.
    get_match_detail — функция match_data.get_match_detail (инъекция, чтобы не плодить импорты)."""
    entries = _load()
    now = time.time()
    changed = False
    for e in entries:
        if e.get("result") is not None:
            continue
        if now - e.get("start_ts", 0) < MIN_SECONDS_AFTER_START:
            continue
        detail = get_match_detail(e["match_id"]) or {}
        status = (detail.get("status") or {}).get("type", "")
        hs = (detail.get("homeScore") or {}).get("current")
        as_ = (detail.get("awayScore") or {}).get("current")
        if status != "finished" or hs is None or as_ is None:
            continue
        probs = e.get("probs", {})
        winner_actual = "home" if hs > as_ else ("away" if as_ > hs else "draw")
        pick = e.get("pick") or {}
        e["result"] = {
            "score": f"{hs}:{as_}",
            "winner_hit": _winner_pred_code(probs) == winner_actual,
            "total_hit": (probs.get("over25", 0) >= 0.5) == (hs + as_ > 2) if "over25" in probs else None,
            "btts_hit": (probs.get("btts_yes", 0) >= 0.5) == (hs > 0 and as_ > 0) if "btts_yes" in probs else None,
            "pick_hit": _outcome_hit(pick.get("code", ""), hs, as_) if pick.get("tier") in ("confident", "moderate") else None,
            "pick_tier": pick.get("tier"),
        }
        changed = True
    if changed:
        _save(entries)


def format_stats_text() -> str:
    """Сводка точности по завершённым матчам из журнала."""
    entries = [e for e in _load() if e.get("result")]
    if not entries:
        return ("📊 Пока нет завершённых матчей с прогнозами.\n"
                "Сделай несколько прогнозов, дождись окончания матчей и вызови /stats снова.")

    def rate(key: str, subset=None) -> tuple[int, int]:
        pool = subset if subset is not None else entries
        vals = [e["result"][key] for e in pool if e["result"].get(key) is not None]
        return sum(vals), len(vals)

    w_hit, w_n = rate("winner_hit")
    t_hit, t_n = rate("total_hit")
    b_hit, b_n = rate("btts_hit")
    confident = [e for e in entries if e["result"].get("pick_tier") == "confident"]
    p_hit, p_n = rate("pick_hit", confident)

    def line(label: str, hit: int, n: int) -> str:
        if n == 0:
            return f"  {label}: нет данных\n"
        return f"  {label}: {hit}/{n} ({hit / n * 100:.0f}%)\n"

    text = f"📊 ТОЧНОСТЬ ПРОГНОЗОВ ({len(entries)} завершённых матчей):\n\n"
    text += line("Исход матча (П1/Х/П2)", w_hit, w_n)
    text += line("Тотал 2.5", t_hit, t_n)
    text += line("Обе забьют", b_hit, b_n)
    text += line("🎯 Уверенные ставки", p_hit, p_n)
    text += "\nЖурнал обнуляется при редеплое сервиса."
    return text
