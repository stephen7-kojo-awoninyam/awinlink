import json
import os

from django.core.management.base import BaseCommand

from organizations.models import (
    Organization,
    OrganizationCategory,
    OrganizationDomain
)

from organizations.models import SportsOrganizationProfile

from sports.models import Sport



class Command(BaseCommand):

    help = "Seed football organizations"



    def handle(self, *args, **kwargs):


        self.stdout.write(
            "Creating football organizations..."
        )


        # Category

        sports_category, _ = OrganizationCategory.objects.get_or_create(
            name="Sports"
        )


        # Domain

        football_domain, _ = OrganizationDomain.objects.get_or_create(
            category=sports_category,
            name="Football"
        )


        # Sport

        football, _ = Sport.objects.get_or_create(
            name="Football"
        )



        file_path = os.path.join(

            "data",

            "organizations",

            "football",

            "ghana.json"

        )



        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            organizations = json.load(file)



        for data in organizations:


            organization, created = Organization.objects.get_or_create(

                name=data["name"],

                country=data["country"],

                defaults={

                    "city": data["city"],

                    "website": data["website"],

                    "description": data["description"],

                    "founded_year": data["founded_year"],

                    "category": sports_category,

                    "domain": football_domain,

                    "official": True,

                    "verified": True

                }

            )


            SportsOrganizationProfile.objects.get_or_create(

                organization=organization,

                sport=football,

                defaults={

                    "league": data["league"],

                    "level": data["level"],

                    "founded": data["founded_year"]

                }

            )


            if created:

                self.stdout.write(

                    self.style.SUCCESS(

                        f"Created {organization.name}"

                    )

                )



        self.stdout.write(

            self.style.SUCCESS(

                "Football organizations loaded successfully"

            )

        )