"""Deterministic fictional discovery benchmark, restricted to an isolated DB."""
import json
import os
from pathlib import Path
from time import perf_counter

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from domains.models import TalentDomain
from skills.models import Skill, SkillCategory
from talents.models import TalentProfile
from recommendations.services import RecommendationEngine
from recommendations.unified import UnifiedRecommendationService
from recommendations.local_benchmark import SURFACES, benchmark_surface, seed_extended_fixtures


PREFIX = "fictional_rec_"
GROUPS = (
    ("SPORTS", "Football", "Passing"),
    ("SPORTS", "Swimming", "Freestyle"),
    ("SPORTS", "Athletics", "Sprinting"),
    ("SCIENCE_TECHNOLOGY", "Software", "Python"),
    ("SCIENCE_TECHNOLOGY", "Robotics", "Electronics"),
    ("SCIENCE_TECHNOLOGY", "Astronomy", "Astrophysics"),
    ("ARTS", "Music", "Piano"),
    ("ARTS", "Painting", "Watercolor"),
    ("OTHERS", "Public Speaking", "Storytelling"),
)


def require_local_database():
    db = connection.settings_dict
    name = str(db["NAME"])
    expected = Path(settings.BASE_DIR) / "recommendation-seed.sqlite3"
    memory = name == ":memory:" or name.startswith("file:memorydb_")
    hosted = any(os.environ.get(key) for key in (
        "RENDER", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME",
        "RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN",
    ))
    if (not settings.DEBUG or hosted or db["ENGINE"] != "django.db.backends.sqlite3"
            or (not memory and Path(name).resolve() != expected.resolve())):
        raise CommandError(
            "Local sandbox only. Use --settings=config.recommendation_seed_settings; "
            "hosted environments and application databases are refused."
        )


def evaluate(users, pipeline):
    """Ground truth is authored cohort membership, independent of engine scores."""
    cohorts = {user.pk: index // 10 for index, user in enumerate(users)}
    hits = returned = covered = 0
    latencies = []
    for user in users:
        start = perf_counter()
        if pipeline == "unified":
            rows = UnifiedRecommendationService().recommend_talents(user, limit=5)
            candidates = [row["item"] for row in rows]
        else:
            rows = RecommendationEngine.recommend_talents_for_talent(user.talent_profile, limit=5)
            candidates = [row["talent"] for row in rows]
        latencies.append((perf_counter() - start) * 1000)
        covered += bool(candidates)
        returned += len(candidates)
        hits += sum(candidate.user_id != user.pk and
                    cohorts.get(candidate.user_id) == cohorts[user.pk]
                    for candidate in candidates)
    return {
        "pipeline": pipeline, "users": len(users), "relevant_results": hits,
        "returned_results": returned,
        "precision_at_5_percent": round(100 * hits / returned, 2) if returned else 0,
        "slot_relevance_at_5_percent": round(100 * hits / (len(users) * 5), 2),
        "user_coverage_percent": round(100 * covered / len(users), 2),
        "recall_at_5_percent": round(100 * hits / (len(users) * 9), 2),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2),
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * .95)], 2),
    }


class Command(BaseCommand):
    help = "Seed exactly 90 fictional users in an isolated local SQLite sandbox."

    def add_arguments(self, parser):
        parser.add_argument("--evaluate", action="store_true", help="Benchmark talent discovery.")
        parser.add_argument("--pipeline", choices=("legacy", "unified", "both"), default="both")
        parser.add_argument("--extended", action="store_true", help="Also seed catalogs and nine cold-start users.")
        parser.add_argument("--surfaces", nargs="+", choices=SURFACES,
                            help="Extended benchmark surfaces (defaults to all four).")
        parser.add_argument("--report", help="Write extended benchmark JSON inside the workspace.")

    def handle(self, *args, **options):
        require_local_database()
        if (options["surfaces"] or options["report"]) and not options["extended"]:
            raise CommandError("--surfaces and --report require --extended.")
        if options["report"] and not options["evaluate"]:
            raise CommandError("--report requires --evaluate.")
        report_path = None
        if options["report"]:
            report_path = Path(options["report"]).resolve()
            if not report_path.is_relative_to(Path(settings.BASE_DIR).resolve()):
                raise CommandError("The report must stay inside the workspace.")
        User = get_user_model()
        users = []
        with transaction.atomic():
            category, _ = SkillCategory.objects.get_or_create(name="Fictional recommendation sandbox")
            for index in range(90):
                cohort, member = divmod(index, 10)
                talent_category, topic, skill_name = GROUPS[cohort]
                username = f"{PREFIX}{index + 1:03d}"
                email = f"{username}@example.invalid"
                user, created = User.objects.get_or_create(username=username, defaults={
                    "email": email, "first_name": f"Fictional {topic}",
                    "last_name": f"Member {member + 1}", "country": "Ghana",
                })
                if not created and (user.email != email or user.has_usable_password()
                                    or user.is_staff or user.is_superuser):
                    raise CommandError(f"Refusing to modify conflicting account: {username}")
                if created:
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                profile, _ = TalentProfile.objects.update_or_create(user=user, defaults={
                    "talent_category": talent_category, "talent_area": topic,
                    "headline": f"Fictional {topic} practice profile",
                    "biography": "Synthetic local recommendation test account.",
                    "country": "Ghana" if member % 2 else "Kenya",
                    "city": "", "experience_level": ("BEGINNER", "INTERMEDIATE", "EXPERT")[member % 3],
                    "profile_visibility": "PUBLIC",
                })
                domain, _ = TalentDomain.objects.get_or_create(name=topic)
                skill, _ = Skill.objects.get_or_create(category=category, name=skill_name)
                profile.domains.set([domain])
                profile.skills.set([skill])
                users.append(user)
            manifest = seed_extended_fixtures(users, GROUPS, PREFIX) if options["extended"] else None
        self.stdout.write("Ready: 90 fictional users (reruns reuse the same accounts).")
        if manifest:
            self.stdout.write("Extended: nine cold-start users, 90 opportunities, 90 courses, 72 organizations.")
        if options["evaluate"]:
            pipelines = ("legacy", "unified") if options["pipeline"] == "both" else (options["pipeline"],)
            reports = []
            for pipeline in pipelines:
                if manifest:
                    for surface in options["surfaces"] or SURFACES:
                        for segment in manifest.segments:
                            self.stdout.write(f"Benchmarking {pipeline}/{surface}/{segment}...")
                            report = benchmark_surface(manifest, pipeline, surface, segment, self.stdout.write)
                            reports.append(report)
                            self.stdout.write(json.dumps(report, sort_keys=True))
                            self.stdout.flush()
                else:
                    self.stdout.write(json.dumps(evaluate(users, pipeline), sort_keys=True))
            if report_path:
                report_path.write_text(json.dumps({
                    "dataset": "90 profiled + 9 cold-start fictional users",
                    "limit": 5, "reports": reports,
                }, indent=2) + "\n", encoding="utf-8")
                self.stdout.write(f"Report saved: {report_path}")
