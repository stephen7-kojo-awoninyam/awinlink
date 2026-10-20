from django.contrib.auth import login
import secrets
from urllib.parse import urlencode
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .tokens import AccountRefreshToken as RefreshToken

from .google_auth import GoogleAuthError, begin, complete, digest, exchange, private_response
from .models import GoogleAuthAttempt
from .security import GoogleThrottle
from .views import authentication_limit_response


def error_page(request, message, status=400):
    return render(request, "accounts/google.html", {"error": message}, status=status)


@private_response
@require_POST
def google_start(request):
    try:
        limited = authentication_limit_response(request, 'google')
        if limited is not None:
            return limited
        link = request.POST.get("link") == "true"
        if link and (not request.user.is_authenticated or not request.user.is_active or not request.user.check_password(request.POST.get("password", ""))):
            raise GoogleAuthError("Sign in and confirm your current Awinlink password before linking Google.")
        if request.user.is_authenticated and not link:
            return redirect("dashboard")
        attempt, url, _ = begin(link_user=request.user if link else None)
        request.session["google_state"] = attempt.state
        request.session.pop("google_verified", None)
        return redirect(url)
    except GoogleAuthError as exc:
        return error_page(request, str(exc))


@private_response
@require_GET
def google_callback(request):
    state = request.GET.get("state", "")
    attempt = GoogleAuthAttempt.objects.filter(state=state).first() if len(state) <= 64 else None
    if not attempt:
        return error_page(request, "Invalid Google sign-in. Start again.")
    if not attempt.mobile_secret_hash and request.session.get("google_state") != state:
        return error_page(request, "Google sign-in does not match this browser. Start again.")
    try:
        code = request.GET.get("code", "")
        if request.GET.get("error") or not code or len(code) > 4096:
            GoogleAuthAttempt.objects.filter(pk=attempt.pk, status="PENDING").update(status="FAILED", verifier="", nonce="")
            raise GoogleAuthError("Google sign-in was cancelled or denied. You can try again.")
        attempt = exchange(state, code)
        if not attempt.mobile_secret_hash:
            request.session.pop("google_state", None)
            request.session["google_verified"] = state
            return redirect("google_complete")
        handoff = secrets.token_urlsafe(32)
        GoogleAuthAttempt.objects.filter(pk=attempt.pk, status="VERIFIED").update(mobile_handoff_hash=digest(handoff))
    except GoogleAuthError as exc:
        if not attempt.mobile_secret_hash:
            return error_page(request, str(exc))
        handoff = ""
    # A handoff alone cannot redeem credentials: the app must also prove its private exchange secret.
    response = HttpResponse(status=302)
    response["Location"] = "awinlink://google-complete?" + urlencode({"handoff": handoff} if handoff else {"error": "cancelled"})
    return response


@private_response
def google_complete(request):
    if request.method not in {"GET", "POST"}:
        return HttpResponse(status=405)
    try:
        with transaction.atomic():
            attempt = GoogleAuthAttempt.objects.select_for_update().filter(state=request.session.get("google_verified", "")).first()
            if not attempt or attempt.mobile_secret_hash:
                raise GoogleAuthError("Start Google sign-in again in this browser.")
            if attempt.link_user_id and (not request.user.is_authenticated or request.user.pk != attempt.link_user_id):
                raise GoogleAuthError("Sign in to the original account before linking Google.")
            if not attempt.link_user_id and request.user.is_authenticated:
                raise GoogleAuthError("Sign out before signing in to another account.")
            # Completion is POST-only, including login; GET displays a confirmation or signup form.
            if request.method == "GET":
                from .google_auth import GoogleSignupForm
                from .models import GoogleIdentity
                if attempt.status != "VERIFIED" or attempt.expires_at <= timezone.now():
                    raise GoogleAuthError("This Google sign-in expired or was already used.")
                known = bool(attempt.link_user_id or GoogleIdentity.objects.filter(subject=attempt.claims["sub"]).exists())
                form = None if known else GoogleSignupForm(claims=attempt.claims, initial={
                    "first_name": attempt.claims.get("given_name", ""), "last_name": attempt.claims.get("family_name", "")})
                return render(request, "accounts/google.html", {"form": form, "ready": True, "linking": bool(attempt.link_user_id)})
            user, form = complete(attempt, request.POST)
            if form:
                return render(request, "accounts/google.html", {"form": form, "ready": True}, status=400)
        request.session.pop("google_verified", None)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        if user.role == "ATHLETE" and not getattr(getattr(user, "talent_profile", None), "talent_category", None):
            return redirect("select_talent_category")
        if user.role == "SCOUT" and not getattr(getattr(user, "scout_profile", None), "scout_category", None):
            return redirect("select_scout_category")
        if user.role == "COACH" and not getattr(getattr(user, "coach_profile", None), "coach_category", None):
            return redirect("select_coach_category")
        return redirect("dashboard")
    except (GoogleAuthError, IntegrityError) as exc:
        message = str(exc) if isinstance(exc, GoogleAuthError) else "This identity or username was just registered. Start again or use your existing sign-in."
        return error_page(request, message)


@private_response
@require_GET
def google_link(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return render(request, "accounts/google.html", {"linking_start": True})


@method_decorator(private_response, name="dispatch")
class GoogleMobileStart(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GoogleThrottle]

    def post(self, request):
        try:
            linking = request.data.get("link") is True
            if linking and (not request.user.is_authenticated or not request.user.is_active or not request.user.check_password(request.data.get("password", ""))):
                raise GoogleAuthError("Confirm your current Awinlink password before linking Google.")
            _, url, secret = begin(mobile=True, link_user=request.user if linking else None)
            return Response({"authorization_url": url, "exchange_secret": secret})
        except GoogleAuthError as exc:
            return Response({"detail": str(exc)}, status=400)


@method_decorator(private_response, name="dispatch")
class GoogleMobileComplete(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GoogleThrottle]

    def post(self, request):
        from api.serializers import UserSerializer
        secret = request.data.get("exchange_secret")
        if not isinstance(secret, str) or not 32 <= len(secret) <= 128:
            return Response({"detail": "Invalid Google exchange."}, status=400)
        signup = request.data.get("signup")
        if signup is not None and not isinstance(signup, dict):
            return Response({"detail": "Invalid signup details."}, status=400)
        try:
            with transaction.atomic():
                attempt = GoogleAuthAttempt.objects.select_for_update().filter(mobile_secret_hash=digest(secret)).first()
                if not attempt or attempt.expires_at <= timezone.now():
                    raise GoogleAuthError("Google sign-in expired. Start again.")
                if attempt.status in {"PENDING", "EXCHANGING"}:
                    return Response({"pending": True})
                handoff = request.data.get("handoff")
                if (not isinstance(handoff, str) or not 32 <= len(handoff) <= 128
                    or not attempt.mobile_handoff_hash or not secrets.compare_digest(digest(handoff), attempt.mobile_handoff_hash)):
                    raise GoogleAuthError("Google sign-in does not match this app session. Start again.")
                if attempt.link_user_id and (not request.user.is_authenticated or request.user.pk != attempt.link_user_id):
                    raise GoogleAuthError("Sign in to the original account before linking Google.")
                user, form = complete(attempt, signup)
                if form:
                    if signup is not None:
                        return Response({"errors": form.errors}, status=400)
                    return Response({"signup_required": True, "email": attempt.claims["email"]})
                refresh = RefreshToken.for_user(user)
                return Response({"user": UserSerializer(user).data, "access": str(refresh.access_token), "refresh": str(refresh)})
        except (GoogleAuthError, IntegrityError) as exc:
            message = str(exc) if isinstance(exc, GoogleAuthError) else "This identity or username was just registered. Start Google sign-in again."
            return Response({"detail": message}, status=400)
