r"""Synthetic loopback preview, with an isolated database and generated media.

Run: .venv\Scripts\python.exe scripts\preview_social_dashboard.py
Never reads or writes the application's database or uploads.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AUDIT = ROOT / ".audit-social-dashboard"
AUDIT.mkdir(exist_ok=True)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.recommendation_seed_settings"
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
from django.conf import settings

settings.DEBUG = True
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": AUDIT / "preview.sqlite3"}}
settings.MEDIA_ROOT = AUDIT / "media"
settings.STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
settings.WEB_PUSH_PUBLIC_KEY = ""
settings.WEB_PUSH_PRIVATE_KEY = ""
import django
django.setup()

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from connections.models import Follow
from domains.models import TalentDomain
from feed.models import Post, Comment, PostLike
from messaging.models import Conversation, ConversationParticipant, Message
from notifications.models import Notification
from talents.models import TalentProfile

assert Path(connection.settings_dict["NAME"]).resolve() == (AUDIT / "preview.sqlite3").resolve()
call_command("migrate", interactive=False, verbosity=0)
media = Path(settings.MEDIA_ROOT)
media.mkdir(exist_ok=True)
font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 84)
domain, _ = TalentDomain.objects.get_or_create(name="Illustration")
people = [("preview_amina", "Amina", "Bello", "Creative technologist. Always making something."),
          ("preview_jordan", "Jordan", "Lee", "Visual artist & storyteller"),
          ("preview_maya", "Maya", "Owusu", "Turning ideas into something you can feel"),
          ("preview_noah", "Noah", "Mensah", "Illustrator. Curious by nature."),
          ("preview_sophia", "Sophia", "Chen", "Designing a little more possibility"),
          ("preview_elijah", "Elijah", "Adeyemi", "Art, movement, and everything in between")]
users = []
for index, (username, first, last, headline) in enumerate(people):
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.first_name, user.last_name = first, last
    user.set_password("LocalPreviewOnly123!")
    user.save()
    profile, _ = TalentProfile.objects.update_or_create(user=user, defaults={
        "talent_category": "ARTS", "talent_area": "Illustration", "headline": headline,
        "country": "Ghana", "city": "Accra", "profile_visibility": "PUBLIC",
        "biography": "A fictional profile for the local dashboard preview.",
    })
    profile.domains.set([domain])
    avatar = Image.new("RGB", (240, 240), ["#dbe9ff", "#d8edea", "#fae7d9", "#e8e2ff", "#deebff", "#f6e3eb"][index])
    draw = ImageDraw.Draw(avatar)
    draw.text((120, 120), first[0] + last[0], fill="#26558b", font=font, anchor="mm")
    avatar.save(media / f"avatar-{index}.png")
    user.profile_picture = f"avatar-{index}.png"
    user.save(update_fields=["profile_picture"])
    users.append(user)
viewer = users[0]
Follow.objects.get_or_create(follower=viewer, following=users[1])
Follow.objects.get_or_create(follower=viewer, following=users[2])

# Generated geometric artwork is only a fixture, not production feed content.
image = Image.new("RGB", (1100, 1000), "#ddeaf7")
draw = ImageDraw.Draw(image)
draw.rectangle((0, 630, 1100, 1000), fill="#256aa2")
draw.ellipse((705, 90, 920, 305), fill="#f4d8aa")
draw.rounded_rectangle((160, 215, 720, 1020), radius=280, fill="#b1c9e2")
draw.rounded_rectangle((250, 300, 630, 1020), radius=190, fill="#5085b9")
draw.rounded_rectangle((330, 390, 550, 1020), radius=110, fill="#143e6b")
draw.rectangle((720, 520, 1100, 625), fill="#749abc")
draw.rectangle((720, 625, 1100, 665), fill="#a4bfd6")
draw.polygon([(0, 810), (1100, 650), (1100, 1000), (0, 1000)], fill="#e7d5bb")
draw.line((0, 900, 1100, 740), fill="#c3ae92", width=4)
image.save(media / "blue-hour.png")
post, _ = Post.objects.update_or_create(author=users[1], caption="A study in blue. Finding a little calm in the spaces between. What have you been creating this week?", defaults={
    "talent": users[1].talent_profile, "image": "blue-hour.png", "post_type": "SHOWCASE", "location": "Accra, Ghana",
})
Post.objects.filter(pk=post.pk).update(created_at=timezone.now())
Comment.objects.get_or_create(user=users[2], post=post, text="The light and the colors. So good!")
for user in users[2:]:
    PostLike.objects.get_or_create(user=user, post=post)
Post.objects.get_or_create(author=users[2], talent=users[2].talent_profile, caption="Small steps count. Finished my first collection of illustrations today, and I couldn't be happier.", post_type="ACHIEVEMENT")
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
if ffmpeg:
    clip = media / "practice.mp4"
    if not clip.exists():
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x1f5fa3:s=480x720:r=12",
                        "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    Post.objects.get_or_create(author=users[3], talent=users[3].talent_profile,
                               caption="A little peek at the process.", video="practice.mp4", post_type="TRAINING")
conversation, _ = Conversation.objects.get_or_create(name="Local preview conversation", created_by=viewer)
for user in (viewer, users[1]):
    ConversationParticipant.objects.get_or_create(conversation=conversation, user=user)
Message.objects.get_or_create(conversation=conversation, sender=users[1], content="Hey Amina, excited to see what you make next!")
Notification.objects.get_or_create(user=viewer, sender=users[2], notification_type="LIKE", message="Maya liked your latest work.", post=post)
print("Local social dashboard preview ready at http://127.0.0.1:8776/home_feed/", flush=True)
if "--seed-only" not in sys.argv:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from config.asgi import application
    from daphne.server import Server
    Server(ASGIStaticFilesHandler(application), endpoints=["tcp:port=8776:interface=127.0.0.1"]).run()
