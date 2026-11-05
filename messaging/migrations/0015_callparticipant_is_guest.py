from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('messaging', '0014_retire_legacy_call_statuses')]
    operations = [migrations.AddField(
        model_name='callparticipant', name='is_guest',
        field=models.BooleanField(default=False),
    ), migrations.AddField(model_name='callparticipant', name='invitation_expires_at',
                           field=models.DateTimeField(null=True, blank=True))]
