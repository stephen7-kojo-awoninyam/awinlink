"""TURN configuration validation. Never include input values in diagnostics."""
import re
from django.conf import settings

_URL = re.compile(r"^(turns?):(\[[0-9a-fA-F:]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::([0-9]{1,5}))?(?:\?transport=(udp|tcp))?$")


def turn_configuration():
    raw_urls = [url.strip() for url in getattr(settings, 'TURN_SERVER_URLS', '').split(',') if url.strip()]
    urls = []
    for url in raw_urls:
        match = _URL.fullmatch(url)
        if match and (not match[3] or 1 <= int(match[3]) <= 65535) and not (match[1] == 'turns' and match[4] == 'udp'):
            urls.append(url)
    secret = getattr(settings, 'TURN_SHARED_SECRET', '')
    required = getattr(settings, 'TURN_REQUIRED', False)
    policy = getattr(settings, 'CALL_ICE_TRANSPORT_POLICY', 'all')
    errors = []
    if not urls:
        errors.append('TURN_SERVER_URLS must contain a public turn: or turns: endpoint.')
    if len(urls) != len(raw_urls):
        errors.append('TURN_SERVER_URLS contains an invalid URL; credentials must not be embedded in URLs.')
    if not secret:
        errors.append('TURN_SHARED_SECRET is missing.')
    elif len(secret) < 32 or secret != secret.strip() or any(char.isspace() for char in secret):
        errors.append('TURN_SHARED_SECRET must be at least 32 characters without whitespace; use a randomly generated value.')
    try:
        ttl = int(getattr(settings, 'TURN_CREDENTIAL_TTL_SECONDS', 3600))
        if not 300 <= ttl <= 86400:
            raise ValueError
    except (TypeError, ValueError):
        ttl = 3600
        errors.append('TURN_CREDENTIAL_TTL_SECONDS must be an integer between 300 and 86400.')
    if policy not in ('all', 'relay'):
        errors.append('CALL_ICE_TRANSPORT_POLICY must be all or relay.')
    return {
        'urls': urls, 'secret': secret, 'required': required, 'policy': policy,
        'ttl': ttl, 'errors': errors,
        'relay_configured': bool(urls and secret),
    }


def turn_summary(config):
    return {
        'urls_configured': bool(config['urls']),
        'secret_configured': bool(config['secret']),
        'production_ready': not config['errors'],
        'required': config['required'],
        'ice_transport_policy': config['policy'] if config['policy'] in ('all', 'relay') else 'invalid',
        'credential_ttl_seconds': config['ttl'],
        'udp_endpoint_configured': any(url.startswith('turn:') and '?transport=tcp' not in url for url in config['urls']),
        'tls_endpoint_configured': any(url.startswith('turns:') for url in config['urls']),
        'errors': config['errors'],
        'reachability_verified': False,
    }
