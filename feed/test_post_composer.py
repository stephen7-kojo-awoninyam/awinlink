from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from feed.forms import PostForm
from feed.models import Post
from organizations.models import Organization
from talents.models import TalentProfile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PostComposerTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.storage = override_settings(MEDIA_ROOT=self.media.name)
        self.storage.enable()
        self.addCleanup(self.storage.disable)
        self.user = get_user_model().objects.create_user(username="composer_talent")
        self.talent = TalentProfile.objects.create(user=self.user, talent_category="ARTS")
        self.client.force_login(self.user)
        self.url = reverse("create_post")

    def data(self, **kwargs):
        return {"caption": "", "post_type": "GENERAL", "visibility": "PUBLIC", **kwargs}

    def ajax(self, data):
        return self.client.post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def photo(self):
        image = BytesIO()
        Image.new("RGB", (3, 3), "blue").save(image, "PNG")
        return SimpleUploadedFile("photo.png", image.getvalue(), content_type="image/png")

    def test_empty_and_whitespace_posts_rejected_on_server(self):
        for caption in ("", " \n\t "):
            with self.subTest(caption=caption):
                response = self.ajax(self.data(caption=caption, location="Location alone is not content"))
                self.assertEqual(response.status_code, 400)
                self.assertIn("__all__", response.json()["errors"])
        self.assertFalse(Post.objects.exists())
        response = self.client.post(self.url, self.data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add some text, a photo, or a video")

    def test_text_posts_use_existing_backend_and_ignore_forged_identity(self):
        other = get_user_model().objects.create_user(username="forged_author")
        response = self.ajax(self.data(caption="  My next chapter  ", author=other.pk, talent=999))
        self.assertEqual(response.status_code, 201)
        post = Post.objects.get(pk=response.json()["post_id"])
        self.assertEqual(post.caption, "My next chapter")
        self.assertEqual(post.author, self.user)
        self.assertEqual(post.talent, self.talent)
        self.assertEqual(response.json()["redirect_url"], reverse("home_feed"))

    def test_photo_only_post_is_valid(self):
        response = self.ajax(self.data(image=self.photo()))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Post.objects.get().image)
        self.assertEqual(Post.objects.get().caption, "")

    def test_video_only_post_is_valid(self):
        video = SimpleUploadedFile("practice.mp4", b"synthetic-upload-test", content_type="video/mp4")
        response = self.ajax(self.data(video=video))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Post.objects.get().video)

    def test_invalid_image_keeps_errors_and_creates_no_post(self):
        response = self.ajax(self.data(image=SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")))
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.json()["errors"])
        self.assertFalse(Post.objects.exists())

    def test_invalid_choices_cannot_bypass_validation(self):
        response = self.ajax(self.data(caption="Hello", visibility="EVERYONE", post_type="BOGUS"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"visibility", "post_type"})
        self.assertFalse(Post.objects.exists())

    def test_no_javascript_submission_still_redirects_to_feed(self):
        response = self.client.post(self.url, self.data(caption="A normal Django post"))
        self.assertRedirects(response, reverse("home_feed"), fetch_redirect_response=False)
        self.assertEqual(Post.objects.count(), 1)

    def test_authentication_and_csrf_remain_required(self):
        self.assertEqual(Client().get(self.url).status_code, 302)
        self.assertEqual(Client().post(self.url, self.data(caption="No login")).status_code, 302)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        self.assertEqual(browser.post(self.url, self.data(caption="No token")).status_code, 403)
        response = browser.get(reverse("courses"))
        token = browser.cookies["csrftoken"].value
        self.assertContains(response, 'id="postComposer"', count=1)
        valid = browser.post(self.url, self.data(caption="With token", csrfmiddlewaretoken=token),
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(valid.status_code, 201)

    def test_active_organization_is_attached_and_suspended_org_is_denied(self):
        user = get_user_model().objects.create_user(username="composer_org", role="ORGANIZATION")
        organization = Organization.objects.create(user=user, name="Local studio", country="Ghana")
        self.client.force_login(user)
        self.assertEqual(self.ajax(self.data(caption="A studio update")).status_code, 201)
        self.assertEqual(Post.objects.get().organization, organization)
        organization.status = "INACTIVE"
        organization.save(update_fields=["status"])
        self.assertEqual(self.ajax(self.data(caption="Should be denied")).status_code, 403)
        self.assertEqual(Post.objects.count(), 1)

    def test_shared_navigation_and_unique_form_ids_on_every_shell(self):
        for role in ("ATHLETE", "SCOUT", "COACH", "ORGANIZATION", "ADMIN"):
            self.user.role = role
            self.user.save(update_fields=["role"])
            for name in ("courses", "notification_list", "messaging:conversation_list", "create_post"):
                with self.subTest(role=role, route=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'id="postComposer"', count=1)
                    self.assertContains(response, 'id="composer_caption"', count=1)
                    self.assertContains(response, 'class="global-post-button"', count=1)
                    html = response.content.decode()
                    nav = html.split('<nav class="mobile-bottom-nav', 1)[1].split('</nav>', 1)[0]
                    self.assertNotIn('Discover', nav)
                    self.assertLess(nav.index('Opportunities'), nav.index('<span>Post</span>'))
                    self.assertLess(nav.index('<span>Post</span>'), nav.index('Messages'))
                    self.assertIn('mobileMoreToggle', nav)
        self.assertNotContains(Client().get(reverse("home")), 'id="postComposer"')

    def test_form_itself_enforces_content_rule(self):
        form = PostForm(data=self.data(caption=" \t "))
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())
