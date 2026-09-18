from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from organizations.models import (
    Organization,
    OrganizationCategory,
    OrganizationDomain
)


User = get_user_model()



class Command(BaseCommand):

    help = "Seed global organizations"



    ORGANIZATIONS = [

        # =========================
        # SPORTS
        # =========================


        {
            "name": "Real Madrid",
            "category": "Sports",
            "domain": "Football",
            "country": "Spain",
            "city": "Madrid",
            "website": "https://www.realmadrid.com"
        },


        {
            "name": "FC Barcelona",
            "category": "Sports",
            "domain": "Football",
            "country": "Spain",
            "city": "Barcelona",
            "website": "https://www.fcbarcelona.com"
        },


        {
            "name": "Manchester United",
            "category": "Sports",
            "domain": "Football",
            "country": "England",
            "city": "Manchester",
            "website": "https://www.manutd.com"
        },


        {
            "name": "Bayern Munich",
            "category": "Sports",
            "domain": "Football",
            "country": "Germany",
            "city": "Munich",
            "website": "https://fcbayern.com"
        },


        {
            "name": "Asante Kotoko",
            "category": "Sports",
            "domain": "Football",
            "country": "Ghana",
            "city": "Kumasi",
            "website": ""
        },


        {
            "name": "Hearts of Oak",
            "category": "Sports",
            "domain": "Football",
            "country": "Ghana",
            "city": "Accra",
            "website": ""
        },


        # =========================
        # TECHNOLOGY
        # =========================


        {
            "name": "Google",
            "category": "Technology",
            "domain": "Software Development",
            "country": "USA",
            "city": "California",
            "website": "https://google.com"
        },


        {
            "name": "Microsoft",
            "category": "Technology",
            "domain": "Software Development",
            "country": "USA",
            "city": "Washington",
            "website": "https://microsoft.com"
        },


        {
            "name": "OpenAI",
            "category": "Technology",
            "domain": "Artificial Intelligence",
            "country": "USA",
            "city": "San Francisco",
            "website": "https://openai.com"
        },


        {
            "name": "MTN Ghana",
            "category": "Technology",
            "domain": "Telecommunications",
            "country": "Ghana",
            "city": "Accra",
            "website": "https://mtn.com.gh"
        },


        # =========================
        # EDUCATION
        # =========================


        {
            "name": "Massachusetts Institute of Technology",
            "category": "Education",
            "domain": "University",
            "country": "USA",
            "city": "Massachusetts",
            "website": "https://mit.edu"
        },


        {
            "name": "Kwame Nkrumah University of Science and Technology",
            "category": "Education",
            "domain": "University",
            "country": "Ghana",
            "city": "Kumasi",
            "website": "https://knust.edu.gh"
        },


        {
            "name": "University of Ghana",
            "category": "Education",
            "domain": "University",
            "country": "Ghana",
            "city": "Accra",
            "website": "https://ug.edu.gh"
        },



        # =========================
        # HEALTHCARE
        # =========================


        {
            "name": "Korle Bu Teaching Hospital",
            "category": "Healthcare",
            "domain": "Hospital",
            "country": "Ghana",
            "city": "Accra",
            "website": ""
        },


        {
            "name": "Komfo Anokye Teaching Hospital",
            "category": "Healthcare",
            "domain": "Hospital",
            "country": "Ghana",
            "city": "Kumasi",
            "website": ""
        },


    ]



    def handle(self, *args, **kwargs):


        created_count = 0


        for data in self.ORGANIZATIONS:


            category = OrganizationCategory.objects.get(

                name=data["category"]

            )


            domain = OrganizationDomain.objects.get(

                name=data["domain"]

            )



            username = (

                data["name"]

                .lower()

                .replace(" ","_")

            )



            user, _ = User.objects.get_or_create(

                username=username,

                defaults={

                    "email": username+"@awinlink.com",

                    "role":"ORGANIZATION"

                }

            )



            user.set_password(

                "Organization@2026"

            )

            user.save()



            organization, created = Organization.objects.get_or_create(

                name=data["name"],

                defaults={

                    "user":user,

                    "category":category,

                    "domain":domain,

                    "country":data["country"],

                    "city":data["city"],

                    "website":data["website"],

                    "verified":True

                }

            )


            if created:

                created_count += 1

                self.stdout.write(

                    self.style.SUCCESS(

                        f"Created {data['name']}"

                    )

                )



        self.stdout.write(

            self.style.SUCCESS(

                f"{created_count} organizations created"

            )

        )