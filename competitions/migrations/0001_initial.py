import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0008_organization_cover_photo_organization_followers"),
        ("talents", "0014_talentprofile_talent_area"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Competition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(max_length=200),
                ),
                (
                    "description",
                    models.TextField(),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("SPORTS", "Sports"),
                            ("SCIENCE_TECHNOLOGY", "Science & Technology"),
                            ("ARTS", "Arts"),
                            ("OTHERS", "Others"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "discipline",
                    models.CharField(blank=True, max_length=150),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SUBMITTED", "Submitted for approval"),
                            ("REJECTED", "Changes requested"),
                            ("APPROVED", "Approved"),
                            ("PUBLISHED", "Published"),
                            ("REGISTRATION_CLOSED", "Registration closed"),
                            ("ONGOING", "Ongoing"),
                            ("JUDGING", "Judging"),
                            ("RESULTS", "Results published"),
                            ("COMPLETED", "Completed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="DRAFT",
                        max_length=30,
                    ),
                ),
                ("registration_start", models.DateField()),
                ("registration_end", models.DateField()),
                ("competition_start", models.DateField()),
                ("competition_end", models.DateField()),
                ("location", models.CharField(blank=True, max_length=200)),
                ("online", models.BooleanField(default=False)),
                ("requirements", models.TextField(blank=True)),
                ("prizes", models.TextField(blank=True)),
                ("rules", models.TextField(blank=True)),
                (
                    "max_participants",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("review_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competitions",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="CompetitionParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("REGISTERED", "Registered"),
                            ("WITHDRAWN", "Withdrawn"),
                            ("DISQUALIFIED", "Disqualified"),
                        ],
                        default="REGISTERED",
                        max_length=20,
                    ),
                ),
                ("submission", models.TextField(blank=True)),
                ("submission_url", models.URLField(blank=True)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="competitions.competition",
                    ),
                ),
                (
                    "talent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competition_participations",
                        to="talents.talentprofile",
                    ),
                ),
            ],
            options={"ordering": ("registered_at",)},
        ),
        migrations.CreateModel(
            name="CompetitionJudge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("MENTOR", "Mentor"),
                            ("EVALUATOR", "Evaluator"),
                            ("JUDGE", "Judge"),
                        ],
                        default="JUDGE",
                        max_length=20,
                    ),
                ),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "coach",
                    models.ForeignKey(
                        limit_choices_to={"role": "COACH"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competition_judging_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="judges",
                        to="competitions.competition",
                    ),
                ),
            ],
            options={"ordering": ("assigned_at",)},
        ),
        migrations.CreateModel(
            name="CompetitionEvaluation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                ("feedback", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "judge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competition_evaluations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "participant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evaluations",
                        to="competitions.competitionparticipant",
                    ),
                ),
            ],
            options={"ordering": ("-updated_at",)},
        ),
        migrations.CreateModel(
            name="CompetitionResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "position",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                ("award", models.CharField(blank=True, max_length=150)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "participant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result",
                        to="competitions.competitionparticipant",
                    ),
                ),
            ],
            options={
                "ordering": ("position", "participant__registered_at"),
            },
        ),
        migrations.AddConstraint(
            model_name="competitionparticipant",
            constraint=models.UniqueConstraint(
                fields=("competition", "talent"),
                name="unique_competition_talent",
            ),
        ),
        migrations.AddConstraint(
            model_name="competitionjudge",
            constraint=models.UniqueConstraint(
                fields=("competition", "coach"),
                name="unique_competition_coach_judge",
            ),
        ),
        migrations.AddConstraint(
            model_name="competitionevaluation",
            constraint=models.UniqueConstraint(
                fields=("participant", "judge"),
                name="unique_participant_competition_judge_evaluation",
            ),
        ),
    ]
