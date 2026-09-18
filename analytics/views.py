from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.utils import timezone
from datetime import timedelta

from talents.models import TalentProfile

from applications.models import Application
from shortlists.models import Shortlist
from django.contrib.auth import get_user_model
from opportunities.models import Opportunity
from organizations.models import Organization
from talents.models import TalentProfile
from .models import (
    TalentScore,
    TalentProfileView,
    RecommendationHistory,
)

from .services import TalentCalculator
from django.db.models import Avg, Count

from coaches.models import (
    CoachProfile,
    CoachTalentView,
    CoachTalentFollow,
    CoachTalentBookmark,
)

from scouts.models import (
    ScoutProfile,
    ScoutTalentView,
    ScoutTalentFollow,
    ScoutTalentBookmark,
)







User = get_user_model()


# =========================================================
# TALENT ANALYTICS DASHBOARD
# =========================================================

@login_required
def talent_analytics(request):
    
    if request.user.role != "ATHLETE":
        return render(
            request,
            "analytics/access_denied.html"
        )

    # -----------------------------------------------------
    # GET TALENT PROFILE
    # -----------------------------------------------------

    talent = TalentProfile.objects.filter(
        user=request.user
    ).first()

    if not talent:

        return render(
            request,
            "analytics/talent_analytics.html",
            {
                "talent": None,
                "analytics": {},
                "score": None,
            }
        )

    # -----------------------------------------------------
    # UPDATE TALENT SCORE
    # -----------------------------------------------------

    score = TalentCalculator.update_score(
        talent
    )

    # -----------------------------------------------------
    # PROFILE VIEWS
    # -----------------------------------------------------

    profile_views_queryset = TalentProfileView.objects.filter(
        talent=talent
    )

    profile_views = profile_views_queryset.count()

    # -----------------------------------------------------
    # UNIQUE ORGANIZATIONS
    # -----------------------------------------------------

    organizations_interested = (
        profile_views_queryset
        .values("organization")
        .distinct()
        .count()
    )

    # -----------------------------------------------------
    # RECENT PROFILE VIEWS
    # -----------------------------------------------------

    thirty_days_ago = timezone.now() - timedelta(days=30)

    recent_profile_views = profile_views_queryset.filter(
        viewed_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # RECOMMENDATIONS
    # -----------------------------------------------------

    recommendations = RecommendationHistory.objects.filter(
        talent=talent
    )

    total_recommendations = recommendations.count()

    average_recommendation_score = (
        recommendations.aggregate(
            average=Avg("score")
        )["average"] or 0
    )

    average_recommendation_score = round(
        average_recommendation_score,
        2
    )

    # -----------------------------------------------------
    # HIGH QUALITY MATCHES
    # -----------------------------------------------------

    strong_matches = recommendations.filter(
        score__gte=70
    ).count()

    excellent_matches = recommendations.filter(
        score__gte=80
    ).count()

    # -----------------------------------------------------
    # APPLICATIONS
    # -----------------------------------------------------

    applications = talent.applications.all()

    total_applications = applications.count()

    accepted_applications = applications.filter(
        status="ACCEPTED"
    ).count()

    rejected_applications = applications.filter(
        status="REJECTED"
    ).count()

    pending_applications = applications.filter(
        status="PENDING"
    ).count()

    reviewing_applications = applications.filter(
        status="REVIEWING"
    ).count()

    # -----------------------------------------------------
    # APPLICATION SUCCESS RATE
    # -----------------------------------------------------

    success_rate = 0

    if total_applications:

        success_rate = round(
            (
                accepted_applications
                / total_applications
            ) * 100
        )

    # -----------------------------------------------------
    # APPLICATION RESPONSE RATE
    # -----------------------------------------------------

    processed_applications = (
        accepted_applications
        + rejected_applications
    )

    response_rate = 0

    if total_applications:

        response_rate = round(
            (
                processed_applications
                / total_applications
            ) * 100
        )

    # -----------------------------------------------------
    # PROFILE VISIBILITY SCORE
    # -----------------------------------------------------

    profile_visibility = 0

    if profile_views >= 20:
        profile_visibility = 100

    elif profile_views >= 10:
        profile_visibility = 75

    elif profile_views >= 5:
        profile_visibility = 50

    elif profile_views > 0:
        profile_visibility = 25

    # -----------------------------------------------------
    # ANALYTICS DATA
    # -----------------------------------------------------

    analytics = {

        # Profile
        "profile_views": profile_views,

        "unique_organizations": (
            organizations_interested
        ),

        "recent_profile_views": (
            recent_profile_views
        ),

        "profile_visibility": (
            profile_visibility
        ),

        # Applications
        "total_applications": (
            total_applications
        ),

        "accepted_applications": (
            accepted_applications
        ),

        "rejected_applications": (
            rejected_applications
        ),

        "pending_applications": (
            pending_applications
        ),

        "reviewing_applications": (
            reviewing_applications
        ),

        "success_rate": success_rate,

        "response_rate": response_rate,

        # Recommendations
        "total_recommendations": (
            total_recommendations
        ),

        "average_recommendation_score": (
            average_recommendation_score
        ),

        "strong_matches": (
            strong_matches
        ),

        "excellent_matches": (
            excellent_matches
        ),
    }

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "analytics/talent_analytics.html",
        {
            "talent": talent,
            "score": score,
            "analytics": analytics,
        }
    )
    
    
    
# =========================================================
# ORGANIZATION ANALYTICS DASHBOARD
# =========================================================
@login_required
def organization_analytics(request):

    # =====================================================
    # ACCESS CONTROL
    # =====================================================

    if request.user.role != "ORGANIZATION":

        return render(
            request,
            "analytics/access_denied.html"
        )

    # =====================================================
    # GET ORGANIZATION
    # =====================================================

    organization = getattr(
        request.user,
        "organization_profile",
        None
    )

    # =====================================================
    # ORGANIZATION DOES NOT EXIST
    # =====================================================

    if not organization:

        return render(
            request,
            "analytics/organization_analytics.html",
            {
                "organization": None,
                "analytics": {},
            }
        )

    # =====================================================
    # DATE RANGE
    # =====================================================

    thirty_days_ago = (
        timezone.now()
        - timedelta(days=30)
    )

    # =====================================================
    # OPPORTUNITIES
    # =====================================================

    opportunities = organization.opportunities.all()

    total_opportunities = opportunities.count()

    active_opportunities = opportunities.filter(
        active=True
    ).count()

    inactive_opportunities = opportunities.filter(
        active=False
    ).count()

    # =====================================================
    # APPLICATIONS
    # =====================================================

    applications = Application.objects.filter(
        opportunity__organization=organization
    )

    total_applications = applications.count()

    pending_applications = applications.filter(
        status="PENDING"
    ).count()

    reviewing_applications = applications.filter(
        status="REVIEWING"
    ).count()

    accepted_applications = applications.filter(
        status="ACCEPTED"
    ).count()

    rejected_applications = applications.filter(
        status="REJECTED"
    ).count()

    # =====================================================
    # UNIQUE TALENTS
    # =====================================================

    unique_talents = (
        applications
        .values("talent")
        .distinct()
        .count()
    )

    # =====================================================
    # APPLICATION SUCCESS RATE
    # =====================================================

    success_rate = 0

    if total_applications:

        success_rate = round(
            (
                accepted_applications
                / total_applications
            ) * 100
        )

    # =====================================================
    # APPLICATION RESPONSE RATE
    # =====================================================

    processed_applications = (
        accepted_applications
        + rejected_applications
    )

    response_rate = 0

    if total_applications:

        response_rate = round(
            (
                processed_applications
                / total_applications
            ) * 100
        )

    # =====================================================
    # SHORTLISTS
    # =====================================================

    shortlists = Shortlist.objects.filter(
        organization=organization
    )

    total_shortlisted = shortlists.count()

    starred_talents = shortlists.filter(
        starred=True
    ).count()

    # =====================================================
    # SHORTLIST RATE
    # =====================================================

    shortlist_rate = 0

    if unique_talents:

        shortlist_rate = round(
            (
                total_shortlisted
                / unique_talents
            ) * 100
        )

    # =====================================================
    # SHORTLISTED TALENTS WHO APPLIED
    # =====================================================

    shortlisted_applicants = (
        applications
        .filter(
            talent__shortlisted_by__organization=organization
        )
        .values("talent")
        .distinct()
        .count()
    )

    # =====================================================
    # TALENT PROFILE VIEWS
    # =====================================================

    profile_views = TalentProfileView.objects.filter(
        organization=organization
    )

    total_profile_views = profile_views.count()

    unique_profiles_viewed = (
        profile_views
        .values("talent")
        .distinct()
        .count()
    )

    # =====================================================
    # MOST VIEWED TALENTS
    # =====================================================

    most_viewed = (
        profile_views
        .values("talent")
        .annotate(
            view_count=Count("id")
        )
        .order_by(
            "-view_count"
        )[:5]
    )

    most_viewed_ids = [
        item["talent"]
        for item in most_viewed
    ]

    most_viewed_queryset = (
        TalentProfile.objects
        .filter(
            id__in=most_viewed_ids
        )
        .select_related(
            "user",
            "talent_score"
        )
    )

    most_viewed_map = {
        talent.id: talent
        for talent in most_viewed_queryset
    }

    most_viewed_talents = []

    for item in most_viewed:

        talent = most_viewed_map.get(
            item["talent"]
        )

        if talent:

            talent.view_count = (
                item["view_count"]
            )

            most_viewed_talents.append(
                talent
            )

    # =====================================================
    # RECOMMENDATIONS
    # =====================================================

    recommendations = RecommendationHistory.objects.filter(
        organization=organization
    )

    total_recommendations = recommendations.count()

    average_match_score = (
        recommendations
        .aggregate(
            average=Avg("score")
        )["average"]
        or 0
    )

    average_match_score = round(
        average_match_score,
        2
    )

    strong_matches = recommendations.filter(
        score__gte=70
    ).count()

    excellent_matches = recommendations.filter(
        score__gte=80
    ).count()

    # =====================================================
    # TOP RECOMMENDED TALENTS
    # =====================================================

    top_recommendations = (
        recommendations
        .values("talent")
        .annotate(
            recommendation_count=Count("id"),
            average_score=Avg("score"),
        )
        .order_by(
            "-average_score",
            "-recommendation_count"
        )[:5]
    )

    top_talent_ids = [
        item["talent"]
        for item in top_recommendations
    ]

    top_talents_queryset = (
        TalentProfile.objects
        .filter(
            id__in=top_talent_ids
        )
        .select_related(
            "user",
            "talent_score"
        )
    )

    top_talents_map = {
        talent.id: talent
        for talent in top_talents_queryset
    }

    top_discovered_talents = []

    for item in top_recommendations:

        talent = top_talents_map.get(
            item["talent"]
        )

        if talent:

            talent.recommendation_count = (
                item["recommendation_count"]
            )

            talent.average_match_score = round(
                item["average_score"],
                2
            )

            top_discovered_talents.append(
                talent
            )

    # =====================================================
    # LAST 30 DAYS ANALYTICS
    # =====================================================

    recent_applications_count = (
        applications
        .filter(
            created_at__gte=thirty_days_ago
        )
        .count()
    )

    recent_recommendations_count = (
        recommendations
        .filter(
            created_at__gte=thirty_days_ago
        )
        .count()
    )

    recent_profile_views_count = (
        profile_views
        .filter(
            viewed_at__gte=thirty_days_ago
        )
        .count()
    )

    recent_shortlists_count = (
        shortlists
        .filter(
            created_at__gte=thirty_days_ago
        )
        .count()
    )

    recent_opportunities_count = (
        opportunities
        .filter(
            created_at__gte=thirty_days_ago
        )
        .count()
    )

    # =====================================================
    # RECENT APPLICATIONS
    # =====================================================

    recent_applications = (
        applications
        .select_related(
            "talent",
            "opportunity"
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # =====================================================
    # RECENT RECOMMENDATIONS
    # =====================================================

    recent_recommendations = (
        recommendations
        .select_related(
            "talent",
            "opportunity"
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # =====================================================
    # ANALYTICS DATA
    # =====================================================

    analytics = {

        # -------------------------------------------------
        # OPPORTUNITIES
        # -------------------------------------------------

        "total_opportunities":
            total_opportunities,

        "active_opportunities":
            active_opportunities,

        "inactive_opportunities":
            inactive_opportunities,

        # -------------------------------------------------
        # APPLICATIONS
        # -------------------------------------------------

        "total_applications":
            total_applications,

        "pending_applications":
            pending_applications,

        "reviewing_applications":
            reviewing_applications,

        "accepted_applications":
            accepted_applications,

        "rejected_applications":
            rejected_applications,

        "success_rate":
            success_rate,

        "response_rate":
            response_rate,

        "unique_talents":
            unique_talents,

        # -------------------------------------------------
        # SHORTLISTS
        # -------------------------------------------------

        "total_shortlisted":
            total_shortlisted,

        "starred_talents":
            starred_talents,

        "shortlist_rate":
            shortlist_rate,

        "shortlisted_applicants":
            shortlisted_applicants,

        # -------------------------------------------------
        # AI RECOMMENDATIONS
        # -------------------------------------------------

        "total_recommendations":
            total_recommendations,

        "average_match_score":
            average_match_score,

        "strong_matches":
            strong_matches,

        "excellent_matches":
            excellent_matches,

        # -------------------------------------------------
        # TALENT DISCOVERY
        # -------------------------------------------------

        "total_profile_views":
            total_profile_views,

        "unique_profiles_viewed":
            unique_profiles_viewed,

        # -------------------------------------------------
        # LAST 30 DAYS
        # -------------------------------------------------

        "recent_applications":
            recent_applications_count,

        "recent_recommendations":
            recent_recommendations_count,

        "recent_profile_views":
            recent_profile_views_count,

        "recent_shortlists":
            recent_shortlists_count,

        "recent_opportunities":
            recent_opportunities_count,
    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "analytics/organization_analytics.html",
        {
            "organization":
                organization,

            "analytics":
                analytics,

            "top_discovered_talents":
                top_discovered_talents,

            "most_viewed_talents":
                most_viewed_talents,

            "recent_applications":
                recent_applications,

            "recent_recommendations":
                recent_recommendations,
        }
    )
    
    




# =========================================================
# ADMIN ANALYTICS DASHBOARD
# =========================================================

@login_required
def admin_analytics(request):

    # -----------------------------------------------------
    # ADMIN ACCESS
    # -----------------------------------------------------

    if request.user.role != "ADMIN":

        return render(
            request,
            "analytics/access_denied.html"
        )

    # -----------------------------------------------------
    # DATE RANGE
    # -----------------------------------------------------

    thirty_days_ago = timezone.now() - timedelta(days=30)

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    total_users = User.objects.count()

    total_talents = TalentProfile.objects.count()

    total_organizations = Organization.objects.count()

    # -----------------------------------------------------
    # OPPORTUNITIES
    # -----------------------------------------------------

    total_opportunities = Opportunity.objects.count()

    active_opportunities = Opportunity.objects.filter(
        active=True
    ).count()

    # -----------------------------------------------------
    # APPLICATIONS
    # -----------------------------------------------------

    total_applications = Application.objects.count()

    accepted_applications = Application.objects.filter(
        status="ACCEPTED"
    ).count()

    pending_applications = Application.objects.filter(
        status="PENDING"
    ).count()

    reviewing_applications = Application.objects.filter(
        status="REVIEWING"
    ).count()

    rejected_applications = Application.objects.filter(
        status="REJECTED"
    ).count()

    # -----------------------------------------------------
    # APPLICATION SUCCESS RATE
    # -----------------------------------------------------

    application_success_rate = 0

    if total_applications:

        application_success_rate = round(
            (
                accepted_applications
                / total_applications
            ) * 100
        )

    # -----------------------------------------------------
    # PROFILE VIEWS
    # -----------------------------------------------------

    total_profile_views = TalentProfileView.objects.count()

    # -----------------------------------------------------
    # RECOMMENDATIONS
    # -----------------------------------------------------

    total_recommendations = (
        RecommendationHistory.objects.count()
    )

    # -----------------------------------------------------
    # SHORTLISTS
    # -----------------------------------------------------

    total_shortlists = 0

    try:

        total_shortlists = Shortlist.objects.count()

    except Exception:

        total_shortlists = 0

    # -----------------------------------------------------
    # TALENT SCORES
    # -----------------------------------------------------

    scored_talents = TalentScore.objects.count()

    average_talent_score = 0

    if scored_talents:

        scores = TalentScore.objects.values_list(
            "overall_score",
            flat=True
        )

        average_talent_score = round(
            sum(scores) / scored_talents,
            2
        )

    # =====================================================
    # LAST 30 DAYS ANALYTICS
    # =====================================================

    # -----------------------------------------------------
    # NEW USERS
    # -----------------------------------------------------

    new_users_30_days = User.objects.filter(
        date_joined__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW TALENTS
    # -----------------------------------------------------
    #
    # We use the users created during the period whose
    # role is ATHLETE because TalentProfile does not need
    # to have a separate timestamp for this metric.
    #

    new_talents_30_days = User.objects.filter(
        role="ATHLETE",
        date_joined__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW ORGANIZATIONS
    # -----------------------------------------------------

    new_organizations_30_days = Organization.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW OPPORTUNITIES
    # -----------------------------------------------------

    new_opportunities_30_days = Opportunity.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW APPLICATIONS
    # -----------------------------------------------------

    new_applications_30_days = Application.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW PROFILE VIEWS
    # -----------------------------------------------------

    new_profile_views_30_days = TalentProfileView.objects.filter(
        viewed_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # NEW RECOMMENDATIONS
    # -----------------------------------------------------

    new_recommendations_30_days = (
        RecommendationHistory.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()
    )

    # -----------------------------------------------------
    # NEW SHORTLISTS
    # -----------------------------------------------------

    new_shortlists_30_days = Shortlist.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()

    # =====================================================
    # ANALYTICS DATA
    # =====================================================

    analytics = {

        # -------------------------------------------------
        # PLATFORM TOTALS
        # -------------------------------------------------

        "total_users":
            total_users,

        "total_talents":
            total_talents,

        "total_organizations":
            total_organizations,

        "total_opportunities":
            total_opportunities,

        "active_opportunities":
            active_opportunities,

        # -------------------------------------------------
        # APPLICATIONS
        # -------------------------------------------------

        "total_applications":
            total_applications,

        "accepted_applications":
            accepted_applications,

        "pending_applications":
            pending_applications,

        "reviewing_applications":
            reviewing_applications,

        "rejected_applications":
            rejected_applications,

        "application_success_rate":
            application_success_rate,

        # -------------------------------------------------
        # DISCOVERY / AI
        # -------------------------------------------------

        "total_profile_views":
            total_profile_views,

        "total_recommendations":
            total_recommendations,

        "total_shortlists":
            total_shortlists,

        "scored_talents":
            scored_talents,

        "average_talent_score":
            average_talent_score,

        # -------------------------------------------------
        # LAST 30 DAYS
        # -------------------------------------------------

        "new_users_30_days":
            new_users_30_days,

        "new_talents_30_days":
            new_talents_30_days,

        "new_organizations_30_days":
            new_organizations_30_days,

        "new_opportunities_30_days":
            new_opportunities_30_days,

        "new_applications_30_days":
            new_applications_30_days,

        "new_profile_views_30_days":
            new_profile_views_30_days,

        "new_recommendations_30_days":
            new_recommendations_30_days,

        "new_shortlists_30_days":
            new_shortlists_30_days,
    }

    # =====================================================
    # RECENT DATA
    # =====================================================

    recent_users = User.objects.order_by(
        "-date_joined"
    )[:5]

    recent_opportunities = Opportunity.objects.select_related(
        "organization"
    ).order_by(
        "-created_at"
    )[:5]

    recent_applications = Application.objects.select_related(
        "talent",
        "opportunity"
    ).order_by(
        "-created_at"
    )[:5]

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "analytics/admin_analytics.html",
        {
            "analytics": analytics,
            "recent_users": recent_users,
            "recent_opportunities": recent_opportunities,
            "recent_applications": recent_applications,
        }
    )

    


# =========================================================
# ANALYTICS DASHBOARD
# =========================================================

@login_required
def analytics_dashboard(request):

    role = request.user.role

    # ATHLETE
    if role == "ATHLETE":
        return redirect("analytics:talent_analytics")

    # ORGANIZATION
    if role == "ORGANIZATION":
        return redirect("analytics:organization_analytics")

    # COACH
    if role == "COACH":
        return redirect("analytics:coach_analytics")

    # SCOUT
    if role == "SCOUT":
        return redirect("analytics:scout_analytics")

    # ADMIN
    if role == "ADMIN":
        return redirect("analytics:admin_analytics")

    return render(
        request,
        "analytics/access_denied.html"
    )
    
    
    
# =========================================================
# COACH ANALYTICS DASHBOARD
# =========================================================

@login_required
def coach_analytics(request):

    # =====================================================
    # ACCESS CONTROL
    # =====================================================

    if request.user.role != "COACH":

        return render(
            request,
            "analytics/access_denied.html"
        )

    # =====================================================
    # GET COACH PROFILE
    # =====================================================

    coach = getattr(
        request.user,
        "coach_profile",
        None
    )

    if not coach:

        return render(
            request,
            "analytics/coach_analytics.html",
            {
                "coach": None,
                "analytics": {},
                "most_viewed_talents": [],
                "most_followed_talents": [],
                "most_bookmarked_talents": [],
                "recent_views": [],
                "recent_follows": [],
                "recent_bookmarks": [],
            }
        )

    # =====================================================
    # TALENT VIEWS
    # =====================================================

    talent_views = CoachTalentView.objects.filter(
        coach=coach
    )

    total_talent_views = talent_views.count()

    unique_talents_viewed = (
        talent_views
        .values("talent")
        .distinct()
        .count()
    )

    # =====================================================
    # FOLLOWED TALENTS
    # =====================================================

    followed_talents = CoachTalentFollow.objects.filter(
        coach=coach
    )

    total_followed_talents = followed_talents.count()

    # =====================================================
    # BOOKMARKED TALENTS
    # =====================================================

    bookmarked_talents = CoachTalentBookmark.objects.filter(
        coach=coach
    )

    total_bookmarked_talents = bookmarked_talents.count()

    # =====================================================
    # MOST VIEWED TALENTS
    # =====================================================

    most_viewed = (
        talent_views
        .values("talent")
        .annotate(
            view_count=Count("id")
        )
        .order_by(
            "-view_count"
        )[:5]
    )

    most_viewed_ids = [
        item["talent"]
        for item in most_viewed
    ]

    most_viewed_queryset = (
        TalentProfile.objects
        .filter(
            id__in=most_viewed_ids
        )
        .select_related(
            "user"
        )
    )

    most_viewed_map = {
        talent.id: talent
        for talent in most_viewed_queryset
    }

    most_viewed_talents = []

    for item in most_viewed:

        talent = most_viewed_map.get(
            item["talent"]
        )

        if talent:

            talent.view_count = (
                item["view_count"]
            )

            most_viewed_talents.append(
                talent
            )

    # =====================================================
    # MOST FOLLOWED TALENTS
    # =====================================================

    most_followed = (
        followed_talents
        .values("talent")
        .annotate(
            follow_count=Count("id")
        )
        .order_by(
            "-follow_count"
        )[:5]
    )

    most_followed_ids = [
        item["talent"]
        for item in most_followed
    ]

    most_followed_queryset = (
        TalentProfile.objects
        .filter(
            id__in=most_followed_ids
        )
        .select_related(
            "user"
        )
    )

    most_followed_map = {
        talent.id: talent
        for talent in most_followed_queryset
    }

    most_followed_talents = []

    for item in most_followed:

        talent = most_followed_map.get(
            item["talent"]
        )

        if talent:

            talent.follow_count = (
                item["follow_count"]
            )

            most_followed_talents.append(
                talent
            )

    # =====================================================
    # MOST BOOKMARKED TALENTS
    # =====================================================

    most_bookmarked = (
        bookmarked_talents
        .values("talent")
        .annotate(
            bookmark_count=Count("id")
        )
        .order_by(
            "-bookmark_count"
        )[:5]
    )

    most_bookmarked_ids = [
        item["talent"]
        for item in most_bookmarked
    ]

    most_bookmarked_queryset = (
        TalentProfile.objects
        .filter(
            id__in=most_bookmarked_ids
        )
        .select_related(
            "user"
        )
    )

    most_bookmarked_map = {
        talent.id: talent
        for talent in most_bookmarked_queryset
    }

    most_bookmarked_talents = []

    for item in most_bookmarked:

        talent = most_bookmarked_map.get(
            item["talent"]
        )

        if talent:

            talent.bookmark_count = (
                item["bookmark_count"]
            )

            most_bookmarked_talents.append(
                talent
            )

    # =====================================================
    # RECENT VIEWS
    # =====================================================

    recent_views = (
        talent_views
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-viewed_at"
        )[:10]
    )

    # =====================================================
    # RECENT FOLLOWS
    # =====================================================

    recent_follows = (
        followed_talents
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # =====================================================
    # RECENT BOOKMARKS
    # =====================================================

    recent_bookmarks = (
        bookmarked_talents
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # =====================================================
    # ANALYTICS DATA
    # =====================================================

    analytics = {

        "total_talent_views":
            total_talent_views,

        "unique_talents_viewed":
            unique_talents_viewed,

        "total_followed_talents":
            total_followed_talents,

        "total_bookmarked_talents":
            total_bookmarked_talents,

    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "analytics/coach_analytics.html",
        {
            "coach":
                coach,

            "analytics":
                analytics,

            "most_viewed_talents":
                most_viewed_talents,

            "most_followed_talents":
                most_followed_talents,

            "most_bookmarked_talents":
                most_bookmarked_talents,

            "recent_views":
                recent_views,

            "recent_follows":
                recent_follows,

            "recent_bookmarks":
                recent_bookmarks,
        }
    )    
    
    
    
# =========================================================
# SCOUT ANALYTICS DASHBOARD
# =========================================================

@login_required
def scout_analytics(request):

    if request.user.role != "SCOUT":

        return render(
            request,
            "analytics/access_denied.html"
        )

    scout = get_object_or_404(
        ScoutProfile,
        user=request.user
    )

    # =====================================================
    # TALENT VIEWS
    # =====================================================

    talent_views = ScoutTalentView.objects.filter(
        scout=scout
    )

    total_talent_views = talent_views.count()

    unique_talents_viewed = (
        talent_views
        .values("talent")
        .distinct()
        .count()
    )

    # =====================================================
    # FOLLOWED TALENTS
    # =====================================================

    followed_talents = ScoutTalentFollow.objects.filter(
        scout=scout
    )

    total_followed_talents = followed_talents.count()

    # =====================================================
    # BOOKMARKED TALENTS
    # =====================================================

    bookmarked_talents = ScoutTalentBookmark.objects.filter(
        scout=scout
    )

    total_bookmarked_talents = bookmarked_talents.count()

    # =====================================================
    # RECENT VIEWS
    # =====================================================

    recent_views = (
        talent_views
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by("-viewed_at")[:10]
    )

    # =====================================================
    # RECENT BOOKMARKS
    # =====================================================

    recent_bookmarks = (
        bookmarked_talents
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by("-created_at")[:10]
    )

    # =====================================================
    # MOST VIEWED TALENTS
    # =====================================================

    most_viewed_talents = (
        talent_views
        .values(
            "talent",
            "talent__user__username",
            "talent__user__first_name",
            "talent__user__last_name",
        )
        .annotate(
            view_count=Count("id")
        )
        .order_by(
            "-view_count"
        )[:5]
    )

    # =====================================================
    # ANALYTICS
    # =====================================================

    analytics = {

        "total_talent_views":
            total_talent_views,

        "unique_talents_viewed":
            unique_talents_viewed,

        "total_followed_talents":
            total_followed_talents,

        "total_bookmarked_talents":
            total_bookmarked_talents,
    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "analytics/scout_analytics.html",
        {
            "scout": scout,
            "analytics": analytics,
            "recent_views": recent_views,
            "recent_bookmarks": recent_bookmarks,
            "most_viewed_talents": most_viewed_talents,
        }
    )    