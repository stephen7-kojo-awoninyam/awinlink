"""TURN configuration validation. Never include input values in diagnostics."""
import re
import ipaddress
from django.conf import settings

_URL = re.compile(r"^(turns?):(\[[0-9a-fA-F:]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::([0-9]{1,5}))?(?:\?transport=(udp|tcp))?$")


def turn_configuration():
    raw_value = getattr(settings, 'TURN_SERVER_URLS', '')
    raw_urls = [url.strip() for url in raw_value.split(',')] if isinstance(raw_value, str) and raw_value else []
    urls = []
    for url in raw_urls:
        match = _URL.fullmatch(url)
        host_valid = False
        if match:
            host = match[2]
            if host.startswith('['):
                try:
                    ipaddress.IPv6Address(host[1:-1])
                    host_valid = True
                except ValueError:
                    pass
            else:
                host_valid = len(host) <= 253 and all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.'))
                if re.fullmatch(r'[0-9.]+', host) and '.' in host:
                    try:
                        ipaddress.IPv4Address(host)
                    except ValueError:
                        host_valid = False
        if match and host_valid and (not match[3] or 1 <= int(match[3]) <= 65535) and not (match[1] == 'turns' and match[4] == 'udp'):
            urls.append(url)
    secret = getattr(settings, 'TURN_SHARED_SECRET', '')
    required = getattr(settings, 'TURN_REQUIRED', False)
    policy = getattr(settings, 'CALL_ICE_TRANSPORT_POLICY', 'all')
    errors = []
    if not urls:
        errors.append('TURN_SERVER_URLS must contain a public turn: or turns: endpoint.')
    if not isinstance(raw_value, str) or len(urls) != len(raw_urls):
        errors.append('TURN_SERVER_URLS contains an invalid URL; credentials must not be embedded in URLs.')
    if not secret:
        errors.append('TURN_SHARED_SECRET is missing.')
    elif not isinstance(secret, str) or len(secret) < 32 or any(char.isspace() or not char.isprintable() for char in secret):
        errors.append('TURN_SHARED_SECRET must be at least 32 characters without whitespace; use a randomly generated value.')
    ttl_valid = True
    try:
        raw_ttl = getattr(settings, 'TURN_CREDENTIAL_TTL_SECONDS', 3600)
        if type(raw_ttl) is not int and not (isinstance(raw_ttl, str) and re.fullmatch(r'[0-9]+', raw_ttl)):
            raise ValueError
        ttl = int(raw_ttl)
        if not 300 <= ttl <= 86400:
            raise ValueError
    except (TypeError, ValueError):
        ttl_valid = False
        ttl = 3600
        errors.append('TURN_CREDENTIAL_TTL_SECONDS must be an integer between 300 and 86400.')
    if policy not in ('all', 'relay'):
        errors.append('CALL_ICE_TRANSPORT_POLICY must be all or relay.')
    optional_stun_only = not required and policy == 'all' and raw_value == '' and secret == '' and ttl_valid
    return {
        'urls': urls, 'secret': secret, 'required': required, 'policy': policy,
        'ttl': ttl, 'errors': errors,
        'relay_configured': not errors,
        'optional_stun_only': optional_stun_only,
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
