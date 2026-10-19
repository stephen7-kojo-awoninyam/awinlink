from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_mobile_safety")]
    operations = [
        migrations.AddField(model_name="user", name="terms_accepted_version",
            field=models.CharField(blank=True, default="", editable=False, max_length=64)),
        migrations.AddField(model_name="user", name="terms_accepted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True)),
    ]
