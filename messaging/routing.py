from django.urls import re_path

from .consumers import (
    CallConsumer,
    UserConsumer,
)


websocket_urlpatterns = [
    re_path(
        r"ws/calls/(?P<call_id>\d+)/$",
        CallConsumer.as_asgi(),
    ),
    re_path(
    r"ws/user/$",
    UserConsumer.as_asgi(),
    ),
]