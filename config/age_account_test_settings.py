"""Isolated age-account tests; no external database, mail, storage or cache."""
from .rising_talent_test_settings import *  # noqa: F403

AUTH_RATE_LIMIT_CACHE_ALIAS = "default"
AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE = False
PASSWORD_RESET_CACHE_ALIAS = "default"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
