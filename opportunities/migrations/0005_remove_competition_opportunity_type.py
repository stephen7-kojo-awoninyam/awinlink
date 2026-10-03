from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opportunities", "0004_opportunity_experience_level_opportunity_skills_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="opportunity",
            name="opportunity_type",
            field=models.CharField(
                choices=[
                    ("JOB", "Job"),
                    ("TRIAL", "Sports Trial"),
                    ("SCHOLARSHIP", "Scholarship"),
                    ("AUDITION", "Audition"),
                ],
                default="JOB",
                max_length=20,
            ),
        ),
    ]
