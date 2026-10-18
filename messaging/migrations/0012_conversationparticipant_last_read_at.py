from django.db import migrations, models


def preserve_read_history(apps, schema_editor):
    Participant = apps.get_model('messaging', 'ConversationParticipant')
    Message = apps.get_model('messaging', 'Message')
    alias = schema_editor.connection.alias
    for participant in Participant.objects.using(alias).iterator():
        latest_read = Message.objects.using(alias).filter(
            conversation_id=participant.conversation_id, is_read=True,
        ).exclude(sender_id=participant.user_id).order_by('-created_at').first()
        if latest_read:
            Participant.objects.using(alias).filter(pk=participant.pk).update(last_read_at=latest_read.created_at)


class Migration(migrations.Migration):
    dependencies = [('messaging', '0011_message_reply_to')]
    operations = [migrations.AddField(
        model_name='conversationparticipant', name='last_read_at',
        field=models.DateTimeField(null=True, blank=True),
    ), migrations.RunPython(preserve_read_history, migrations.RunPython.noop)]
