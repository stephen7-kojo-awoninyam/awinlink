from django.core.validators import RegexValidator
from django.db import migrations, models
import learning.validators


class Migration(migrations.Migration):
    dependencies = [('learning', '0015_resource_pagination_indexes')]

    operations = [
        migrations.AddField(
            model_name='lesson', name='captions',
            field=models.FileField(blank=True, null=True, upload_to='learning/captions/', validators=[learning.validators.validate_webvtt]),
        ),
        migrations.AddField(
            model_name='lesson', name='caption_language',
            field=models.CharField(blank=True, max_length=35, validators=[RegexValidator('^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$', 'Enter a valid BCP 47 language tag.')]),
        ),
        migrations.AddField(
            model_name='lesson', name='transcript',
            field=models.TextField(blank=True, validators=[learning.validators.validate_transcript]),
        ),
    ]
