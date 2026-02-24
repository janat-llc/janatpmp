"""Temporal Affinity Engine — grounding context from time + location.

R17: Pure-function module. No external APIs, no pip dependencies beyond stdlib.
Takes current time + geographic coordinates, returns a temporal context dict
with time-of-day, season, sunrise/sunset, estimated temperature range, etc.

All defaults match Mat's house in Fargo, ND (46.8290N, 96.8540W).
Sunrise/sunset accuracy: ~10-15 minutes (standard solar position equations).
Temperature: static monthly averages from NOAA climate normals, not a forecast.
"""

import math
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from atlas.config import LOCATION_LAT, LOCATION_LON, LOCATION_NAME, LOCATION_TZ

logger = logging.getLogger(__name__)

# Average low/high temperatures (F) by month for Fargo, ND (NOAA normals)
_FARGO_TEMPS_F: dict[int, tuple[int, int]] = {
    1:  (-2, 17),
    2:  (3, 23),
    3:  (16, 36),
    4:  (30, 53),
    5:  (43, 67),
    6:  (53, 76),
    7:  (58, 82),
    8:  (55, 80),
    9:  (44, 69),
    10: (31, 55),
    11: (17, 36),
    12: (2, 21),
}


def _solar_declination(day_of_year: int) -> float:
    """Solar declination in degrees. Accurate to ~0.5 degrees."""
    return 23.45 * math.sin(math.radians(360.0 / 365.0 * (day_of_year - 81)))


def _hour_angle(latitude: float, declination: float) -> float | None:
    """Hour angle for sunrise/sunset in degrees. None during polar conditions."""
    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)
    cos_ha = -math.tan(lat_rad) * math.tan(dec_rad)
    if cos_ha < -1.0 or cos_ha > 1.0:
        return None  # Polar day or polar night
    return math.degrees(math.acos(cos_ha))


def _sunrise_sunset(
    lat: float, lon: float, dt: datetime,
) -> tuple[datetime | None, datetime | None]:
    """Approximate sunrise and sunset in local time. ~10-15 min accuracy."""
    doy = dt.timetuple().tm_yday
    dec = _solar_declination(doy)
    ha = _hour_angle(lat, dec)
    if ha is None:
        return None, None

    utc_offset = dt.utcoffset()
    tz_hours = utc_offset.total_seconds() / 3600.0 if utc_offset else 0.0

    # Solar noon offset: difference between clock noon and solar noon
    noon_offset = (tz_hours * 15.0 - lon) / 15.0
    solar_noon = 12.0 + noon_offset

    daylight_half = ha / 15.0  # hours from noon to sunrise/sunset
    sunrise_hours = solar_noon - daylight_half
    sunset_hours = solar_noon + daylight_half

    base = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    sunrise = base + timedelta(hours=sunrise_hours)
    sunset = base + timedelta(hours=sunset_hours)
    return sunrise, sunset


def _time_of_day(hour: int) -> str:
    """Map hour (0-23) to time-of-day label."""
    if 5 <= hour < 8:
        return "early morning"
    if 8 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _greeting_hint(hour: int) -> str:
    """Appropriate greeting for the time of day."""
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 21:
        return "Good evening"
    return "Good evening"


def _season(month: int, lat: float) -> str:
    """Season from month. Hemisphere-aware (lat sign flips for southern)."""
    northern = {12: "winter", 1: "winter", 2: "winter",
                3: "spring", 4: "spring", 5: "spring",
                6: "summer", 7: "summer", 8: "summer",
                9: "fall", 10: "fall", 11: "fall"}
    s = northern.get(month, "unknown")
    if lat < 0:
        flip = {"winter": "summer", "summer": "winter",
                "spring": "fall", "fall": "spring"}
        s = flip.get(s, s)
    return s


def _temp_range_f(month: int) -> tuple[int, int]:
    """Average low/high F for Fargo, ND by month."""
    return _FARGO_TEMPS_F.get(month, (20, 40))


def _f_to_c(f: int) -> int:
    """Fahrenheit to Celsius, rounded."""
    return round((f - 32) * 5 / 9)


def get_temporal_context(
    lat: float = LOCATION_LAT,
    lon: float = LOCATION_LON,
    timezone: str = LOCATION_TZ,
    now: datetime | None = None,
) -> dict:
    """Build temporal context from current time + location.

    Args:
        lat: Latitude in decimal degrees (positive = north).
        lon: Longitude in decimal degrees (negative = west).
        timezone: IANA timezone string (e.g. 'America/Chicago').
        now: Override current time for testing. Defaults to datetime.now(tz).

    Returns:
        Dict with time_of_day, day_of_week, date_formatted, season,
        sunrise, sunset, daylight_hours, temp_range_f, temp_range_c,
        location_name, greeting_hint.
    """
    tz = ZoneInfo(timezone)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    hour = now.hour
    month = now.month

    sunrise_dt, sunset_dt = _sunrise_sunset(lat, lon, now)
    if sunrise_dt and sunset_dt:
        daylight_seconds = (sunset_dt - sunrise_dt).total_seconds()
        daylight_hours = round(daylight_seconds / 3600.0, 1)
        sunrise_str = sunrise_dt.strftime("%I:%M %p").lstrip("0")
        sunset_str = sunset_dt.strftime("%I:%M %p").lstrip("0")
    else:
        daylight_hours = 0.0
        sunrise_str = "N/A"
        sunset_str = "N/A"

    low_f, high_f = _temp_range_f(month)
    low_c, high_c = _f_to_c(low_f), _f_to_c(high_f)

    # Extract city name from full address for conversational display
    location_name = LOCATION_NAME
    parts = location_name.split(",")
    if len(parts) >= 2:
        display_location = ",".join(parts[-2:]).strip()
    else:
        display_location = location_name

    return {
        "time_of_day": _time_of_day(hour),
        "day_of_week": now.strftime("%A"),
        "date_formatted": now.strftime("%A, %B %d, %Y"),
        "season": _season(month, lat),
        "sunrise": sunrise_str,
        "sunset": sunset_str,
        "daylight_hours": daylight_hours,
        "temp_range_f": (low_f, high_f),
        "temp_range_c": (low_c, high_c),
        "location_name": display_location,
        "greeting_hint": _greeting_hint(hour),
        "hour": hour,
        "month": month,
        "timezone": timezone,
    }


def format_temporal_prompt(ctx: dict) -> str:
    """Format temporal context as natural language for system prompt injection.

    Args:
        ctx: Dict from get_temporal_context().

    Returns:
        Multi-line string suitable for injection into system prompt.
    """
    low_f, high_f = ctx["temp_range_f"]
    low_c, high_c = ctx["temp_range_c"]

    lines = [
        f"It is {ctx['date_formatted']}, {ctx['time_of_day']}.",
        f"You are in {ctx['location_name']}.",
        f"The sun rose at {ctx['sunrise']} and will set at {ctx['sunset']}"
        f" (~{ctx['daylight_hours']} hours of daylight).",
        f"It is {ctx['season']} — typical temperatures today range"
        f" from {low_f}\u00b0F to {high_f}\u00b0F ({low_c}\u00b0C to {high_c}\u00b0C).",
    ]
    return "\n".join(lines)
