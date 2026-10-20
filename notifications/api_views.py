from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MobilePushToken, VoipPushToken
import re
from accounts.security import PushThrottle


class MobilePushTokenAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PushThrottle]

    def post(self, request):
        token = request.data.get("token")
        platform = request.data.get("platform")
        if (
            not isinstance(token, str)
            or len(token) > 255
            or not token.startswith(("ExponentPushToken[", "ExpoPushToken["))
            or not token.endswith("]")
        ):
            return Response(
                {"detail": "A valid Expo push token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if platform not in {"android", "ios"}:
            return Response(
                {"detail": "platform must be android or ios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rebinding a token prevents a previous account from receiving calls after
        # this device signs into a different account.
        MobilePushToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "platform": platform},
        )
        return Response({"registered": True}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        token = request.data.get("token")
        if not isinstance(token, str) or not token:
            return Response(
                {"detail": "token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        MobilePushToken.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VoipPushTokenAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PushThrottle]

    def post(self, request):
        token = request.data.get('token')
        environment = request.data.get('environment')
        expo_token = request.data.get('expo_token') or ''
        if not isinstance(expo_token, str) or len(expo_token) > 255:
            return Response({'detail': 'Invalid Expo token.'}, status=400)
        if not isinstance(token, str) or not re.fullmatch(r'[a-fA-F0-9]{64,512}', token) or len(token) % 2:
            return Response({'detail': 'A valid PushKit token is required.'}, status=400)
        if not isinstance(environment, str) or environment not in {'development', 'production'}:
            return Response({'detail': 'Invalid APNs environment.'}, status=400)
        if expo_token and not MobilePushToken.objects.filter(user=request.user, platform='ios', token=expo_token).exists():
            return Response({'detail': 'Register this device for notifications first.'}, status=400)
        VoipPushToken.objects.update_or_create(token=token.lower(), defaults={'user': request.user, 'environment': environment, 'expo_token': expo_token})
        return Response({'registered': True}, status=201)

    def delete(self, request):
        token = request.data.get('token')
        if not isinstance(token, str) or not token:
            return Response({'detail': 'token is required.'}, status=400)
        VoipPushToken.objects.filter(user=request.user, token=token.lower()).delete()
        return Response(status=204)
