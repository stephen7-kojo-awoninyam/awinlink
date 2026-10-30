from django.db import migrations, models


def retire_legacy_calls(apps, schema_editor):
    alias = schema_editor.connection.alias
    Call = apps.get_model('messaging', 'Call')
    Participant = apps.get_model('messaging', 'CallParticipant')
    # These retired statuses predate group calls. Never revive an old accepted
    # call as a live session. Keep its decision and all original timestamps.
    for call in Call.objects.using(alias).filter(status__in=['ACCEPTED', 'REJECTED']).iterator():
        original = call.status
        if call.legacy_status and call.legacy_status != original:
            raise RuntimeError('Conflicting legacy call provenance; review before migration.')
        Participant.objects.using(alias).filter(call_id=call.pk, status='JOINED').update(status='LEFT')
        # The removed receiver field cannot establish who rejected an already
        # upgraded call. Preserve the aggregate decision, not an invented
        # individual rejection. Existing explicit REJECTED rows stay intact.
        Participant.objects.using(alias).filter(call_id=call.pk, status__in=['INVITED', 'RINGING']).update(status='MISSED')
        call.legacy_status = original
        call.status = 'ENDED'
        call.save(using=alias, update_fields=['legacy_status', 'status'])


class Migration(migrations.Migration):
    dependencies = [('messaging', '0013_resource_pagination_indexes')]
    operations = [
        migrations.AddField(model_name='call', name='legacy_status',
            field=models.CharField(max_length=10, blank=True, default='', editable=False)),
        # Unconditionally irreversible: removing provenance is not a rollback.
        migrations.RunPython(retire_legacy_calls),
    ]
