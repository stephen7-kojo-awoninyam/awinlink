"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("athletes/",include("athletes.urls")),
    path("search/",include("search.urls")),
    path("organizations/",include("organizations.urls")),
    path("talents/",include("talents.urls")),
    path("applications/",include("applications.urls")),
    path("onboarding/",include("onboarding.urls")),
    path("invitations/",include("invitations.urls")),
    path("messages/",include("messaging.urls")),
    path("notifications/",include("notifications.urls")),
    path("shortlists/",include("shortlists.urls")),
    path("portfolio/",include("portfolio.urls")),
    path("opportunities/", include("opportunities.urls")),  
    path("recruitment/",include("recruitment.urls")),
    path("connections/",include("connections.urls")),
    path("feed/",include("feed.urls")),   
    path("events/",include("events.urls")),
    path("learning/", include("learning.urls")),
    path("analytics/", include("analytics.urls")),
    path( "coaches/", include("coaches.urls") ),
    path("scouts/",include("scouts.urls")),
    path("api/", include("api.urls")),
    path("api/feed/",include("feed.urls_api")),
    path("api/messaging/",include("messaging.api_urls")),
    path("events/",include("events.api_urls")),
    path("api/learning/",include("learning.api_urls")),
    path("api/portfolio/",include("portfolio.api_urls")),
    path("api/domains/",include("domains.api_urls",namespace="domains_api")),
    path("api/scouts/",include("scouts.api_urls",namespace="scouts_api")),
    path("api/coaches/",include("coaches.api_urls",namespace="coaches_api")),
    path("sports/", include("sports.urls")),
    path("science-technology/",include("science_technology.urls")),
    path("arts/",include("art.urls")),
    path("others/",include("others.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)