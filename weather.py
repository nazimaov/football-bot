"""Погода в городе матча через OpenWeather."""
import logging

import requests

from config import OPENWEATHER_KEY

logger = logging.getLogger(__name__)


def get_weather(city: str) -> str:
    """Текстовый блок с погодой. Возвращает '' если нет ключа или города."""
    if not OPENWEATHER_KEY or not city:
        return ""
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_KEY, "units": "metric", "lang": "ru"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            logger.warning("get_weather(%s): статус %s", city, r.status_code)
            return f"\n[!] Погода для {city} недоступна\n"
        d = r.json()
        temp = d.get("main", {}).get("temp")
        feels = d.get("main", {}).get("feels_like")
        wind = d.get("wind", {}).get("speed")
        desc = d.get("weather", [{}])[0].get("description", "")
        humidity = d.get("main", {}).get("humidity")
        result = f"\n=== ПОГОДА в {city} ===\n"
        result += f"  {desc.capitalize()} | {temp}°C (ощущ. {feels}°C)\n"
        result += f"  Ветер: {wind} м/с | Влажность: {humidity}%\n"
        warnings = []
        if isinstance(wind, (int, float)) and wind > 8: warnings.append("сильный ветер")
        if isinstance(temp, (int, float)):
            if temp < 3: warnings.append("холодно")
            elif temp > 28: warnings.append("жара")
        if "дожд" in desc.lower() or "rain" in desc.lower(): warnings.append("дождь")
        if warnings:
            result += "  ⚠ " + ", ".join(warnings) + "\n"
        return result
    except Exception as e:
        logger.exception("Ошибка get_weather(%s)", city)
        return f"\n[!] Погода: {e}\n"
