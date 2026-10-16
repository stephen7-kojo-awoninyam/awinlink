from django.urls import re_path

from .consumers import ClassroomConsumer
from .whiteboard_consumer import WhiteboardConsumer


websocket_urlpatterns = [
    re_path(r"^ws/learning/sessions/(?P<session_id>[1-9]\d{0,18})/whiteboard/$", WhiteboardConsumer.as_asgi()),
    re_path(r"^ws/learning/sessions/(?P<session_id>[1-9]\d{0,18})/$", ClassroomConsumer.as_asgi()),
]
