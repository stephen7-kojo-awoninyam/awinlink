from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0003_recommendationhistory"),
        ("talents", "0007_talentprofile_experience_level_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TalentScore",
        ),

        migrations.CreateModel(
            name="TalentScore",
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
                    "physical_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "performance_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "achievement_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "experience_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "verification_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "overall_score",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=5,
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "talent",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="talent_score",
                        to="talents.talentprofile",
                    ),
                ),
            ],
        ),
    ]