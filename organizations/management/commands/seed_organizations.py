from django.core.management.base import BaseCommand

from organizations.models import (
    OrganizationCategory,
    OrganizationDomain
)



class Command(BaseCommand):

    help = "Populate global organization categories and domains"


    def handle(self, *args, **kwargs):


        self.stdout.write(
            "Creating organization categories..."
        )


        organization_data = {


            "Sports": [

                "Football",
                "Basketball",
                "Athletics",
                "Tennis",
                "Boxing",
                "Swimming",
                "Volleyball",
                "Cricket",
                "Rugby"

            ],



            "Music": [

                "Record Label",
                "Music Studio",
                "Artist Management",
                "Music Production",
                "Concert Organization"

            ],



            "Technology": [

                "Software Development",
                "Artificial Intelligence",
                "Cybersecurity",
                "Telecommunications",
                "Cloud Computing"

            ],



            "Healthcare": [

                "Hospital",
                "Clinic",
                "Pharmaceutical",
                "Medical Research"

            ],



            "Education": [

                "University",
                "School",
                "Training Institute",
                "Research Center"

            ],



            "Media": [

                "Television",
                "Film Production",
                "News Organization",
                "Content Creation"

            ],



            "Fashion": [

                "Fashion House",
                "Model Agency",
                "Design Studio"

            ],



            "Finance": [

                "Bank",
                "Investment Company",
                "Insurance",
                "FinTech"

            ],



            "Transportation": [

                "Airline",
                "Logistics",
                "Ride Sharing",
                "Shipping"

            ]

        }




        for category_name, domains in organization_data.items():


            category, created = OrganizationCategory.objects.get_or_create(

                name=category_name,

                defaults={

                    "description":
                    f"{category_name} organizations"

                }

            )


            if created:

                self.stdout.write(
                    f"Created category: {category_name}"
                )



            for domain_name in domains:


                domain, created = OrganizationDomain.objects.get_or_create(

                    name=domain_name,

                    category=category,

                    defaults={

                        "description":
                        f"{domain_name} organizations"

                    }

                )


                if created:

                    self.stdout.write(
                        f"  Created domain: {domain_name}"
                    )



        self.stdout.write(

            self.style.SUCCESS(

                "Organization categories and domains created successfully!"

            )

        )