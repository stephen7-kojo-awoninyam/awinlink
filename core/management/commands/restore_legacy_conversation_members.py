"""Restore empty legacy rooms only from an independently reviewed backup manifest."""
import hashlib
import json
from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from messaging.models import Conversation, ConversationParticipant


class Command(BaseCommand):
    help = 'Validate a reviewed pre-0006 backup membership manifest; dry-run unless --apply.'

    def add_arguments(self, parser):
        parser.add_argument('manifest')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        try:
            raw = Path(options['manifest']).read_bytes()
            manifest = json.loads(raw)
        except (OSError, ValueError) as error:
            raise CommandError('Cannot read a valid JSON membership manifest.') from error
        if not isinstance(manifest, dict) or set(manifest) != {'source_backup_sha256', 'rooms'}:
            raise CommandError('Manifest requires source_backup_sha256 and rooms only.')
        if not isinstance(manifest['source_backup_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', manifest['source_backup_sha256']):
            raise CommandError('A reviewed source backup SHA-256 is required.')
        rooms = manifest['rooms']
        if not isinstance(rooms, list) or not rooms:
            raise CommandError('rooms must be a nonempty list.')
        parsed = {}
        for room in rooms:
            if not isinstance(room, dict) or set(room) != {'conversation_id', 'user_ids'}:
                raise CommandError('Each room requires conversation_id and user_ids only.')
            pk, users = room['conversation_id'], room['user_ids']
            if (type(pk) is not int or pk <= 0 or pk in parsed or not isinstance(users, list)
                    or len(users) not in (1, 2) or any(type(value) is not int or value <= 0 for value in users)
                    or len(set(users)) != len(users)):
                raise CommandError('Invalid or duplicate legacy room/user identifiers.')
            parsed[pk] = set(users)  # A single user may own both legacy profiles.
        alias = options['database']
        with transaction.atomic(using=alias):
            found = set(Conversation.objects.using(alias).select_for_update().filter(pk__in=sorted(parsed)).order_by('pk').values_list('pk', flat=True))
            users = set().union(*parsed.values())
            if found != set(parsed) or get_user_model().objects.using(alias).filter(pk__in=users).count() != len(users):
                raise CommandError('Unknown room or user; no memberships changed.')
            additions = []
            for pk, desired in parsed.items():
                actual = set(ConversationParticipant.objects.using(alias).filter(conversation_id=pk).values_list('user_id', flat=True))
                if actual and actual != desired:
                    raise CommandError('Nonempty membership conflicts with manifest; no memberships changed.')
                if not actual:
                    additions.extend(ConversationParticipant(conversation_id=pk, user_id=user) for user in sorted(desired))
            if options['apply']:
                ConversationParticipant.objects.using(alias).bulk_create(additions)
        self.stdout.write(json.dumps({'applied': options['apply'], 'rooms': len(parsed), 'memberships': len(additions),
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'source_backup_sha256': manifest['source_backup_sha256']}))
