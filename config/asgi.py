"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)


django_asgi_application = get_asgi_application()


from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.db import database_sync_to_async
from channels.security.websocket import AllowedHostsOriginValidator
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from messaging.routing import websocket_urlpatterns


@database_sync_to_async
def _user_from_jwt(token):
    """Resolve a Channels user from the same JWT used by the mobile REST API."""
    try:
        authentication = JWTAuthentication()
        validated_token = authentication.get_validated_token(token)
        return authentication.get_user(validated_token)
    except (AuthenticationFailed, InvalidToken, TokenError):
        return None


class JWTWebSocketMiddleware:
    """Allow native clients to authenticate Channels with an Authorization header."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin1")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            user = await _user_from_jwt(token)
            if user is not None:
                scope = {**scope, "user": user, "jwt_authenticated": True}
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return AuthMiddlewareStack(JWTWebSocketMiddleware(inner))


class WebSocketOriginMiddleware:
    """Validate browser origins while allowing authenticated native JWT sockets."""

    def __init__(self, inner):
        self.inner = inner
        self.browser_application = AllowedHostsOriginValidator(inner)

    async def __call__(self, scope, receive, send):
        has_origin = any(name == b"origin" for name, _ in scope.get("headers", []))
        if scope.get("jwt_authenticated") and not has_origin:
            return await self.inner(scope, receive, send)
        return await self.browser_application(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,

        "websocket": JWTAuthMiddlewareStack(
            WebSocketOriginMiddleware(URLRouter(
                websocket_urlpatterns
            ))
        ),
    }
)
