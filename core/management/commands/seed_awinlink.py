from django.core.management.base import BaseCommand

from django.contrib.auth import get_user_model


from organizations.models import Organization

from talents.models import TalentProfile

from skills.models import Skill, SkillCategory

from domains.models import TalentDomain

from opportunities.models import Opportunity, OpportunityRequirement


User = get_user_model()



class Command(BaseCommand):

    help = "Populate Awinlink with demo data"



    def handle(self, *args, **kwargs):


        self.stdout.write(
            "Creating Awinlink demo data..."
        )



        # =========================
        # ORGANIZATION
        # =========================


        org_user, created = User.objects.get_or_create(

            username="awinsports",

            defaults={

                "email":"info@awinsports.com",

                "role":"ORGANIZATION"

            }

        )


        org_user.set_password(
            "AwinSports@2026"
        )

        org_user.save()



        organization, _ = Organization.objects.get_or_create(

            user=org_user,

            defaults={

                "name":"Awin Sports Academy",

                "country":"Ghana",

                "city":"Accra",

                "website":"https://awinsports.com"

            }

        )





        # =========================
        # SKILL CATEGORY
        # =========================


        sports_category, _ = SkillCategory.objects.get_or_create(

            name="Sports"

        )



        # =========================
        # SKILLS
        # =========================


        skill_names = [

            "Football",

            "Basketball",

            "Athletics",

            "Leadership",

            "Fitness",

            "Teamwork",

            "Coaching"

        ]



        skills = {}



        for name in skill_names:


            skill, _ = Skill.objects.get_or_create(

                name=name,

                category=sports_category

            )


            skills[name] = skill






        # =========================
        # DOMAINS
        # =========================


        domain_names = [

            "Sports",

            "Football",

            "Basketball",

            "Athletics"

        ]



        domains = {}



        for name in domain_names:


            domain, _ = TalentDomain.objects.get_or_create(

                name=name

            )


            domains[name] = domain






        # =========================
        # TALENTS
        # =========================


        talents = [


            {

                "username":"kwame",

                "headline":
                "Professional Football Player",

                "skills":[

                    "Football",

                    "Leadership",

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

                "username":"kofi",

                "headline":
                "Basketball Player",

                "skills":[

                    "Basketball",

                    "Fitness"

                ],

                "domains":[

                    "Sports",

                    "Basketball"

                ],

                "verified":False

            },



            {

                "username":"ama",

                "headline":
                "Athletics Runner",

                "skills":[

                    "Athletics"

                ],

                "domains":[

                    "Sports",

                    "Athletics"

                ],

                "verified":False

            }


        ]





        for data in talents:



            user, _ = User.objects.get_or_create(

                username=data["username"],

                defaults={

                    "email":
                    f'{data["username"]}@gmail.com',

                    "role":"ATHLETE"

                }

            )



            user.set_password(
                "Talent@2026"
            )

            user.save()





            profile, _ = TalentProfile.objects.get_or_create(

                user=user,

                defaults={

                    "headline":
                    data["headline"],

                    "country":
                    "Ghana",

                    "city":
                    "Accra",

                    "verified":
                    data["verified"]

                }

            )



            for skill in data["skills"]:


                profile.skills.add(

                    skills[skill]

                )



            for domain in data["domains"]:


                profile.domains.add(

                    domains[domain]

                )






        # =========================
        # OPPORTUNITIES
        # =========================


        opportunities = [


            {
                "title":
                "Football Talent Recruitment 2026",

                "description":
                "Searching for talented football players.",

                "domain":
                "Football",

                "skills":[

                    "Football",

                    "Leadership",

                    "Fitness"

                ]

            },



            {
                "title":
                "Basketball Development Program",

                "description":
                "Looking for talented basketball players.",

                "domain":
                "Basketball",

                "skills":[

                    "Basketball",

                    "Fitness",

                    "Teamwork"

                ]

            },



            {
                "title":
                "Athletics Scholarship 2026",

                "description":
                "Searching for athletics talents.",

                "domain":
                "Athletics",

                "skills":[

                    "Athletics",

                    "Fitness"

                ]

            }


        ]





        for data in opportunities:



            opportunity, _ = Opportunity.objects.get_or_create(

                organization=organization,

                title=data["title"],

                defaults={

                    "description":
                    data["description"],

                    "domain":
                    domains[data["domain"]],

                    "active":
                    True

                }

            )



            for skill_name in data["skills"]:



                skill = skills[skill_name]



                # Direct skill relationship

                opportunity.skills.add(

                    skill

                )



                # Recommendation engine requirements

                OpportunityRequirement.objects.get_or_create(

                    opportunity=opportunity,

                    skill=skill,

                    defaults={

                        "importance":5

                    }

                )





        self.stdout.write(

            self.style.SUCCESS(

                "Awinlink demo data created successfully!"

            )

        )




        self.stdout.write(

            self.style.SUCCESS(

                "Awinlink demo data created successfully!"

            )

        )
        
        
        
        