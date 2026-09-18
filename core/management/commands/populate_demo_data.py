from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from talents.models import (
    TalentProfile,
    Achievement,
    Certification,
    Experience,
)

from sports.models import (
    Sport,
    SportCategory,
    PerformanceMetric,
    SportsTalentProfile,
)

from domains.models import TalentDomain

from skills.models import (
    SkillCategory,
    Skill,
)

from organizations.models import (
    OrganizationCategory,
    OrganizationDomain,
    Organization,
    SportsOrganizationProfile,
)

from opportunities.models import (
    Opportunity,
    OpportunityRequirement,
)

from analytics.models import TalentScore


User = get_user_model()


class Command(BaseCommand):

    help = "Populate Awinlink with realistic demo data for end-to-end testing."

    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING(
                "Starting Awinlink demo data population..."
            )
        )

        # =========================================================
        # USERS
        # =========================================================

        self.stdout.write("Creating demo users...")

        athlete, created = User.objects.get_or_create(
            username="stephen",
            defaults={
                "first_name": "Stephen",
                "last_name": "Awoninyam",
                "email": "stephen.demo@awinlink.test",
                "role": "ATHLETE",
                "country": "Ghana",
                "phone_number": "0200000000",
            }
        )

        if created:
            athlete.set_password("StephenDemo123!")
            athlete.save()

        else:
            athlete.first_name = "Stephen"
            athlete.last_name = "Awoninyam"
            athlete.role = "ATHLETE"
            athlete.country = "Ghana"
            athlete.save(
                update_fields=[
                    "first_name",
                    "last_name",
                    "role",
                    "country",
                ]
            )

        organization_users = [
            {
                "username": "accra_united_demo",
                "first_name": "Accra",
                "last_name": "United",
                "email": "accra.united@awinlink.test",
            },
            {
                "username": "golden_city_demo",
                "first_name": "Golden",
                "last_name": "City",
                "email": "golden.city@awinlink.test",
            },
            {
                "username": "coastal_stars_demo",
                "first_name": "Coastal",
                "last_name": "Stars",
                "email": "coastal.stars@awinlink.test",
            },
        ]

        organization_accounts = []

        for data in organization_users:

            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "role": "ORGANIZATION",
                    "country": "Ghana",
                }
            )

            if created:
                user.set_password("Demo12345!")
                user.save()

            organization_accounts.append(user)

        scout, created = User.objects.get_or_create(
            username="demo_scout",
            defaults={
                "first_name": "Kwame",
                "last_name": "Mensah",
                "email": "scout@awinlink.test",
                "role": "SCOUT",
                "country": "Ghana",
            }
        )

        if created:
            scout.set_password("Demo12345!")
            scout.save()

        coach, created = User.objects.get_or_create(
            username="demo_coach",
            defaults={
                "first_name": "Daniel",
                "last_name": "Boateng",
                "email": "coach@awinlink.test",
                "role": "COACH",
                "country": "Ghana",
            }
        )

        if created:
            coach.set_password("Demo12345!")
            coach.save()

        # =========================================================
        # SPORT
        # =========================================================

        self.stdout.write("Creating football data...")

        football, _ = Sport.objects.get_or_create(
            name="Football",
            defaults={
                "description": (
                    "Association football and related competitive "
                    "football activities."
                )
            }
        )

        football_categories = {}

        categories = [
            "Goalkeeper",
            "Defender",
            "Midfielder",
            "Forward",
        ]

        for name in categories:

            category, _ = SportCategory.objects.get_or_create(
                sport=football,
                name=name,
                defaults={
                    "description": f"Football {name} position category."
                }
            )

            football_categories[name] = category

        # =========================================================
        # PERFORMANCE METRICS
        # =========================================================

        metrics = [
            ("Speed", "km/h"),
            ("Passing Accuracy", "%"),
            ("Shot Accuracy", "%"),
            ("Dribbling Success", "%"),
            ("Tackles Won", "%"),
            ("Stamina", "score"),
        ]

        for name, unit in metrics:

            PerformanceMetric.objects.get_or_create(
                sport=football,
                name=name,
                defaults={
                    "unit": unit,
                    "description": f"Football performance metric: {name}.",
                }
            )

        # =========================================================
        # TALENT DOMAINS
        # =========================================================

        football_domain, _ = TalentDomain.objects.get_or_create(
            name="Football",
            defaults={
                "description": (
                    "Football playing, coaching, scouting and "
                    "professional football development."
                )
            }
        )

        sports_domain, _ = TalentDomain.objects.get_or_create(
            name="Sports",
            defaults={
                "description": (
                    "General sports and athletic talent development."
                )
            }
        )

        # =========================================================
        # SKILL CATEGORIES
        # =========================================================

        technical_category, _ = SkillCategory.objects.get_or_create(
            name="Football Technical Skills"
        )

        physical_category, _ = SkillCategory.objects.get_or_create(
            name="Football Physical Skills"
        )

        tactical_category, _ = SkillCategory.objects.get_or_create(
            name="Football Tactical Skills"
        )

        # =========================================================
        # SKILLS
        # =========================================================

        technical_skills = [
            "Ball Control",
            "Passing",
            "Dribbling",
            "Finishing",
            "Crossing",
            "First Touch",
        ]

        physical_skills = [
            "Speed",
            "Stamina",
            "Agility",
            "Strength",
        ]

        tactical_skills = [
            "Positioning",
            "Game Reading",
            "Decision Making",
            "Teamwork",
        ]

        skill_objects = {}

        for name in technical_skills:

            skill, _ = Skill.objects.get_or_create(
                category=technical_category,
                name=name
            )

            skill_objects[name] = skill

        for name in physical_skills:

            skill, _ = Skill.objects.get_or_create(
                category=physical_category,
                name=name
            )

            skill_objects[name] = skill

        for name in tactical_skills:

            skill, _ = Skill.objects.get_or_create(
                category=tactical_category,
                name=name
            )

            skill_objects[name] = skill

        # =========================================================
        # STEPHEN TALENT PROFILE
        # =========================================================

        self.stdout.write("Creating athlete profile...")

        talent, _ = TalentProfile.objects.get_or_create(
            user=athlete,
            defaults={
                "talent_category": "SPORTS",
                "availability_status": "AVAILABLE",
                "profile_visibility": "PUBLIC",
                "preferred_work_type": "ONSITE",
                "experience_level": "INTERMEDIATE",
                "headline": "Football Midfielder",
                "biography": (
                    "Talented Ghanaian football midfielder looking for "
                    "competitive opportunities, trials and professional "
                    "development."
                ),
                "country": "Ghana",
                "city": "Accra",
                "verified": True,
            }
        )

        talent.talent_category = "SPORTS"
        talent.availability_status = "AVAILABLE"
        talent.profile_visibility = "PUBLIC"
        talent.preferred_work_type = "ONSITE"
        talent.experience_level = "INTERMEDIATE"
        talent.headline = "Football Midfielder"
        talent.biography = (
            "Talented Ghanaian football midfielder looking for "
            "competitive opportunities, trials and professional "
            "development."
        )
        talent.country = "Ghana"
        talent.city = "Accra"
        talent.verified = True
        talent.save()

        talent.domains.add(
            football_domain,
            sports_domain,
        )

        talent.skills.add(
            skill_objects["Ball Control"],
            skill_objects["Passing"],
            skill_objects["Dribbling"],
            skill_objects["First Touch"],
            skill_objects["Speed"],
            skill_objects["Stamina"],
            skill_objects["Positioning"],
            skill_objects["Game Reading"],
            skill_objects["Decision Making"],
            skill_objects["Teamwork"],
        )

        # =========================================================
        # SPORTS TALENT PROFILE
        # =========================================================

        SportsTalentProfile.objects.update_or_create(
            talent=talent,
            defaults={
                "sport": football,
                "sport_category": football_categories["Midfielder"],
                "position": "Central Midfielder",
                "height": 1.78,
                "weight": 72.00,
                "bio": (
                    "Central midfielder with strong passing, ball control, "
                    "game reading and teamwork abilities."
                ),
            }
        )

        # =========================================================
        # ACHIEVEMENTS
        # =========================================================

        Achievement.objects.get_or_create(
            talent=talent,
            title="Best Midfielder - Regional Youth Tournament",
            defaults={
                "description": (
                    "Recognized as one of the top midfielders during "
                    "a regional youth football tournament."
                ),
                "date_received": date(2025, 8, 15),
            }
        )

        Achievement.objects.get_or_create(
            talent=talent,
            title="Tournament Finalist",
            defaults={
                "description": (
                    "Helped team reach the final of a competitive "
                    "football tournament."
                ),
                "date_received": date(2024, 12, 10),
            }
        )

        # =========================================================
        # CERTIFICATION
        # =========================================================

        Certification.objects.get_or_create(
            talent=talent,
            name="Football Performance & Development Certificate",
            defaults={
                "issuing_organization": "Awinlink Sports Academy",
                "issue_date": date(2025, 6, 20),
            }
        )

        # =========================================================
        # EXPERIENCE
        # =========================================================

        Experience.objects.get_or_create(
            talent=talent,
            company="Accra Community Football Academy",
            role="Central Midfielder",
            defaults={
                "description": (
                    "Participated in competitive football training, "
                    "matches and tactical development."
                ),
                "start_date": date(2023, 1, 10),
                "end_date": date(2025, 12, 20),
                "currently_working": False,
            }
        )

        # =========================================================
        # TALENT SCORE
        # =========================================================

        TalentScore.objects.update_or_create(
            talent=talent,
            defaults={
                "physical_score": 82,
                "performance_score": 84,
                "achievement_score": 78,
                "experience_score": 80,
                "verification_score": 100,
                "overall_score": 84,
            }
        )

        # =========================================================
        # ORGANIZATION CATEGORY
        # =========================================================

        sports_category, _ = OrganizationCategory.objects.get_or_create(
            name="Sports",
            defaults={
                "description": (
                    "Sports clubs, academies, federations and "
                    "other sporting organizations."
                )
            }
        )

        # =========================================================
        # ORGANIZATION DOMAINS
        # =========================================================

        football_org_domain, _ = OrganizationDomain.objects.get_or_create(
            category=sports_category,
            name="Football",
            defaults={
                "description": (
                    "Football clubs, academies, leagues and organizations."
                )
            }
        )

        # =========================================================
        # ORGANIZATIONS
        # =========================================================

        organization_data = [
            {
                "user": organization_accounts[0],
                "name": "Accra United Demo FC",
                "city": "Accra",
                "level": "REGIONAL",
                "size": "MEDIUM",
                "description": (
                    "A demo football club focused on identifying and "
                    "developing talented football players in Ghana."
                ),
                "league": "Greater Accra Regional League",
                "sport_level": "SEMI_PRO",
                "stadium": "Accra Community Stadium",
                "nickname": "The United",
            },
            {
                "user": organization_accounts[1],
                "name": "Golden City Demo FC",
                "city": "Kumasi",
                "level": "NATIONAL",
                "size": "MEDIUM",
                "description": (
                    "A demo professional football organization "
                    "searching for emerging football talent."
                ),
                "league": "Ghana Premier Development League",
                "sport_level": "PROFESSIONAL",
                "stadium": "Golden City Stadium",
                "nickname": "The Gold Stars",
            },
            {
                "user": organization_accounts[2],
                "name": "Coastal Stars Demo Academy",
                "city": "Cape Coast",
                "level": "REGIONAL",
                "size": "SMALL",
                "description": (
                    "A football academy developing young players "
                    "through structured training and competitive matches."
                ),
                "league": "Central Region Youth League",
                "sport_level": "ACADEMY",
                "stadium": "Coastal Training Ground",
                "nickname": "Coastal Stars",
            },
        ]

        organizations = []

        for data in organization_data:

            organization, _ = Organization.objects.update_or_create(
                user=data["user"],
                defaults={
                    "name": data["name"],
                    "category": sports_category,
                    "domain": football_org_domain,
                    "country": "Ghana",
                    "city": data["city"],
                    "headquarters": data["city"] + ", Ghana",
                    "website": "https://example.com",
                    "email": data["user"].email,
                    "phone": "0300000000",
                    "description": data["description"],
                    "founded_year": 2015,
                    "organization_size": data["size"],
                    "level": data["level"],
                    "official": True,
                    "claimed": True,
                    "verified": True,
                    "status": "ACTIVE",
                }
            )

            SportsOrganizationProfile.objects.update_or_create(
                organization=organization,
                defaults={
                    "sport": football,
                    "league": data["league"],
                    "level": data["sport_level"],
                    "founded": 2015,
                    "stadium": data["stadium"],
                    "nickname": data["nickname"],
                    "colors": "Blue and White",
                    "website": "https://example.com",
                }
            )

            organizations.append(organization)

        # =========================================================
        # OPPORTUNITIES
        # =========================================================

        self.stdout.write("Creating football opportunities...")

        opportunities = [
            {
                "organization": organizations[0],
                "title": "Central Midfielder Football Trial",
                "description": (
                    "Accra United Demo FC is looking for talented "
                    "central midfielders for an upcoming player trial. "
                    "Candidates should demonstrate strong passing, "
                    "ball control, tactical awareness and teamwork."
                ),
                "type": "TRIAL",
                "experience": "INTERMEDIATE",
                "work_type": "ONSITE",
                "location": "Accra, Ghana",
                "skills": [
                    "Ball Control",
                    "Passing",
                    "Decision Making",
                    "Teamwork",
                    "Stamina",
                ],
                "requirements": [
                    ("Passing", 5),
                    ("Ball Control", 5),
                    ("Decision Making", 4),
                    ("Teamwork", 4),
                    ("Stamina", 3),
                ],
            },
            {
                "organization": organizations[1],
                "title": "Professional Midfielder Recruitment",
                "description": (
                    "Golden City Demo FC is recruiting an experienced "
                    "midfielder with strong technical and tactical "
                    "abilities for the upcoming competitive season."
                ),
                "type": "JOB",
                "experience": "EXPERT",
                "work_type": "ONSITE",
                "location": "Kumasi, Ghana",
                "skills": [
                    "Passing",
                    "Ball Control",
                    "Game Reading",
                    "Positioning",
                    "Decision Making",
                ],
                "requirements": [
                    ("Passing", 5),
                    ("Game Reading", 5),
                    ("Positioning", 4),
                    ("Decision Making", 5),
                    ("Ball Control", 4),
                ],
            },
            {
                "organization": organizations[2],
                "title": "Football Academy Player Trial",
                "description": (
                    "Coastal Stars Demo Academy is accepting applications "
                    "from promising young footballers interested in "
                    "academy development and competitive football."
                ),
                "type": "TRIAL",
                "experience": "BEGINNER",
                "work_type": "ONSITE",
                "location": "Cape Coast, Ghana",
                "skills": [
                    "Dribbling",
                    "First Touch",
                    "Speed",
                    "Teamwork",
                    "Ball Control",
                ],
                "requirements": [
                    ("Dribbling", 4),
                    ("First Touch", 4),
                    ("Speed", 3),
                    ("Teamwork", 4),
                    ("Ball Control", 4),
                ],
            },
        ]

        for data in opportunities:

            deadline = timezone.localdate() + timedelta(days=30)

            opportunity, _ = Opportunity.objects.update_or_create(
                organization=data["organization"],
                title=data["title"],
                defaults={
                    "description": data["description"],
                    "opportunity_type": data["type"],
                    "domain": football_domain,
                    "experience_level": data["experience"],
                    "work_type": data["work_type"],
                    "location": data["location"],
                    "deadline": deadline,
                    "active": True,
                }
            )

            opportunity.skills.set(
                [
                    skill_objects[name]
                    for name in data["skills"]
                ]
            )

            for skill_name, importance in data["requirements"]:

                OpportunityRequirement.objects.update_or_create(
                    opportunity=opportunity,
                    skill=skill_objects[skill_name],
                    defaults={
                        "importance": importance
                    }
                )

        # =========================================================
        # FINISHED
        # =========================================================

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "=============================================="
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Awinlink demo data populated successfully!"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "=============================================="
            )
        )

        self.stdout.write("")
        self.stdout.write("Demo accounts:")
        self.stdout.write("")
        self.stdout.write(
            "ATHLETE:"
        )
        self.stdout.write(
            "  Username: stephen"
        )
        self.stdout.write(
            "  Password: StephenDemo123!"
        )
        self.stdout.write("")
        self.stdout.write(
            "ORGANIZATION:"
        )
        self.stdout.write(
            "  accra_united_demo / Demo12345!"
        )
        self.stdout.write(
            "  golden_city_demo / Demo12345!"
        )
        self.stdout.write(
            "  coastal_stars_demo / Demo12345!"
        )
        self.stdout.write("")
        self.stdout.write(
            "SCOUT:"
        )
        self.stdout.write(
            "  demo_scout / Demo12345!"
        )
        self.stdout.write("")
        self.stdout.write(
            "COACH:"
        )
        self.stdout.write(
            "  demo_coach / Demo12345!"
        )
        self.stdout.write("")
        self.stdout.write(
            "Football organizations created: "
            f"{len(organizations)}"
        )
        self.stdout.write(
            "Football opportunities created: "
            f"{Opportunity.objects.filter(domain=football_domain).count()}"
        )
        self.stdout.write(
            "Athlete: "
            f"{talent.user.username}"
        )