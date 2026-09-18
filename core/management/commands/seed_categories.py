from django.core.management.base import BaseCommand

from organizations.models import OrganizationCategory


class Command(BaseCommand):

    help = "Seed organization categories"


    def handle(self, *args, **kwargs):

        categories = [

            {
                "name": "Sports",
                "description": "Sports clubs, academies, federations and associations.",
            },

            {
                "name": "Music",
                "description": "Music labels, studios, artists and producers.",
            },

            {
                "name": "Technology",
                "description": "Technology companies and startups.",
            },

            {
                "name": "Healthcare",
                "description": "Hospitals, clinics and healthcare organizations.",
            },

            {
                "name": "Education",
                "description": "Schools, universities and educational institutions.",
            },

            {
                "name": "Media",
                "description": "Television, radio, news and digital media.",
            },

            {
                "name": "Fashion",
                "description": "Fashion houses, designers and model agencies.",
            },

            {
                "name": "Finance",
                "description": "Banks, insurance and investment firms.",
            },

            {
                "name": "Agriculture",
                "description": "Agriculture and agribusiness organizations.",
            },

            {
                "name": "Engineering",
                "description": "Engineering and construction firms.",
            },

            {
                "name": "Government",
                "description": "Government ministries and public agencies.",
            },

            {
                "name": "NGO",
                "description": "Non-governmental organizations.",
            },

            {
                "name": "Entertainment",
                "description": "Entertainment companies and event organizers.",
            },

            {
                "name": "Hospitality",
                "description": "Hotels, restaurants and tourism organizations.",
            },

            {
                "name": "Transportation",
                "description": "Airlines, logistics and transport companies.",
            },

            {
                "name": "Manufacturing",
                "description": "Manufacturing industries.",
            },

            {
                "name": "Real Estate",
                "description": "Real estate developers and agencies.",
            },

            {
                "name": "Law",
                "description": "Law firms and legal organizations.",
            },

            {
                "name": "Research",
                "description": "Research institutes and innovation centers.",
            },

            {
                "name": "Arts",
                "description": "Art galleries, museums and creative organizations.",
            },

        ]

        created = 0

        for category in categories:

            _, was_created = OrganizationCategory.objects.get_or_create(
                name=category["name"],
                defaults={
                    "description": category["description"]
                }
            )

            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {category['name']}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} new categories added."
            )
        )