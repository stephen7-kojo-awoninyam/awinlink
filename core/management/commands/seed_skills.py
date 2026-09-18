from django.core.management.base import BaseCommand

from organizations.models import OrganizationDomain
from skills.models import Skill, SkillCategory



class Command(BaseCommand):

    help = "Populate Awinlink global skills"


    SKILLS = {


        "Football": [

            "Ball Control",
            "Dribbling",
            "Passing",
            "Long Passing",
            "Crossing",
            "Finishing",
            "Heading",
            "Tackling",
            "Marking",
            "Positioning",
            "Vision",
            "Speed",
            "Agility",
            "Strength",
            "Stamina",
            "Leadership",
            "Captaincy",
            "Free Kick",
            "Penalty Taking",
            "Goalkeeping",
            "Game Reading",
            "Teamwork",

        ],



        "Basketball": [

            "Ball Handling",
            "Shooting",
            "Three Point Shooting",
            "Passing",
            "Defense",
            "Rebounding",
            "Dunking",
            "Speed",
            "Agility",
            "Teamwork",
            "Leadership",

        ],



        "Athletics": [

            "Sprint",
            "Long Distance Running",
            "Jumping",
            "Throwing",
            "Endurance",
            "Speed",
            "Strength",
            "Fitness",
            "Discipline",

        ],



        "Software Development": [

            "Python",
            "Java",
            "JavaScript",
            "C++",
            "C#",
            "Django",
            "React",
            "Vue.js",
            "Node.js",
            "SQL",
            "Database Design",
            "API Development",
            "Git",
            "Docker",
            "Testing",

        ],



        "Artificial Intelligence": [

            "Machine Learning",
            "Deep Learning",
            "Neural Networks",
            "Computer Vision",
            "Natural Language Processing",
            "Python",
            "TensorFlow",
            "PyTorch",
            "Data Analysis",

        ],



        "Cybersecurity": [

            "Network Security",
            "Penetration Testing",
            "Ethical Hacking",
            "Digital Forensics",
            "Security Auditing",
            "Risk Assessment",

        ],



        "Music Production": [

            "Song Writing",
            "Music Arrangement",
            "Audio Mixing",
            "Mastering",
            "Sound Engineering",
            "Beat Production",
            "Recording",

        ],



        "Artist Management": [

            "Talent Management",
            "Marketing",
            "Brand Development",
            "Negotiation",
            "Communication",

        ],



        "Hospital": [

            "Patient Care",
            "Surgery",
            "Nursing",
            "Emergency Care",
            "Medical Diagnosis",

        ],



        "Photography": [

            "Photography",
            "Photo Editing",
            "Lighting",
            "Camera Operation",

        ],



        "Telecommunications": [

            "Network Engineering",
            "Fiber Optics",
            "DWDM",
            "GPON",
            "Microwave Transmission",
            "Routing",
            "MPLS",
            "IP Networking",

        ],


    }



    def handle(self, *args, **kwargs):


        category, _ = SkillCategory.objects.get_or_create(

            name="General Skills"

        )


        total = 0



        for domain_name, skill_list in self.SKILLS.items():


            try:

                domain = OrganizationDomain.objects.get(

                    name=domain_name

                )


            except OrganizationDomain.DoesNotExist:


                self.stdout.write(

                    self.style.WARNING(

                        f"Domain missing: {domain_name}"

                    )

                )

                continue



            self.stdout.write(

                self.style.NOTICE(

                    f"\n{domain_name}"

                )

            )



            for skill_name in skill_list:



                skill, created = Skill.objects.get_or_create(

                    name=skill_name,

                    category=category

                )


                if created:

                    total += 1

                    self.stdout.write(

                        f"   ✓ {skill_name}"

                    )



        self.stdout.write("")

        self.stdout.write(

            self.style.SUCCESS(

                f"{total} skills created successfully."

            )

        )