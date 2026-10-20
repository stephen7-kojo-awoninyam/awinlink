from django.test import SimpleTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from types import SimpleNamespace
from unittest.mock import AsyncMock
from rest_framework.test import APIClient
from asgiref.sync import async_to_sync
from redis.exceptions import TimeoutError as RedisTimeoutError
from rest_framework_simplejwt.tokens import AccessToken
import base64
import hashlib
import hmac
import time

from notifications.models import Notification
from .consumers import UserConsumer
from .models import (
    Call,
    CallParticipant,
    Conversation,
    ConversationParticipant,
    Message,
)


class MessagingUrlNamesTest(SimpleTestCase):
    def test_messaging_urls_are_namespaced_and_available(self):
        self.assertEqual(reverse("messaging:conversation_list"), "/messages/conversations/")
        self.assertEqual(reverse("messaging:conversation", args=[42]), "/messages/42/")
        self.assertEqual(reverse("messaging:start_conversation", args=[7]), "/messages/start/7/")
        self.assertEqual(reverse("messaging:start_coach_conversation", args=[11]), "/messages/start-coach/11/")


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class ConversationListSearchTests(TestCase):
    def test_list_search_includes_participant_username(self):
        user_model = get_user_model()
        current_user = user_model.objects.create_user(username="search_owner")
        participant = user_model.objects.create_user(
            username="search_handle",
            first_name="Taylor",
            last_name="Example",
        )
        conversation = Conversation.objects.create(created_by=current_user)
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=current_user,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=participant,
        )
        self.client.force_login(current_user)

        response = self.client.get(reverse("messaging:conversation_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="mobileGlobalSearch"')
        self.assertContains(response, 'data-search-name="Taylor Example"')
        self.assertContains(response, 'data-search-username="search_handle"')


class StartConversationTests(TestCase):
    def test_unconnected_user_is_redirected_to_connections_page(self):
        user_model = get_user_model()
        sender = user_model.objects.create_user(
            username="profile_visitor",
            password="TestPass123!",
        )
        talent_user = user_model.objects.create_user(
            username="profile_talent",
            password="TestPass123!",
        )
        self.client.force_login(sender)

        response = self.client.post(
            reverse("messaging:start_conversation", args=[talent_user.id])
        )

        self.assertRedirects(
            response,
            reverse("connections:connections_list"),
        )


class SendMessageAjaxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="self_messenger",
            password="TestPass123!",
        )
        self.conversation = Conversation.objects.create(
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_sending_message_does_not_redirect_or_reload(self):
        response = self.client.post(
            reverse("messaging:send_message", args=[self.conversation.id]),
            {"content": "A message to myself", "message_type": "TEXT"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["message"]["content"], "A message to myself")
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 1)

    def test_sending_reply_links_message_and_returns_quoted_message_preview(self):
        recipient = get_user_model().objects.create_user(
            username="reply_recipient",
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=recipient,
        )
        original = Message.objects.create(
            conversation=self.conversation,
            sender=recipient,
            content="The original message",
        )

        response = self.client.post(
            reverse("messaging:send_message", args=[self.conversation.id]),
            {
                "content": "My reply",
                "message_type": "TEXT",
                "reply_to_id": original.pk,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 201)
        reply = Message.objects.get(content="My reply")
        self.assertEqual(reply.reply_to, original)
        self.assertEqual(
            response.json()["message"]["reply_to"],
            {
                "id": original.pk,
                "sender_name": recipient.username,
                "content": "The original message",
            },
        )

    def test_reply_cannot_reference_a_message_from_another_conversation(self):
        other_conversation = Conversation.objects.create(
            created_by=self.user,
        )
        ConversationParticipant.objects.create(
            conversation=other_conversation,
            user=self.user,
        )
        original = Message.objects.create(
            conversation=other_conversation,
            sender=self.user,
            content="Not part of this chat",
        )

        response = self.client.post(
            reverse("messaging:send_message", args=[self.conversation.id]),
            {
                "content": "Invalid reply",
                "reply_to_id": original.pk,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.filter(content="Invalid reply").count(), 0)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class ConversationReplyTemplateTests(TestCase):
    def test_conversation_shows_reply_action_and_quoted_parent(self):
        user_model = get_user_model()
        sender = user_model.objects.create_user(username="quote_sender")
        recipient = user_model.objects.create_user(username="quote_recipient")
        conversation = Conversation.objects.create(created_by=sender)
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=sender,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=recipient,
        )
        original = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content="Original specific message",
        )
        Message.objects.create(
            conversation=conversation,
            sender=recipient,
            content="Reply in the conversation",
            reply_to=original,
        )
        self.client.force_login(recipient)

        response = self.client.get(
            reverse("messaging:conversation", args=[conversation.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original specific message")
        self.assertContains(response, "Reply in the conversation")
        self.assertContains(response, 'class="reply-message-button"')
        self.assertContains(response, 'name="reply_to_id"')
        self.assertContains(response, "Replying to")


class MessageReadReceiptTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.sender = user_model.objects.create_user(
            username="message_sender",
            password="TestPass123!",
        )
        self.recipient = user_model.objects.create_user(
            username="message_recipient",
            password="TestPass123!",
        )
        conversation = Conversation.objects.create(
            created_by=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=self.recipient,
        )
        self.message = Message.objects.create(
            conversation=conversation,
            sender=self.sender,
            content="Unread message",
        )

    def test_sender_cannot_mark_own_message_as_read(self):
        self.client.force_login(self.sender)

        response = self.client.patch(
            f"/api/messaging/messages/{self.message.id}/read/"
        )

        self.assertEqual(response.status_code, 403)
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_read)

    def test_recipient_can_mark_message_as_read(self):
        self.client.force_login(self.recipient)

        response = self.client.patch(
            f"/api/messaging/messages/{self.message.id}/read/"
        )

        self.assertEqual(response.status_code, 200)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_read)


class SendMessageAPINotificationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.sender = user_model.objects.create_user(
            username="api_sender",
            password="TestPass123!",
        )
        self.recipient = user_model.objects.create_user(
            username="api_recipient",
            password="TestPass123!",
        )
        self.conversation = Conversation.objects.create(
            created_by=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=self.conversation,
            user=self.recipient,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.sender)

    def test_api_message_notifies_other_conversation_members(self):
        response = self.client.post(
            f"/api/messaging/conversations/{self.conversation.id}/messages/create/",
            {"message_type": "TEXT", "content": "Hello from the API"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Notification.objects.filter(
                user=self.recipient,
                sender=self.sender,
                notification_type="MESSAGE",
                conversation=self.conversation,
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.sender,
                notification_type="MESSAGE",
                conversation=self.conversation,
            ).exists()
        )

    def test_api_message_reply_returns_quoted_message(self):
        original = Message.objects.create(
            conversation=self.conversation,
            sender=self.recipient,
            content="API original",
        )

        response = self.client.post(
            f"/api/messaging/conversations/{self.conversation.id}/messages/create/",
            {
                "message_type": "TEXT",
                "content": "API reply",
                "reply_to_id": original.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["reply_to"],
            {
                "id": original.pk,
                "sender_name": self.recipient.username,
                "content": "API original",
            },
        )

    def test_api_message_reply_cannot_reference_other_conversation(self):
        other_conversation = Conversation.objects.create(
            created_by=self.sender,
        )
        ConversationParticipant.objects.create(
            conversation=other_conversation,
            user=self.sender,
        )
        original = Message.objects.create(
            conversation=other_conversation,
            sender=self.sender,
            content="Outside message",
        )

        response = self.client.post(
            f"/api/messaging/conversations/{self.conversation.id}/messages/create/",
            {
                "message_type": "TEXT",
                "content": "Invalid API reply",
                "reply_to_id": original.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Message.objects.filter(content="Invalid API reply").exists()
        )


class RejectCallStateTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.caller = user_model.objects.create_user(
            username="call_caller",
            password="TestPass123!",
        )
        self.callee = user_model.objects.create_user(
            username="call_callee",
            password="TestPass123!",
        )
        conversation = Conversation.objects.create(
            created_by=self.caller,
        )
        self.call = Call.objects.create(
            conversation=conversation,
            initiated_by=self.caller,
            call_type="VOICE",
            status="RINGING",
        )
        CallParticipant.objects.create(
            call=self.call,
            user=self.caller,
            status="JOINED",
        )
        CallParticipant.objects.create(
            call=self.call,
            user=self.callee,
            status="RINGING",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.callee)

    def test_rejecting_last_callee_ends_the_call(self):
        response = self.client.post(
            f"/api/messaging/calls/{self.call.id}/reject/"
        )

        self.assertEqual(response.status_code, 200)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, "ENDED")


class UserConsumerRedisFailureTests(SimpleTestCase):
    def test_redis_timeout_rejects_socket_without_raising(self):
        consumer = UserConsumer()
        consumer.scope = {
            "user": SimpleNamespace(id=42, is_authenticated=True, is_active=True),
        }
        consumer.channel_name = "test-channel"
        consumer.channel_layer = SimpleNamespace(
            group_add=AsyncMock(
                side_effect=RedisTimeoutError("Redis unavailable")
            ),
        )
        consumer.close = AsyncMock()
        consumer.credentials_valid = AsyncMock(return_value=True)
        consumer.accept = AsyncMock()

        async_to_sync(consumer.connect)()

        consumer.close.assert_awaited_once_with(code=1013)
        consumer.accept.assert_not_awaited()


class MobileCallApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.caller = user_model.objects.create_user(username="native_caller", password="TestPass123!")
        self.callee = user_model.objects.create_user(username="native_callee", password="TestPass123!")
        self.conversation = Conversation.objects.create(created_by=self.caller)
        ConversationParticipant.objects.create(conversation=self.conversation, user=self.caller)
        ConversationParticipant.objects.create(conversation=self.conversation, user=self.callee)
        self.client = APIClient()

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_start_and_accept_call_expose_participants_for_webrtc_negotiation(self):
        self.client.force_authenticate(self.caller)
        started = self.client.post(
            f"/api/messaging/conversations/{self.conversation.id}/calls/start/",
            {"call_type": "VIDEO"},
            format="json",
        )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.data["call_type"], "VIDEO")
        self.assertEqual(len(started.data["participants"]), 2)

        self.client.force_authenticate(self.callee)
        accepted = self.client.post(f"/api/messaging/calls/{started.data['id']}/accept/")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data["status"], "ACTIVE")
        self.assertTrue(any(item["user"]["id"] == self.caller.id for item in accepted.data["participants"]))

    def test_call_start_requires_conversation_membership(self):
        outsider = get_user_model().objects.create_user(username="call_outsider", password="TestPass123!")
        self.client.force_authenticate(outsider)
        response = self.client.post(
            f"/api/messaging/conversations/{self.conversation.id}/calls/start/",
            {"call_type": "VOICE"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_end_call_ends_every_participant_and_rejects_nonparticipants(self):
        call = Call.objects.create(
            conversation=self.conversation,
            initiated_by=self.caller,
            call_type="VOICE",
            status="ACTIVE",
        )
        CallParticipant.objects.create(call=call, user=self.caller, status="JOINED")
        CallParticipant.objects.create(call=call, user=self.callee, status="JOINED")
        outsider = get_user_model().objects.create_user(username="call_end_outsider")
        self.client.force_authenticate(outsider)
        denied = self.client.post(f"/api/messaging/calls/{call.id}/end/")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.caller)
        ended = self.client.post(f"/api/messaging/calls/{call.id}/end/")
        self.assertEqual(ended.status_code, 200)
        call.refresh_from_db()
        self.assertEqual(call.status, "ENDED")
        self.assertEqual(
            set(call.participants.values_list("status", flat=True)),
            {"LEFT"},
        )

    def test_incoming_call_feed_only_contains_calls_ringing_this_user(self):
        call = Call.objects.create(
            conversation=self.conversation,
            initiated_by=self.caller,
            call_type="VOICE",
            status="RINGING",
        )
        CallParticipant.objects.create(call=call, user=self.caller, status="JOINED")
        CallParticipant.objects.create(call=call, user=self.callee, status="RINGING")
        self.client.force_authenticate(self.callee)

        response = self.client.get("/api/messaging/calls/incoming/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [call.id])

    @override_settings(TURN_SERVER_URLS="turn:turn.example.test:3478,turns:turn.example.test:5349", TURN_SHARED_SECRET="unit-test-secret")
    def test_ice_endpoint_returns_short_lived_coturn_credentials(self):
        self.client.force_authenticate(self.caller)
        response = self.client.get("/api/messaging/calls/ice-servers/")
        self.assertEqual(response.status_code, 200)
        turn = response.data["ice_servers"][1]
        expires, user_id = turn["username"].split(":")
        self.assertEqual(user_id, str(self.caller.id))
        self.assertGreaterEqual(int(expires), int(time.time()) + 3590)
        expected = base64.b64encode(
            hmac.new(b"unit-test-secret", turn["username"].encode(), hashlib.sha1).digest()
        ).decode("ascii")
        self.assertEqual(turn["credential"], expected)
        self.assertEqual(turn["urls"], ["turn:turn.example.test:3478", "turns:turn.example.test:5349"])

    def test_ice_endpoint_requires_authentication(self):
        response = self.client.get("/api/messaging/calls/ice-servers/")
        self.assertEqual(response.status_code, 401)


class MobileWebSocketJwtTests(TransactionTestCase):
    def test_authorization_header_is_attached_to_websocket_scope(self):
        from config.asgi import JWTWebSocketMiddleware

        user = get_user_model().objects.create_user(username="socket_header_user", password="TestPass123!")

        async def inner(scope, receive, send):
            return scope["user"]

        scope = {
            "type": "websocket",
            "headers": [(b"authorization", f"Bearer {AccessToken.for_user(user)}".encode())],
        }
        resolved = async_to_sync(JWTWebSocketMiddleware(inner))(scope, None, None)
        self.assertEqual(resolved.pk, user.pk)

    def test_jwt_bearer_token_resolves_to_authenticated_channels_user(self):
        from config.asgi import _user_from_jwt

        user = get_user_model().objects.create_user(username="socket_mobile_user", password="TestPass123!")
        resolved = async_to_sync(_user_from_jwt)(str(AccessToken.for_user(user)))
        self.assertEqual(resolved.pk, user.pk)
        self.assertTrue(resolved.is_authenticated)

    def test_invalid_jwt_is_anonymous(self):
        from config.asgi import _user_from_jwt

        self.assertIsNone(async_to_sync(_user_from_jwt)("invalid-token"))
