from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
import asyncio
import uuid


class Command(BaseCommand):
    help = 'Check messaging channel layer group delivery without sending user events.'

    def handle(self, **options):
        backend = settings.CHANNEL_LAYERS['default']['BACKEND']
        if 'InMemory' in backend:
            self.stderr.write('In-memory Channels works only within one process. Configure REDIS_URL for multiple workers.')
        async def probe():
            layer = get_channel_layer()
            channel = await layer.new_channel()
            group = 'health_' + uuid.uuid4().hex
            try:
                await layer.group_add(group, channel)
                await layer.group_send(group, {'type': 'health.check'})
                event = await asyncio.wait_for(layer.receive(channel), timeout=5)
                if event['type'] != 'health.check':
                    raise ValueError('Unexpected channel event')
            finally:
                await layer.group_discard(group, channel)
        try:
            async_to_sync(probe)()
        except Exception as error:
            raise CommandError(f'Channel layer delivery failed: {error}') from error
        self.stdout.write(self.style.SUCCESS(f'Channel group delivery OK: {backend}'))
