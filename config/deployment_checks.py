from django.conf import settings
from django.core.cache import caches
from django.core.checks import Error, Tags, register
from django.core.cache.backends.redis import RedisCache


@register(Tags.security, deploy=True)
def shared_authentication_cache(app_configs, **kwargs):
    if not settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE:
        if not settings.DEBUG:
            return [Error('Shared authentication protection cannot be disabled in production.', id='awinlink.E002')]
        return []
    from accounts.security import is_shared_auth_cache
    try:
        if is_shared_auth_cache(caches[settings.AUTH_RATE_LIMIT_CACHE_ALIAS]):
            return []
    except Exception:
        pass
    return [Error('Production authentication requires a supported shared atomic cache.',
        hint='Configure REDIS_URL for the security cache before release. Do not disable shared protection.',
        id='awinlink.E001')]


@register(Tags.security, deploy=True)
def shared_resource_cache(app_configs, **kwargs):
    if settings.DEBUG and not settings.HOSTED_PRODUCTION:
        return []
    try:
        if isinstance(caches[settings.AWINLINK_RESOURCE_CACHE_ALIAS], RedisCache):
            return []
    except Exception:
        pass
    return [Error('Production resource protection requires the built-in shared Redis cache.',
        hint='Configure REDIS_URL; process-local limits are development-only.', id='awinlink.E003')]
