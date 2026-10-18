from django.contrib.auth import get_user_model, logout
from collections.abc import Mapping
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from redis.exceptions import RedisError

from .models import ContentReport, UserBlock
from .recovery import RecoveryForm, RecoverySetPasswordForm, RecoveryUnavailable, allow_request, allow_confirmation, send_recovery, GENERIC_SENT, INVALID_LINK
from .recovery_views import PrivateRecoveryResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters


@method_decorator([never_cache, sensitive_post_parameters()], name='dispatch')
class PasswordResetRequest(PrivateRecoveryResponse, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        try:
            if not allow_request(request):
                return Response({'detail': 'Too many requests. Please try again later.'}, status=429, headers={'Retry-After': '3600'})
        except RecoveryUnavailable:
            return Response({'detail': 'Password recovery is temporarily unavailable. Please try again later.'}, status=503)
        if not isinstance(request.data, Mapping):
            return Response({'detail': 'Enter a valid email address.'}, status=400)
        form = RecoveryForm(request.data)
        if not form.is_valid():
            return Response(form.errors, status=400)
        try:
            send_recovery(form, mobile=True)
        except RecoveryUnavailable:
            return Response({'detail': 'Password recovery is temporarily unavailable. Please try again later.'}, status=503)
        return Response({'detail': GENERIC_SENT})


@method_decorator([never_cache, sensitive_post_parameters()], name='dispatch')
class PasswordResetConfirm(PrivateRecoveryResponse, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @transaction.atomic
    def post(self, request):
        try:
            if not allow_confirmation(request):
                return Response({'detail': 'Too many requests. Please try again later.'}, status=429, headers={'Retry-After': '900'})
        except RecoveryUnavailable:
            return Response({'detail': 'Password recovery is temporarily unavailable. Please try again later.'}, status=503)
        if not isinstance(request.data, Mapping):
            return Response({'detail': INVALID_LINK}, status=400)
        uid, token = request.data.get('uid'), request.data.get('token')
        if not isinstance(uid, str) or len(uid) > 64 or not isinstance(token, str) or len(token) > 128:
            return Response({'detail': INVALID_LINK}, status=400)
        try:
            user = get_user_model().objects.select_for_update().get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
        except (ValueError, TypeError, OverflowError, UnicodeDecodeError, get_user_model().DoesNotExist):
            user = None
        if not user or not user.has_usable_password() or not default_token_generator.check_token(user, token):
            return Response({'detail': INVALID_LINK}, status=400)
        if any(not isinstance(request.data.get(key), str) or len(request.data[key]) > 4096 for key in ('new_password1', 'new_password2')):
            return Response({'detail': 'Enter and confirm a valid new password.'}, status=400)
        form = RecoverySetPasswordForm(user, request.data)
        if not form.is_valid():
            return Response(form.errors, status=400)
        form.save()
        return Response({'detail': 'Password updated. Sign in with your new password.'})


class DeleteAccount(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request):
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        password = request.data.get('password')
        if not isinstance(password, str) or not user.check_password(password):
            return Response({'detail': 'Enter your current password.'}, status=400)
        # Organizations belong to their team. Require an explicit ownership decision.
        from organizations.models import Organization
        if Organization.objects.filter(user=user).exists():
            return Response({'detail': 'Transfer organization ownership before deleting your account.'}, status=409)
        user.delete()
        logout(request)
        return Response(status=204)


class BlockAccounts(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(list(UserBlock.objects.filter(user=request.user).values('blocked_user_id', 'blocked_user__username')))

    def post(self, request):
        serializer = BlockInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = get_object_or_404(get_user_model(), pk=serializer.validated_data['user_id'], is_active=True)
        if target.pk == request.user.pk:
            return Response({'detail': 'You cannot block yourself.'}, status=400)
        UserBlock.objects.get_or_create(user=request.user, blocked_user=target)
        from messaging.models import Call, CallParticipant
        from django.utils import timezone
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        calls = Call.objects.filter(conversation__participants__user=request.user, status__in=['RINGING', 'ACTIVE']).filter(conversation__participants__user=target).distinct()
        layer = get_channel_layer()
        for call in calls:
            call.status = 'ENDED'
            call.ended_at = timezone.now()
            call.save(update_fields=['status', 'ended_at'])
            CallParticipant.objects.filter(call=call).update(status='LEFT')
            if layer:
                try:
                    async_to_sync(layer.group_send)(f'call_{call.pk}', {'type': 'call_ended', 'ended_by': request.user.pk, 'ended_by_username': request.user.username})
                except (OSError, RedisError):
                    # Persist the block even when the signaling service is offline.
                    pass
        from connections.models import Follow, Connection
        from django.db.models import Q
        Follow.objects.filter(Q(follower=request.user, following=target) | Q(follower=target, following=request.user)).delete()
        Connection.objects.filter(Q(sender=request.user, receiver=target) | Q(sender=target, receiver=request.user)).delete()
        return Response({'blocked': True})

    def delete(self, request):
        serializer = BlockInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        UserBlock.objects.filter(user=request.user, blocked_user_id=serializer.validated_data['user_id']).delete()
        return Response(status=204)


class BlockInput(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class ReportInput(serializers.ModelSerializer):
    class Meta:
        model = ContentReport
        fields = ['target_type', 'target_id', 'reason', 'details']


class ReportContent(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReportInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['target_type'] == 'user':
            get_object_or_404(get_user_model(), pk=data['target_id'], is_active=True)
        elif data['target_type'] == 'post':
            from feed.models import Post
            from feed.api_views import PostDetailAPIView
            post = get_object_or_404(Post, pk=data['target_id'])
            if not PostDetailAPIView().can_view_post(request.user, post):
                return Response({'detail': 'Post unavailable.'}, status=404)
        else:
            from messaging.models import Message
            get_object_or_404(Message, pk=data['target_id'], conversation__participants__user=request.user)
        report = serializer.save(reporter=request.user)
        return Response({'id': report.pk, 'detail': 'Report submitted for review.'}, status=201)
