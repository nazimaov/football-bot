"""Статистическая модель прогноза (распределение Пуассона) на основе среднего голов команд.

Считает вероятности исходов/тотала/ОЗ независимо от AI, чтобы финальные проценты
в ответе опирались на реальный расчёт, а не только на текстовое "мнение" модели.
"""
import math

LEAGUE_AVG_GOALS_FALLBACK = 2.6  # средний тотал футбольного матча, если нет данных по турниру
HOME_ADVANTAGE = 1.10
AWAY_DISADVANTAGE = 0.92
MAX_GOALS = 6  # диапазон суммирования распределения Пуассона (0..6 голов на команду)


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def estimate_expected_goals(home_stats: dict, away_stats: dict, league_avg: float | None) -> tuple | None:
    """Считает ожидаемые голы хозяев/гостей по их среднему голов за/против.
    None если по одной из команд нет статистики (compute_scoring_stats вернул {})."""
    if not home_stats or not away_stats:
        return None
    lam_home = (home_stats["avg_scored"] + away_stats["avg_conceded"]) / 2
    lam_away = (away_stats["avg_scored"] + home_stats["avg_conceded"]) / 2
    lam_home *= HOME_ADVANTAGE
    lam_away *= AWAY_DISADVANTAGE
    lam_home = max(lam_home, 0.1)
    lam_away = max(lam_away, 0.1)
    return lam_home, lam_away


def compute_probabilities(lam_home: float, lam_away: float) -> dict:
    """Вероятности П1/Х/П2, тотала Б/М 2.5 и обе забьют — по независимому распределению Пуассона."""
    home_win = draw = away_win = 0.0
    over25 = 0.0
    btts = 0.0
    for i in range(MAX_GOALS + 1):
        p_i = _poisson_pmf(i, lam_home)
        for j in range(MAX_GOALS + 1):
            p_j = _poisson_pmf(j, lam_away)
            p = p_i * p_j
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            if i + j > 2:
                over25 += p
            if i > 0 and j > 0:
                btts += p
    return {
        "home_win": home_win, "draw": draw, "away_win": away_win,
        "over25": over25, "under25": 1 - over25,
        "btts_yes": btts, "btts_no": 1 - btts,
        "expected_goals_home": lam_home, "expected_goals_away": lam_away,
    }


def format_prediction_text(probs: dict, home_name: str, away_name: str) -> str:
    """Текстовый блок с расчётными вероятностями — опорные цифры для AI. '' если расчёта нет."""
    if not probs:
        return ""
    text = "\n=== РАСЧЁТНАЯ МОДЕЛЬ (Пуассон, по среднему голов) ===\n"
    if "expected_goals_home" in probs:
        text += f"  Ожидаемые голы: {home_name} {probs['expected_goals_home']:.2f} | {away_name} {probs['expected_goals_away']:.2f}\n"
    text += f"  П1: {probs['home_win']*100:.0f}% | Х: {probs['draw']*100:.0f}% | П2: {probs['away_win']*100:.0f}%\n"
    text += f"  Тотал 2.5: Б {probs['over25']*100:.0f}% / М {probs['under25']*100:.0f}%\n"
    text += f"  Обе забьют: Да {probs['btts_yes']*100:.0f}% / Нет {probs['btts_no']*100:.0f}%\n"
    return text


# ------------------------------------------------------------------
# Смешивание с рынком букмекеров и выбор уверенной ставки
# ------------------------------------------------------------------
ODDS_WEIGHT = 0.70  # доля рынка в смеси: рынок исторически точнее любительской модели
CONFIDENT_THRESHOLD = 0.70   # "уверенная ставка"
MODERATE_THRESHOLD = 0.62    # "умеренная ставка"


def _blend_group(model: dict | None, market: dict | None, keys: list[str]) -> dict:
    """Взвешенная смесь по группе исходов + нормировка к 1. Работает и если один источник пуст."""
    if model and market:
        raw = {k: (1 - ODDS_WEIGHT) * model[k] + ODDS_WEIGHT * market[k] for k in keys}
    elif market:
        raw = {k: market[k] for k in keys}
    elif model:
        raw = {k: model[k] for k in keys}
    else:
        return {}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def blend_with_odds(model_probs: dict | None, odds: dict) -> dict:
    """Итоговые вероятности: Пуассон 30% + рынок 70% (по рынкам, где есть кэфы).
    Если кэфов нет — возвращает модель как есть. Если нет модели — только рынок."""
    model_probs = model_probs or {}
    if not odds:
        return dict(model_probs)

    result = dict(model_probs)

    m = odds.get("1x2")
    model_1x2 = ({"home": model_probs["home_win"], "draw": model_probs["draw"], "away": model_probs["away_win"]}
                 if "home_win" in model_probs else None)
    blended = _blend_group(model_1x2, m, ["home", "draw", "away"])
    if blended:
        result["home_win"], result["draw"], result["away_win"] = blended["home"], blended["draw"], blended["away"]

    t = odds.get("total25")
    model_t = ({"over": model_probs["over25"], "under": model_probs["under25"]}
               if "over25" in model_probs else None)
    blended = _blend_group(model_t, t, ["over", "under"])
    if blended:
        result["over25"], result["under25"] = blended["over"], blended["under"]

    b = odds.get("btts")
    model_b = ({"yes": model_probs["btts_yes"], "no": model_probs["btts_no"]}
               if "btts_yes" in model_probs else None)
    blended = _blend_group(model_b, b, ["yes", "no"])
    if blended:
        result["btts_yes"], result["btts_no"] = blended["yes"], blended["no"]

    return result


def pick_best_bet(probs: dict, home_name: str, away_name: str) -> dict:
    """Выбирает самую вероятную ставку из одиночных исходов, двойных шансов, тотала и ОЗ.
    Возвращает {"label", "prob", "code", "tier"}; tier: confident / moderate / none.
    Ничья как одиночная ставка не предлагается — она почти никогда не бывает уверенной."""
    if not probs or "home_win" not in probs:
        return {}
    candidates = [
        (f"Победа {home_name}", probs["home_win"], "home"),
        (f"Победа {away_name}", probs["away_win"], "away"),
        (f"1X ({home_name} не проиграет)", probs["home_win"] + probs["draw"], "dc_1x"),
        (f"X2 ({away_name} не проиграет)", probs["away_win"] + probs["draw"], "dc_x2"),
    ]
    if "over25" in probs:
        candidates.append(("Тотал больше 2.5", probs["over25"], "over25"))
        candidates.append(("Тотал меньше 2.5", probs["under25"], "under25"))
    if "btts_yes" in probs:
        candidates.append(("Обе забьют: Да", probs["btts_yes"], "btts_yes"))
        candidates.append(("Обе забьют: Нет", probs["btts_no"], "btts_no"))

    label, prob, code = max(candidates, key=lambda c: c[1])
    if prob >= CONFIDENT_THRESHOLD:
        tier = "confident"
    elif prob >= MODERATE_THRESHOLD:
        tier = "moderate"
    else:
        tier = "none"
    return {"label": label, "prob": prob, "code": code, "tier": tier}


def format_verdict_text(pick: dict) -> str:
    """Детерминированный вердикт модели — вставляется в данные для AI и в итоговый отчёт."""
    if not pick:
        return ""
    p = pick["prob"] * 100
    if pick["tier"] == "confident":
        return f"\n=== ВЕРДИКТ МОДЕЛИ ===\n  УВЕРЕННАЯ СТАВКА: {pick['label']} ({p:.0f}%)\n"
    if pick["tier"] == "moderate":
        return f"\n=== ВЕРДИКТ МОДЕЛИ ===\n  Умеренная ставка: {pick['label']} ({p:.0f}%) — играть осторожно\n"
    return (f"\n=== ВЕРДИКТ МОДЕЛИ ===\n  УВЕРЕННОЙ СТАВКИ НЕТ: максимум {pick['label']} ({p:.0f}%), "
            f"это ниже порога уверенности — лучше пропустить матч\n")
