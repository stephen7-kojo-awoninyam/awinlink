from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from . import recovery_views
from . import google_views


urlpatterns = [
path("google/start/", google_views.google_start, name="google_start"),
path("google/callback/", google_views.google_callback, name="google_callback"),
path("google/complete/", google_views.google_complete, name="google_complete"),
path("google/link/", google_views.google_link, name="google_link"),
# Registration, login and logout
path("register/", views.register, name="register"),
path("login/", views.user_login, name="login"),
path("logout/", views.user_logout, name="logout"),


# Password reset
path(
    "password-reset/",
    recovery_views.PasswordResetView.as_view(),
    name="password_reset",
),

path(
    "password-reset/done/",
    auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html",
    ),
    name="password_reset_done",
),

path(
    "reset/<uidb64>/<token>/",
    recovery_views.PasswordResetConfirmView.as_view(),
    name="password_reset_confirm",
),

path(
    "reset/done/",
    auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html",
    ),
    name="password_reset_complete",
),
path("loading/", views.loading_page, name="loading"),
path(
    "check-organization-username/",
    views.check_organization_username,
    name="check_organization_username",
),
path(
    "check-username/",
    views.check_username,
    name="check_username",
),

]
