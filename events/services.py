import uuid

from .models import EventCertificate, EventRegistration


class EventRecommendationEngine:

    @staticmethod
    def calculate_score(talent, event):

        score = 0

        # ==========================================
        # DOMAIN MATCHING
        # ==========================================

        if event.category and event.category.domain:

            if talent.domains.filter(
                id=event.category.domain.id
            ).exists():

                score += 40

        # ==========================================
        # LOCATION MATCHING
        # ==========================================

        if (
            talent.country
            and event.location
            and talent.country.lower() in event.location.lower()
        ):

            score += 20

        # ==========================================
        # TALENT VERIFICATION
        # ==========================================

        if talent.verified:

            score += 10

        # ==========================================
        # PROFILE COMPLETENESS
        # ==========================================

        if talent.biography:

            score += 10

        if talent.skills.exists():

            score += 20

        return score


# ==========================================
# CERTIFICATE GENERATOR
# ==========================================

class CertificateGenerator:

    @staticmethod
    def generate(event, talent):

        # ==========================================
        # VERIFY ATTENDANCE
        # ==========================================

        registration = EventRegistration.objects.filter(
            event=event,
            talent=talent,
            status="ATTENDED"
        ).first()

        if not registration:
            return None

        # ==========================================
        # CREATE OR GET CERTIFICATE
        # ==========================================

        certificate, created = EventCertificate.objects.get_or_create(

            event=event,

            talent=talent,

            defaults={

                "certificate_title":
                    "Certificate of Participation",

                "issued_by":
                    event.organizer,

                "certificate_code":
                    f"AW-{uuid.uuid4().hex[:8].upper()}",

                "description":
                    f"This certificate is awarded to "
                    f"{talent.user.get_full_name() or talent.user.username} "
                    f"for participating in {event.title}.",

                "verified":
                    True,

            }

        )

        return certificate