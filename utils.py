"""Общие вспомогательные функции: разбор текста матча и извлечение данных из ответов API."""
from match_data import search_team


def split_teams(text: str) -> tuple[str, str]:
    """Умное разделение строки на две команды.
    Поддерживает: vs, -, –, —, /, |, x, против (даже без разделителя через поиск)."""
    text = text.strip()
    separators = [" vs ", " VS ", " v ", " против ", " - ", " – ", " — ", " / ", " | ", " x ", " X "]
    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    for sep in ["-", "–", "—", "/", "|"]:
        if sep in text:
            parts = text.split(sep, 1)
            t1, t2 = parts[0].strip(), parts[1].strip()
            if t1 and t2:
                return t1, t2
    words = text.split()
    if len(words) >= 2:
        best = None
        for i in range(1, len(words)):
            t1 = " ".join(words[:i])
            t2 = " ".join(words[i:])
            r1 = search_team(t1)
            r2 = search_team(t2)
            if r1.get("id") and r2.get("id"):
                return t1, t2
            if not best and (r1.get("id") or r2.get("id")):
                best = (t1, t2)
        if best:
            return best
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return text, ""


def extract_venue_city(*sources) -> tuple[str, str]:
    """Ищет stadium и city во всех возможных местах. Возвращает (stadium, city)."""
    stadium = ""
    city = ""
    for src in sources:
        if not isinstance(src, dict):
            continue
        venue = src.get("venue") or src.get("stadium") or {}
        if isinstance(venue, dict):
            if not stadium:
                stadium = (venue.get("name") or
                           (venue.get("stadium") or {}).get("name", "") if isinstance(venue.get("stadium"), dict) else venue.get("stadium", "") or
                           "")
            if not city:
                c = venue.get("city")
                if isinstance(c, dict):
                    city = c.get("name", "")
                elif isinstance(c, str):
                    city = c
                if not city:
                    city = venue.get("cityName", "") or ""
                if not city:
                    country = venue.get("country", {})
                    if isinstance(country, dict):
                        city = country.get("name", "")
        if not city:
            c = src.get("city") or src.get("cityName")
            if isinstance(c, dict):
                city = c.get("name", "")
            elif isinstance(c, str):
                city = c
    return stadium, city


def extract_referee(*sources) -> tuple[str, dict]:
    """Ищет судью во всех возможных местах."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        ref = src.get("referee")
        if isinstance(ref, dict) and ref.get("name"):
            return ref.get("name"), ref
        if isinstance(ref, str) and ref:
            return ref, {}
    return "", {}
