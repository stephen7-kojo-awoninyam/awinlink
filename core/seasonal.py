import logging
import unicodedata
from datetime import date, timedelta
from functools import lru_cache

import holidays
from django.utils import timezone


logger = logging.getLogger(__name__)

SEASONS = {
    "christmas": (
        "Holiday season",
        "Wishing our community a joyful holiday season.",
        "bi-stars",
    ),
    "ramadan": (
        "Ramadan Kareem",
        "Wishing you a peaceful and generous Ramadan.",
        "bi-moon-stars",
    ),
    "eid": (
        "Eid Mubarak",
        "Wishing you joy, peace, and connection.",
        "bi-stars",
    ),
    "easter": (
        "Happy Easter",
        "Wishing our community a joyful Easter.",
        "bi-flower1",
    ),
    "independence": (
        "Independence Day",
        "Celebrating independence and the strength of our community.",
        "bi-flag",
    ),
}


def _easter_sunday(year):
    """Return the Gregorian Easter Sunday for the given year."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _normalize_holiday_name(name):
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", name.casefold())
        if not unicodedata.combining(character)
    )


def _is_eid_al_fitr(name):
    return (
        ("eid" in name and ("fitr" in name or "fitri" in name))
        or "korite" in name
        or "hari raya puasa" in name
        or "aidilfitri" in name
        or "idul fitri" in name
        or "lebaran" in name
    )


def _is_eid_al_adha(name):
    return (
        ("eid" in name and "adha" in name)
        or "bakrid" in name
        or "tabaski" in name
        or "hari raya haji" in name
    )


@lru_cache(maxsize=256)
def _country_holidays(country_code, year):
    if not country_code or len(country_code) != 2:
        return {}

    try:
        return holidays.country_holidays(
            country_code.upper(),
            years=range(year - 1, year + 2),
        )
    except NotImplementedError:
        logger.warning(
            "No seasonal holiday calendar is available for country code %s.",
            country_code,
        )
        return {}


def get_season(country_code="", today=None):
    today = today or timezone.localdate()

    if (today.month == 12 and today.day >= 15) or (
        today.month == 1 and today.day <= 2
    ):
        return "christmas"

    observed_holidays = _country_holidays(country_code, today.year)
    normalized_holidays = [
        (holiday_date, _normalize_holiday_name(name))
        for holiday_date, name in observed_holidays.items()
    ]

    independence_names = (
        "independence",
        "national day",
        "republic day",
        "founding day",
    )
    for holiday_date, name in normalized_holidays:
        if any(keyword in name for keyword in independence_names) and abs(
            (today - holiday_date).days
        ) <= 3:
            return "independence"

    for holiday_date, name in normalized_holidays:
        if _is_eid_al_fitr(name):
            estimated_ramadan_start = holiday_date - timedelta(days=30)
            if estimated_ramadan_start - timedelta(days=1) <= today < holiday_date:
                return "ramadan"

    for holiday_date, name in normalized_holidays:
        if "ramadan" in name or "ramazan" in name:
            if "eid" not in name and holiday_date - timedelta(days=1) <= today <= (
                holiday_date + timedelta(days=32)
            ):
                return "ramadan"

        if (_is_eid_al_fitr(name) or _is_eid_al_adha(name)) and abs(
            (today - holiday_date).days
        ) <= 2:
            return "eid"

    easter_sunday = _easter_sunday(today.year)
    if easter_sunday - timedelta(days=2) <= today <= (
        easter_sunday + timedelta(days=1)
    ):
        return "easter"

    return ""


def seasonal_theme(request):
    country_code = ""
    if request.user.is_authenticated:
        country_code = request.user.country or ""

    theme = get_season(country_code)
    title, message, icon = SEASONS.get(theme, ("", "", ""))
    return {
        "seasonal_theme": theme,
        "seasonal_title": title,
        "seasonal_message": message,
        "seasonal_icon": icon,
    }
