from django.contrib.auth import get_user_model, logout
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from redis.exceptions import RedisError

from .models import ContentReport, UserBlock


class RecoveryThrottle(SimpleRateThrottle):
    scope = 'mobile_recovery'
    rate = '5/hour'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class PasswordResetRequest(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RecoveryThrottle]

    def post(self, request):
        form = PasswordResetForm(request.data)
        if not form.is_valid():
            return Response(form.errors, status=400)
        form.save(request=request, use_https=request.is_secure(),
                  email_template_name='accounts/mobile_password_reset_email.txt',
                  subject_template_name='accounts/password_reset_subject.txt')
        return Response({'detail': 'If an active account matches, password reset instructions have been sent.'})


class PasswordResetConfirm(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RecoveryThrottle]

    def post(self, request):
        try:
            user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(request.data.get('uid', ''))), is_active=True)
        except (ValueError, TypeError, OverflowError, UnicodeDecodeError, get_user_model().DoesNotExist):
            user = None
        token = request.data.get('token')
        if not user or not isinstance(token, str) or not default_token_generator.check_token(user, token):
            return Response({'detail': 'This reset link is invalid or expired.'}, status=400)
        form = SetPasswordForm(user, request.data)
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
