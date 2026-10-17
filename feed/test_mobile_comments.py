from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from feed.models import Post, Comment


class MobileCommentTests(APITestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(username='comment-author')
        self.viewer = get_user_model().objects.create_user(username='comment-viewer')
        self.post = Post.objects.create(author=self.author, caption='Private', visibility='PRIVATE')
        self.url = f'/api/feed/posts/{self.post.pk}/comments/'
        self.client.force_authenticate(self.viewer)

    def test_private_comments_cannot_be_read_or_created(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'text': 'no'}, format='json').status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_public_comment_lifecycle_and_ownership(self):
        self.post.visibility = 'PUBLIC'
        self.post.save()
        response = self.client.post(self.url, {'text': ' Hello '}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['text'], 'Hello')
        delete_url = f"/api/feed/comments/{response.data['id']}/delete/"
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.delete(delete_url).status_code, 403)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(len(self.client.get(self.url).data), 1)
        self.assertEqual(self.client.delete(delete_url).status_code, 200)

    def test_non_string_comment_is_validation_error(self):
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.post(self.url, {'text': ['bad']}, format='json').status_code, 400)
