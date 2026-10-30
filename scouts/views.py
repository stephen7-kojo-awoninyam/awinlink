from accounts.roles import active_user_has_role
from talents.visibility import public_talent_profiles_for
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import models
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.utils import timezone
from talents.models import TalentProfile
from .forms import ScoutCategoryForm, ScoutProfileForm
from .models import (
    ScoutProfile,
    ScoutTalentView,
    ScoutTalentFollow,
    ScoutTalentBookmark,
)


# Create your views here.


# =========================================================
# SCOUT DASHBOARD
# =========================================================

@login_required
@never_cache
def scout_dashboard(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    total_views = ScoutTalentView.objects.filter(
        scout=scout,
        talent__in=public_talent_profiles_for(request.user),
    ).count()

    total_followed = ScoutTalentFollow.objects.filter(
        scout=scout,
        talent__in=public_talent_profiles_for(request.user),
    ).count()

    total_bookmarks = ScoutTalentBookmark.objects.filter(
        scout=scout,
        talent__in=public_talent_profiles_for(request.user),
    ).count()

    recent_views = (
        ScoutTalentView.objects
        .filter(
            scout=scout,
            talent__in=public_talent_profiles_for(request.user),
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by("-viewed_at")[:5]
    )

    recent_bookmarks = (
        ScoutTalentBookmark.objects
        .filter(
            scout=scout,
            talent__in=public_talent_profiles_for(request.user),
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by("-created_at")[:5]
    )

    return render(
        request,
        "dashboard/scout_dashboard.html",
        {
            "scout": scout,
            "total_views": total_views,
            "total_followed": total_followed,
            "total_bookmarks": total_bookmarks,
            "recent_views": recent_views,
            "recent_bookmarks": recent_bookmarks,
        }
    )


# =========================================================
# TALENT DETAIL
# =========================================================
@login_required
@never_cache
def scout_talent_detail(request, talent_id):

    if not active_user_has_role(request.user, "SCOUT"):

        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    talent = get_object_or_404(
        public_talent_profiles_for(request.user).select_related("user").prefetch_related(
            "domains",
            "skills",
        ),
        id=talent_id,
        profile_visibility="PUBLIC",
    )

    # =====================================================
    # RECORD PROFILE VIEW
    # =====================================================

    cooldown_time = timezone.now() - timedelta(minutes=30)

    recent_view = ScoutTalentView.objects.filter(
        scout=scout,
        talent=talent,
        viewed_at__gte=cooldown_time
    ).exists()

    if not recent_view:

        ScoutTalentView.objects.create(
            scout=scout,
            talent=talent
        )

    # =====================================================
    # FOLLOW STATUS
    # =====================================================

    is_following = ScoutTalentFollow.objects.filter(
        scout=scout,
        talent=talent
    ).exists()

    # =====================================================
    # BOOKMARK STATUS
    # =====================================================

    bookmark = ScoutTalentBookmark.objects.filter(
        scout=scout,
        talent=talent
    ).first()    
    return render(
        request,
        "scouts/talent_detail.html",
        {
            "scout": scout,
            "talent": talent,
            "is_following": is_following,
            "bookmark": bookmark,
        }
    )


# =========================================================
# FOLLOW TALENT
# =========================================================

@login_required
@require_POST
@never_cache
def follow_talent(request, talent_id):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    talent = get_object_or_404(
        public_talent_profiles_for(request.user),
        id=talent_id,
        profile_visibility="PUBLIC",
    )

    follow, created = ScoutTalentFollow.objects.get_or_create(
        scout=scout,
        talent=talent
    )

    if created:

        messages.success(
            request,
            "Talent followed successfully."
        )

    else:

        follow.delete()

        messages.success(
            request,
            "Talent unfollowed."
        )

    return redirect(
        "scout_talent_detail",
        talent_id=talent.id
    )


# =========================================================
# BOOKMARK TALENT
# =========================================================

@login_required
@require_POST
@never_cache
def bookmark_talent(request, talent_id):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    talent = get_object_or_404(
        public_talent_profiles_for(request.user),
        id=talent_id,
        profile_visibility="PUBLIC",
    )

    bookmark, created = ScoutTalentBookmark.objects.get_or_create(
        scout=scout,
        talent=talent
    )

    if created:

        messages.success(
            request,
            "Talent bookmarked successfully."
        )

    else:

        bookmark.delete()

        messages.success(
            request,
            "Talent removed from bookmarks."
        )

    return redirect(
        "scout_talent_detail",
        talent_id=talent.id
    )
    
    
    
# =========================================================
# REMOVE BOOKMARK
# =========================================================

@login_required
@require_POST
@never_cache
def remove_bookmark(request, talent_id):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout = get_object_or_404(
        ScoutProfile,
        user=request.user
    )

    ScoutTalentBookmark.objects.filter(
        scout=scout,
        talent_id=talent_id,
    ).delete()

    return redirect("scout_bookmarked_talents")
    
    
# =========================================================
# SAVED TALENTS
# =========================================================

@login_required
@never_cache
def saved_talents(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout = get_object_or_404(
        ScoutProfile,
        user=request.user
    )

    bookmarks = (
        ScoutTalentBookmark.objects
        .filter(
            scout=scout,
            talent__in=public_talent_profiles_for(request.user),
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "scouts/saved_talents.html",
        {
            "scout": scout,
            "bookmarks": bookmarks,
        }
    )   
    
    
# =========================================================
# SCOUT TALENT LIST
# =========================================================

@login_required
@never_cache
def scout_talent_list(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    # =====================================================
    # ALL TALENTS
    # =====================================================

    talents = public_talent_profiles_for(request.user).select_related(
        "user"
    ).prefetch_related(
        "domains",
        "skills"
    ).filter(
        profile_visibility="PUBLIC"
    ).order_by(
        "-verified",
        "user__username",
    )

    # =====================================================
    # SEARCH
    # =====================================================

    query = request.GET.get("q", "").strip()

    if query:

        talents = talents.filter(
            models.Q(
                user__username__icontains=query
            )
            |
            models.Q(
                user__first_name__icontains=query
            )
            |
            models.Q(
                user__last_name__icontains=query
            )
            |
            models.Q(
                headline__icontains=query
            )
            |
            models.Q(
                biography__icontains=query
            )
        )

    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    talents = talents.distinct()

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "scouts/talent_list.html",
        {
            "scout": scout,
            "talents": talents,
            "query": query,
        }
    )
    
    
# =========================================================
# SCOUT BOOKMARKED TALENTS
# =========================================================

@login_required
@never_cache
def scout_bookmarked_talents(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    bookmarks = (
        ScoutTalentBookmark.objects
        .filter(
            scout=scout,
            talent__in=public_talent_profiles_for(request.user),
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .prefetch_related(
            "talent__domains",
            "talent__skills"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "scouts/bookmarked_talents.html",
        {
            "scout": scout,
            "bookmarks": bookmarks,
        }
    )    
    
    
# =========================================================
# SCOUT FOLLOWED TALENTS
# =========================================================

@login_required
@never_cache
def scout_followed_talents(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    followed_talents = (
        ScoutTalentFollow.objects
        .filter(
            scout=scout,
            talent__in=public_talent_profiles_for(request.user),
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .prefetch_related(
            "talent__domains",
            "talent__skills"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "scouts/followed_talents.html",
        {
            "scout": scout,
            "followed_talents": followed_talents,
        }
    )   
    
    
# =========================================================
# UPDATE SCOUT TALENT BOOKMARK NOTES
# =========================================================

@login_required
@require_POST
@never_cache
def update_bookmark_notes(request, talent_id):

    if not active_user_has_role(request.user, "SCOUT"):

        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    talent = get_object_or_404(
        public_talent_profiles_for(request.user),
        id=talent_id,
        profile_visibility="PUBLIC",
    )

    bookmark = get_object_or_404(
        ScoutTalentBookmark,
        scout=scout,
        talent=talent
    )

    bookmark.notes = request.POST.get(
        "notes",
        ""
    ).strip()

    bookmark.save()

    messages.success(
        request,
        "Scouting notes saved successfully."
    )

    return redirect(
        "scout_talent_detail",
        talent_id=talent.id
    )  
    
    
@login_required
@never_cache
def select_scout_category(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout, created = ScoutProfile.objects.get_or_create(
        user=request.user
    )

    if scout.scout_category:
        return redirect("scout_dashboard")

    if request.method == "POST":

        form = ScoutCategoryForm(
            request.POST,
            instance=scout
        )

        if form.is_valid():
            form.save()

            return redirect("create_scout_profile")

    else:

        form = ScoutCategoryForm(
            instance=scout
        )

    return render(
        request,
        "scouts/select_category.html",
        {
            "form": form,
            "scout": scout,
        }
    ) 
    
    
@login_required
@never_cache
def create_scout_profile(request):

    if not active_user_has_role(request.user, "SCOUT"):
        return render(
            request,
            "analytics/access_denied.html"
        )

    scout = get_object_or_404(
        ScoutProfile,
        user=request.user
    )

    if not scout.scout_category:
        return redirect("select_scout_category")

    if request.method == "POST":

        form = ScoutProfileForm(
            request.POST,
            instance=scout
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Scout profile created successfully."
            )

            return redirect("scout_dashboard")

    else:

        form = ScoutProfileForm(
            instance=scout
        )

    return render(
        request,
        "scouts/create_profile.html",
        {
            "form": form,
            "scout": scout,
        }
    )       
     