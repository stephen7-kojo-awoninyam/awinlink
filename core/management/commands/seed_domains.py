from django.core.management.base import BaseCommand

from organizations.models import (
    OrganizationCategory,
    OrganizationDomain,
)


class Command(BaseCommand):

    help = "Seed organization domains"


    DOMAINS = {

        "Sports": [

            "Football",
            "Basketball",
            "Volleyball",
            "Athletics",
            "Cricket",
            "Rugby",
            "Swimming",
            "Boxing",
            "MMA",
            "Cycling",
            "Tennis",
            "Golf",
            "Baseball",
            "Hockey",
            "Esports",
            "Motorsports",
            "Chess",
            "Badminton",
            "Handball",
            "Table Tennis",

        ],

        "Music": [

            "Record Label",
            "Music Production",
            "Music Studio",
            "Artist Management",
            "Concert Organization",
            "Music Distribution",
            "Choir",
            "Orchestra",
            "DJ Services",
            "Podcast",

        ],

        "Technology": [

            "Software Development",
            "Artificial Intelligence",
            "Machine Learning",
            "Cybersecurity",
            "Cloud Computing",
            "Networking",
            "Telecommunications",
            "Data Science",
            "Blockchain",
            "Game Development",
            "UI UX Design",
            "DevOps",
            "Embedded Systems",
            "Robotics",
            "IoT",

        ],

        "Healthcare": [

            "Hospital",
            "Clinic",
            "Dental",
            "Pharmacy",
            "Medical Laboratory",
            "Radiology",
            "Physiotherapy",
            "Mental Health",
            "Medical Research",
            "Veterinary",

        ],

        "Education": [

            "University",
            "College",
            "High School",
            "Primary School",
            "Training Institute",
            "Research Center",
            "Online Learning",
            "Vocational School",

        ],

        "Media": [

            "Television",
            "Radio",
            "Newspaper",
            "Magazine",
            "Digital Media",
            "Film Production",
            "Photography",
            "Animation",

        ],

        "Finance": [

            "Commercial Bank",
            "Investment Bank",
            "Insurance",
            "Microfinance",
            "FinTech",
            "Investment Company",
            "Accounting",
            "Auditing",

        ],

        "Fashion": [

            "Fashion House",
            "Model Agency",
            "Textile",
            "Fashion Design",
            "Jewelry",
            "Beauty",

        ],

        "Agriculture": [

            "Crop Farming",
            "Livestock",
            "Poultry",
            "AgriTech",
            "Food Processing",
            "Forestry",

        ],

        "Engineering": [

            "Civil",
            "Mechanical",
            "Electrical",
            "Mining",
            "Petroleum",
            "Chemical",
            "Industrial",
            "Aerospace",

        ],

        "Entertainment": [

            "Film",
            "Television",
            "Comedy",
            "Dance",
            "Event Management",
            "Talent Management",

        ],

        "Transportation": [

            "Airline",
            "Shipping",
            "Logistics",
            "Railway",
            "Ride Sharing",
            "Public Transport",

        ],

        "Government": [

            "Ministry",
            "Municipality",
            "Defense",
            "Immigration",
            "Police",
            "Fire Service",

        ],

        "NGO": [

            "Health",
            "Education",
            "Environment",
            "Youth Development",
            "Women Empowerment",
            "Human Rights",

        ],

        "Hospitality": [

            "Hotel",
            "Restaurant",
            "Resort",
            "Travel Agency",
            "Tourism",

        ],

        "Real Estate": [

            "Property Development",
            "Property Management",
            "Real Estate Agency",

        ],

        "Law": [

            "Law Firm",
            "Corporate Law",
            "Litigation",
            "Legal Aid",

        ],

        "Research": [

            "Scientific Research",
            "Innovation Hub",
            "Think Tank",

        ],

        "Arts": [

            "Painting",
            "Sculpture",
            "Gallery",
            "Museum",
            "Creative Studio",

        ],

    }


    def handle(self, *args, **kwargs):

        total = 0

        for category_name, domains in self.DOMAINS.items():

            category = OrganizationCategory.objects.get(
                name=category_name
            )

            self.stdout.write(
                self.style.NOTICE(f"\n{category_name}")
            )

            for domain_name in domains:

                _, created = OrganizationDomain.objects.get_or_create(
                    category=category,
                    name=domain_name,
                )

                if created:
                    total += 1
                    self.stdout.write(
                        f"   ✓ {domain_name}"
                    )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {total} domains."
            )
        )