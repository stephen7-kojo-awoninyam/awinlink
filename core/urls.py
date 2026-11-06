from django.urls import path
from . import views
from .public_views import public_page
from .safety_views import child_safety_report
from accounts.login_views import SharedLimitLoginView

urlpatterns = [
    path('delete-account/sign-in/', SharedLimitLoginView.as_view(template_name='core/deletion_login.html', next_page='/delete-account/'), name='deletion_login'),
    path('privacy/', public_page, {'page': 'privacy'}, name='privacy'),
    path('terms/', public_page, {'page': 'terms'}, name='terms'),
    path('community-guidelines/', public_page, {'page': 'community-guidelines'}, name='community_guidelines'),
    path('child-safety/', public_page, {'page': 'child-safety'}, name='child_safety'),
    path('child-safety/report/', child_safety_report, name='child_safety_report'),
    path('support/', public_page, {'page': 'support'}, name='support'),
    path('delete-account/', public_page, {'page': 'delete-account'}, name='delete_account'),
    path("", views.home, name="home"),
    
    path("home_feed/",views.home_feed,name="home_feed"),
    
    path("explore/",views.explore,name="explore"),
]

