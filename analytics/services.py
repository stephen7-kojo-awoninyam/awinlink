from decimal import Decimal

from analytics.models import TalentScore


class TalentCalculator:

    # =====================================================
    # CALCULATE TALENT SCORE
    # =====================================================

    @staticmethod
    def calculate(profile):

        physical = Decimal("0")
        performance = Decimal("0")
        achievements = Decimal("0")
        experience = Decimal("0")
        verification = Decimal("0")

        # =================================================
        # PHYSICAL SCORE
        # =================================================
        #
        # Physical attributes are optional for a general
        # talent platform, so we only award points when
        # the information exists.
        # =================================================

        physical_fields = 0

        if getattr(profile, "height", None):
            physical_fields += 1

        if getattr(profile, "weight", None):
            physical_fields += 1

        if physical_fields:
            physical = Decimal(
                physical_fields * 20
            )

        # =================================================
        # EXPERIENCE SCORE
        # =================================================

        levels = {
            "BEGINNER": Decimal("20"),
            "AMATEUR": Decimal("50"),
            "PROFESSIONAL": Decimal("80"),
            "ELITE": Decimal("100"),
        }

        experience = levels.get(
            getattr(
                profile,
                "experience_level",
                None
            ),
            Decimal("0")
        )

        # =================================================
        # VERIFICATION SCORE
        # =================================================

        if getattr(profile, "verified", False):

            verification = Decimal("100")

        # =================================================
        # ACHIEVEMENT SCORE
        # =================================================

        achievement_manager = getattr(
            profile,
            "achievements",
            None
        )

        if achievement_manager:

            achievement_count = (
                achievement_manager.count()
            )

            achievements = min(
                Decimal(
                    achievement_count * 20
                ),
                Decimal("100")
            )

        # =================================================
        # PERFORMANCE SCORE
        # =================================================
        #
        # Calculate from application outcomes where
        # possible.
        #
        # Accepted = strongest evidence
        # Reviewing = moderate evidence
        # Pending = some evidence
        #
        # If there are no applications yet, performance
        # remains 0 rather than inventing a score.
        # =================================================

        applications_manager = getattr(
            profile,
            "applications",
            None
        )

        if applications_manager:

            total_applications = (
                applications_manager.count()
            )

            if total_applications:

                accepted = applications_manager.filter(
                    status="ACCEPTED"
                ).count()

                reviewing = applications_manager.filter(
                    status="REVIEWING"
                ).count()

                pending = applications_manager.filter(
                    status="PENDING"
                ).count()

                performance = (
                    Decimal(accepted) * Decimal("100")
                    + Decimal(reviewing) * Decimal("60")
                    + Decimal(pending) * Decimal("30")
                ) / Decimal(total_applications)

                performance = min(
                    performance,
                    Decimal("100")
                )

        # =================================================
        # OVERALL SCORE
        # =================================================

        overall = (
            physical * Decimal("0.20")
            + performance * Decimal("0.35")
            + achievements * Decimal("0.20")
            + experience * Decimal("0.15")
            + verification * Decimal("0.10")
        )

        overall = min(
            overall,
            Decimal("100")
        )

        # =================================================
        # RETURN SCORES
        # =================================================

        return {
            "physical": physical,
            "performance": performance,
            "achievements": achievements,
            "experience": experience,
            "verification": verification,
            "overall": overall,
        }

    # =====================================================
    # UPDATE / SAVE TALENT SCORE
    # =====================================================

    @staticmethod
    def update_score(profile):

        scores = TalentCalculator.calculate(
            profile
        )

        talent_score, created = TalentScore.objects.update_or_create(
            talent=profile,
            defaults={
                "physical_score": scores["physical"],
                "performance_score": scores["performance"],
                "achievement_score": scores["achievements"],
                "experience_score": scores["experience"],
                "verification_score": scores["verification"],
                "overall_score": scores["overall"],
            }
        )

        return talent_score