from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MobilePushToken


class MobilePushTokenAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
