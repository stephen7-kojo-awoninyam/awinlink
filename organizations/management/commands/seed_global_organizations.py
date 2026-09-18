from django.core.management.base import BaseCommand

from organizations.models import (
    Organization,
    OrganizationCategory,
    OrganizationDomain
)



class Command(BaseCommand):

    help = "Seed global organizations for Awinlink"



    def handle(self, *args, **kwargs):


        self.stdout.write(
            "Creating global organizations..."
        )


        # =====================================
        # HELPER FUNCTION
        # =====================================

        def create_org(
            name,
            country,
            category_name,
            domain_name,
            website="",
            description=""
        ):


            category = OrganizationCategory.objects.get(
                name=category_name
            )


            domain = OrganizationDomain.objects.get(
                name=domain_name
            )


            organization, created = Organization.objects.get_or_create(

                name=name,

                country=country,

                defaults={

                    "category": category,

                    "domain": domain,

                    "website": website,

                    "description": description,

                    "verified": True

                }

            )


            if created:

                self.stdout.write(
                    f"Created: {name}"
                )





        # =====================================
        # SPORTS ORGANIZATIONS
        # =====================================


        sports = [

            (
                "Manchester United",
                "England",
                "Football"
            ),

            (
                "Real Madrid",
                "Spain",
                "Football"
            ),

            (
                "FC Barcelona",
                "Spain",
                "Football"
            ),

            (
                "Bayern Munich",
                "Germany",
                "Football"
            ),

            (
                "Paris Saint-Germain",
                "France",
                "Football"
            ),

            (
                "Asante Kotoko",
                "Ghana",
                "Football"
            ),

            (
                "Hearts of Oak",
                "Ghana",
                "Football"
            ),


            (
                "NBA",
                "USA",
                "Basketball"
            ),

            (
                "Los Angeles Lakers",
                "USA",
                "Basketball"
            ),


            (
                "World Athletics",
                "Monaco",
                "Athletics"
            ),


            (
                "Wimbledon",
                "England",
                "Tennis"
            ),


        ]



        for name, country, domain in sports:


            create_org(

                name,

                country,

                "Sports",

                domain

            )





        # =====================================
        # MUSIC ORGANIZATIONS
        # =====================================


        music = [


            (
                "Universal Music Group",
                "USA",
                "Record Label"
            ),


            (
                "Sony Music Entertainment",
                "USA",
                "Record Label"
            ),


            (
                "Warner Music Group",
                "USA",
                "Record Label"
            ),


            (
                "Abbey Road Studios",
                "England",
                "Music Studio"
            ),


        ]



        for name, country, domain in music:


            create_org(

                name,

                country,

                "Music",

                domain

            )





        # =====================================
        # TECHNOLOGY ORGANIZATIONS
        # =====================================


        technology = [


            (
                "Google",
                "USA",
                "Artificial Intelligence"
            ),


            (
                "Microsoft",
                "USA",
                "Software Development"
            ),


            (
                "OpenAI",
                "USA",
                "Artificial Intelligence"
            ),


            (
                "Huawei",
                "China",
                "Telecommunications"
            ),


            (
                "Cisco",
                "USA",
                "Telecommunications"
            ),


        ]



        for name, country, domain in technology:


            create_org(

                name,

                country,

                "Technology",

                domain

            )






        # =====================================
        # HEALTHCARE ORGANIZATIONS
        # =====================================


        healthcare = [


            (
                "World Health Organization",
                "Switzerland",
                "Medical Research"
            ),


            (
                "Mayo Clinic",
                "USA",
                "Hospital"
            ),


            (
                "Pfizer",
                "USA",
                "Pharmaceutical"
            )


        ]



        for name, country, domain in healthcare:


            create_org(

                name,

                country,

                "Healthcare",

                domain

            )






        # =====================================
        # EDUCATION ORGANIZATIONS
        # =====================================


        education = [


            (
                "Harvard University",
                "USA",
                "University"
            ),


            (
                "Massachusetts Institute of Technology",
                "USA",
                "University"
            ),


            (
                "University of Oxford",
                "England",
                "University"
            )

        ]



        for name, country, domain in education:


            create_org(

                name,

                country,

                "Education",

                domain

            )





        self.stdout.write(

            self.style.SUCCESS(

                "Global organizations created successfully!"

            )

        )