from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from talents.models import TalentProfile
from skills.models import Skill
from domains.models import TalentDomain


User = get_user_model()



class Command(BaseCommand):

    help = "Create global demo talents"



    TALENTS = [


        # =========================
        # FOOTBALL
        # =========================


        {
            "username":"kwame_player",

            "headline":
            "Attacking Midfielder",

            "country":"Ghana",

            "skills":[

                "Football",
                "Leadership",
                "Teamwork",
                "Fitness"

            ],

            "domains":[

                "Sports",
                "Football"

            ],

            "verified":True

        },


        {
            "username":"mohamed_salah_demo",

            "headline":
            "Professional Winger",

            "country":"Egypt",

            "skills":[

                "Football",
                "Fitness",
                "Teamwork"

            ],

            "domains":[

                "Sports",
                "Football"

            ],

            "verified":True

        },


        {
            "username":"kevin_midfielder",

            "headline":
            "Creative Midfielder",

            "country":"Belgium",

            "skills":[

                "Football",
                "Leadership"

            ],

            "domains":[

                "Sports",
                "Football"

            ],

            "verified":False

        },


        # =========================
        # BASKETBALL
        # =========================


        {
            "username":"john_basketball",

            "headline":
            "Basketball Point Guard",

            "country":"USA",

            "skills":[

                "Basketball",
                "Leadership",
                "Fitness"

            ],

            "domains":[

                "Sports",
                "Basketball"

            ],

            "verified":True

        },


        {
            "username":"kwesi_hoops",

            "headline":
            "Basketball Forward",

            "country":"Ghana",

            "skills":[

                "Basketball",
                "Teamwork"

            ],

            "domains":[

                "Sports",
                "Basketball"

            ],

            "verified":False

        },



        # =========================
        # TECHNOLOGY TALENTS
        # =========================


        {
            "username":"stephen_ai",

            "headline":
            "Machine Learning Engineer",

            "country":"Ghana",

            "skills":[

                "Python",
                "Artificial Intelligence"

            ],

            "domains":[

                "Technology",
                "Artificial Intelligence"

            ],

            "verified":True

        },


        {
            "username":"ama_security",

            "headline":
            "Cybersecurity Analyst",

            "country":"Ghana",

            "skills":[

                "Cybersecurity"

            ],

            "domains":[

                "Technology",
                "Cybersecurity"

            ],

            "verified":False

        },


        # =========================
        # MUSIC
        # =========================


        {
            "username":"yaw_music",

            "headline":
            "Afrobeats Artist",

            "country":"Ghana",

            "skills":[

                "Music Production"

            ],

            "domains":[

                "Music"

            ],

            "verified":False

        },


    ]



    def handle(self,*args,**kwargs):


        for data in self.TALENTS:


            user, created = User.objects.get_or_create(

                username=data["username"],

                defaults={

                    "email":

                    data["username"]+"@awinlink.com",

                    "role":"ATHLETE"

                }

            )


            user.set_password(
                "Talent@2026"
            )

            user.save()



            profile, created = TalentProfile.objects.get_or_create(

                user=user,

                defaults={

                    "headline":
                    data["headline"],

                    "country":
                    data["country"],

                    "city":
                    "",

                    "verified":
                    data["verified"]

                }

            )



            for skill_name in data["skills"]:


                skill = Skill.objects.filter(

                    name=skill_name

                ).first()


                if skill:

                    profile.skills.add(skill)



            for domain_name in data["domains"]:


                domain = TalentDomain.objects.filter(

                    name=domain_name

                ).first()


                if domain:

                    profile.domains.add(domain)



            self.stdout.write(

                self.style.SUCCESS(

                    f"Created talent {data['username']}"

                )

            )



        self.stdout.write(

            self.style.SUCCESS(

                "Global talents created successfully"

            )

        )