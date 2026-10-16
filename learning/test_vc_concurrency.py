from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.test import TransactionTestCase, skipUnlessDBFeature

from . import classroom_chat as chat, classroom_services as services, whiteboard_services as board
from . import test_classroom_security as security, test_whiteboard as drawings
from .models import ClassroomChatMessage, Whiteboard, WhiteboardOperation


class VCConcurrencyTests(security.ClassroomFixture, TransactionTestCase):
    race = security.ClassroomConcurrencyTests.race

    def setUp(self):
        delivery = patch('notifications.signals.publish_notification'); delivery.start(); self.addCleanup(delivery.stop)
        super().setUp()

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_writers_at_one_revision_commit_one_board_change(self):
        state = board.snapshot(actor=self.host, session_id=self.session.pk)
        def draw():
            return board.command(actor=self.host, session_id=self.session.pk, data={'operation_id': str(uuid4()),
                'base_revision': state['revision'], 'action': 'add', 'payload': drawings.drawing()})
        outcomes = self.race(draw, draw)
        self.assertEqual(sum(isinstance(item, board.RevisionConflict) for item in outcomes), 1)
        self.assertEqual(Whiteboard.objects.get(session=self.session).revision, 1)
        self.assertEqual(WhiteboardOperation.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_chat_retry_creates_exactly_one_message(self):
        self.admit(); data = {'client_id': str(uuid4()), 'text': 'One concurrent message'}
        def send(): return chat.send(actor=self.learner, session_id=self.session.pk, data=data)
        outcomes = self.race(send, send)
        self.assertEqual(len({item['id'] for item in outcomes}), 1)
        self.assertEqual(ClassroomChatMessage.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_ending_racing_a_board_write_cannot_allow_post_end_edits(self):
        state = board.snapshot(actor=self.host, session_id=self.session.pk)
        def draw(): return board.command(actor=self.host, session_id=self.session.pk, data={'operation_id': str(uuid4()),
            'base_revision': state['revision'], 'action': 'add', 'payload': drawings.drawing()})
        self.race(draw, lambda: services.end_session(actor=self.host, session=self.session))
        self.session.refresh_from_db(); self.assertEqual(self.session.status, 'ENDED')
        with self.assertRaises(PermissionDenied): draw()
        self.assertLessEqual(WhiteboardOperation.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_removal_racing_chat_send_closes_future_read_and_write_access(self):
        participant = self.admit()
        def send(): return chat.send(actor=self.learner, session_id=self.session.pk,
            data={'client_id': str(uuid4()), 'text': 'Before removal only'})
        self.race(send, lambda: services.remove_participant(actor=self.host, session=self.session, participant=participant))
        with self.assertRaises(PermissionDenied): send()
        with self.assertRaises(PermissionDenied): chat.history(actor=self.learner, session_id=self.session.pk)
        self.assertLessEqual(ClassroomChatMessage.objects.count(), 1)
