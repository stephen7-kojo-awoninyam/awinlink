"""Prevent shared or browser caches from retaining viewer-dependent responses."""
from django.utils.cache import patch_cache_control


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Middleware also sees denial responses produced by Django's exception
        # handler, outside an individual view's never_cache decorator.
        if request.path_info.startswith(('/api/', '/media/', '/coaches/', '/scouts/',
                '/athletes/', '/talents/', '/talent/', '/events/', '/portfolio/',
                '/feed/', '/home_feed/', '/explore/', '/analytics/', '/recommendations/')):
            patch_cache_control(response, private=True, no_store=True)
        return response
