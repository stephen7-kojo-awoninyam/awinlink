from datetime import date

import holidays
from django.test import SimpleTestCase

from .seasonal import get_season


class SeasonalThemeTests(SimpleTestCase):
    def test_christmas_theme_is_available_without_a_country(self):
        self.assertEqual(get_season(today=date(2026, 12, 25)), "christmas")

    def test_easter_theme_uses_the_gregorian_easter_date(self):
        self.assertEqual(get_season(today=date(2026, 4, 3)), "easter")

    def test_independence_theme_uses_the_users_country_calendar(self):
        self.assertEqual(
            get_season("GH", today=date(2026, 3, 6)),
            "independence",
        )

    def test_ramadan_theme_uses_the_users_country_calendar(self):
        ghana_holidays = holidays.country_holidays("GH", years=[2026])
        eid_al_fitr = next(
            holiday_date
            for holiday_date, name in ghana_holidays.items()
            if "eid" in name.casefold() and "fitr" in name.casefold()
        )

        self.assertEqual(
            get_season("GH", today=eid_al_fitr - date.resolution * 10),
            "ramadan",
        )

    def test_eid_theme_uses_the_users_country_calendar(self):
        ghana_holidays = holidays.country_holidays("GH", years=[2026])
        eid_dates = [
            holiday_date
            for holiday_date, name in ghana_holidays.items()
            if "eid" in name.casefold()
        ]

        self.assertTrue(eid_dates)
        for eid_date in eid_dates:
            with self.subTest(eid_date=eid_date):
                self.assertEqual(get_season("GH", today=eid_date), "eid")
