from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .services import TalentCalculator


class TalentCalculatorTests(SimpleTestCase):
	def test_supported_experience_levels_receive_scores(self):
		expected_scores = {
			"BEGINNER": Decimal("20"),
			"INTERMEDIATE": Decimal("50"),
			"EXPERT": Decimal("80"),
		}

		for level, expected_score in expected_scores.items():
			with self.subTest(level=level):
				profile = SimpleNamespace(experience_level=level)

				scores = TalentCalculator.calculate(profile)

				self.assertEqual(scores["experience"], expected_score)

	def test_physical_score_uses_related_sports_profile(self):
		profile = SimpleNamespace(
			experience_level="BEGINNER",
			sports_profile=SimpleNamespace(
				height=Decimal("180"),
				weight=Decimal("75"),
			),
		)

		scores = TalentCalculator.calculate(profile)

		self.assertEqual(scores["physical"], Decimal("40"))
