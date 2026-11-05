import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0009_age_safety_permissions')]

    operations = [
        migrations.AddField(
            model_name='googleauthattempt', name='purpose',
            field=models.CharField(choices=[('LOGIN', 'Sign in or link'), ('DELETE', 'Account deletion')], default='LOGIN', max_length=16),
        ),
        migrations.AddField(
            model_name='googleauthattempt', name='reauth_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='googleauthattempt', name='reauth_auth_hash',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
