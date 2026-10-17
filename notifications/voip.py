"""Direct APNs VoIP transport. Expo notification tokens cannot deliver PushKit pushes."""
import logging
import time
from django.conf import settings
from .models import VoipPushToken

logger = logging.getLogger(__name__)


def native_call_uuid(call_id):
    if not 0 < call_id <= 0xffffffffffff:
        raise ValueError('Invalid native call ID.')
    return f'a7100000-0000-4000-8000-{call_id:012x}'


def send_voip_call_push(user_id, data):
    """Return Expo device tokens successfully covered by native VoIP delivery."""
    delivered = set()
    if not all([settings.MOBILE_APNS_TEAM_ID, settings.MOBILE_APNS_KEY_ID, settings.MOBILE_APNS_PRIVATE_KEY]):
        return delivered
    if data['expires_at'] <= time.time():
        return delivered
    import jwt
    import httpx
    try:
        bearer = jwt.encode({'iss': settings.MOBILE_APNS_TEAM_ID, 'iat': int(time.time())}, settings.MOBILE_APNS_PRIVATE_KEY, algorithm='ES256', headers={'kid': settings.MOBILE_APNS_KEY_ID})
    except (ValueError, TypeError, jwt.PyJWTError):
        logger.warning('APNs signing credentials are invalid; using notification fallback.')
        return delivered
    for device in VoipPushToken.objects.filter(user_id=user_id):
        host = 'api.sandbox.push.apple.com' if device.environment == 'development' else 'api.push.apple.com'
        try:
            with httpx.Client(http2=True, timeout=5) as client:
                response = client.post(f'https://{host}/3/device/{device.token}', json={'aps': {'content-available': 1}, **data}, headers={
                    'authorization': f'bearer {bearer}', 'apns-topic': f'{settings.MOBILE_IOS_BUNDLE_ID}.voip',
                    'apns-push-type': 'voip', 'apns-priority': '10', 'apns-expiration': str(int(data['expires_at'])),
                })
            if response.status_code == 200:
                if device.expo_token: delivered.add(device.expo_token)
            elif response.status_code == 410:
                device.delete()
            else:
                logger.warning('APNs call delivery failed with status %s for device record %s.', response.status_code, device.pk)
        except (httpx.HTTPError, OSError):
            logger.warning('APNs transport unavailable for device record %s.', device.pk)
    return delivered
