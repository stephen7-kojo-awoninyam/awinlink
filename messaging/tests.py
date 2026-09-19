from django.test import SimpleTestCase
from django.urls import reverse


class MessagingUrlNamesTest(SimpleTestCase):
    def test_messaging_urls_are_namespaced_and_available(self):
        self.assertEqual(reverse("messaging:conversation_list"), "/messages/conversations/")
        self.assertEqual(reverse("messaging:conversation", args=[42]), "/messages/42/")
        self.assertEqual(reverse("messaging:start_conversation", args=[7]), "/messages/start/7/")
        self.assertEqual(reverse("messaging:start_coach_conversation", args=[11]), "/messages/start-coach/11/")
