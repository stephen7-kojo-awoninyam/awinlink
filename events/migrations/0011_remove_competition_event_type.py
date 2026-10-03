from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0010_eventcomment_eventlike"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("WORKSHOP", "Workshop"),
                    ("BOOTCAMP", "Bootcamp"),
                    ("AUDITION", "Audition"),
                    ("CONFERENCE", "Conference"),
                    ("TRIAL", "Talent Trial"),
                    ("WEBINAR", "Webinar"),
                ],
                max_length=30,
            ),
        ),
    ]
