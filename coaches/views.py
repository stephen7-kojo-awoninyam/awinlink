
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CoachProfile
from talents.models import TalentProfile
from .models import CoachProfile, CoachTalentView
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

from messaging.models import (
    Conversation,
    ConversationParticipant,
)

from .models import (
    CoachProfile,
    CoachTalentView,
    CoachTalentFollow,
    CoachTalentBookmark,
)


from messaging.models import (
    Conversation,
    ConversationParticipant,
    Message,
)
        

# Create your views here.



# =========================================================
# COACH PROFILE
# =========================================================

@login_required
def coach_profile(request):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can access the coach profile."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET OR CREATE PROFILE
    # -----------------------------------------------------

    profile, created = CoachProfile.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        "coaches/coach_profile.html",
        {
            "profile": profile,
        }
    )


# =========================================================
# EDIT COACH PROFILE
# =========================================================

@login_required
def edit_coach_profile(request):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can edit a coach profile."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET OR CREATE PROFILE
    # -----------------------------------------------------

    profile, created = CoachProfile.objects.get_or_create(
        user=request.user
    )

    # -----------------------------------------------------
    # UPDATE PROFILE
    # -----------------------------------------------------

    if request.method == "POST":

        profile.headline = request.POST.get(
            "headline",
            ""
        )

        profile.biography = request.POST.get(
            "biography",
            ""
        )

        profile.specialization = request.POST.get(
            "specialization",
            ""
        )

        profile.experience_level = request.POST.get(
            "experience_level",
            "BEGINNER"
        )

        profile.years_of_experience = request.POST.get(
            "years_of_experience",
            0
        ) or 0

        profile.country = request.POST.get(
            "country",
            ""
        )

        profile.city = request.POST.get(
            "city",
            ""
        )

        profile.certifications = request.POST.get(
            "certifications",
            ""
        )

        # -------------------------------------------------
        # SPORT
        # -------------------------------------------------

        sport_id = request.POST.get("sport")

        if sport_id:

            from sports.models import Sport

            profile.sport = get_object_or_404(
                Sport,
                id=sport_id
            )

        else:

            profile.sport = None

        # -------------------------------------------------
        # ORGANIZATION
        # -------------------------------------------------

        organization_id = request.POST.get(
            "organization"
        )

        if organization_id:

            from organizations.models import Organization

            profile.organization = get_object_or_404(
                Organization,
                id=organization_id
            )

        else:

            profile.organization = None

        # -------------------------------------------------
        # PROFILE PHOTO
        # -------------------------------------------------

        if request.FILES.get("profile_photo"):

            profile.profile_photo = request.FILES[
                "profile_photo"
            ]

        # -------------------------------------------------
        # COVER PHOTO
        # -------------------------------------------------

        if request.FILES.get("cover_photo"):

            profile.cover_photo = request.FILES[
                "cover_photo"
            ]

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------

        profile.save()

        messages.success(
            request,
            "Coach profile updated successfully."
        )

        return redirect(
            "coach_profile"
        )

    # -----------------------------------------------------
    # FORM OPTIONS
    # -----------------------------------------------------

    from sports.models import Sport
    from organizations.models import Organization

    sports = Sport.objects.all().order_by("name")

    organizations = Organization.objects.filter(
        status="ACTIVE"
    ).order_by("name")

    # -----------------------------------------------------
    # EXPERIENCE LEVEL OPTIONS
    # -----------------------------------------------------

    experience_levels = CoachProfile.EXPERIENCE_LEVELS

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "coaches/edit_coach_profile.html",
        {
            "profile": profile,
            "sports": sports,
            "organizations": organizations,
            "experience_levels": experience_levels,
        }
    )
    
    

# =========================================================
# COACH TALENT DIRECTORY
# =========================================================
@login_required
def coach_talent_directory(request):


    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can access the talent directory."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH PROFILE
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET TALENTS
    # -----------------------------------------------------

    talents = TalentProfile.objects.select_related(
        "user"
    ).all().order_by(
        "-verified",
        "user__first_name",
        "user__last_name"
    )

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:

        talents = talents.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__username__icontains=search)
            | Q(headline__icontains=search)
            | Q(biography__icontains=search)
            | Q(city__icontains=search)
            | Q(country__icontains=search)
        )

    # -----------------------------------------------------
    # SPORT FILTER
    # -----------------------------------------------------

    sport = request.GET.get(
        "sport",
        ""
    ).strip()

    if sport:

        talents = talents.filter(
            sport__id=sport
        )

    # -----------------------------------------------------
    # EXPERIENCE FILTER
    # -----------------------------------------------------

    experience_level = request.GET.get(
        "experience_level",
        ""
    ).strip()

    if experience_level:

        talents = talents.filter(
            experience_level=experience_level
        )

    # -----------------------------------------------------
    # SPORTS
    # -----------------------------------------------------

    from sports.models import Sport

    sports = Sport.objects.all().order_by(
        "name"
    )

    # -----------------------------------------------------
    # SAVED TALENTS
    # -----------------------------------------------------

    saved_talent_ids = set(
        CoachTalentBookmark.objects.filter(
            coach=coach
        ).values_list(
            "talent_id",
            flat=True
        )
    )

    # -----------------------------------------------------
    # FOLLOWED TALENTS
    # -----------------------------------------------------

    followed_talent_ids = set(
        CoachTalentFollow.objects.filter(
            coach=coach
        ).values_list(
            "talent_id",
            flat=True
        )
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "coaches/talent_directory.html",
        {
            "coach": coach,

            "talents": talents,

            "sports": sports,

            "search": search,

            "selected_sport": sport,

            "selected_experience": experience_level,

            "experience_levels": (
                TalentProfile.EXPERIENCE_LEVELS
            ),

            "saved_talent_ids": saved_talent_ids,

            "followed_talent_ids": followed_talent_ids,
        }
    )




# =========================================================
# VIEW TALENT PROFILE AS COACH
# =========================================================

@login_required
def coach_view_talent(request, talent_id):

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can view talents."
        )

        return redirect("home")

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    talent = get_object_or_404(
        TalentProfile.objects.select_related(
            "user"
        ),
        id=talent_id
    )

    # -----------------------------------------------------
    # RECORD PROFILE VIEW
    # -----------------------------------------------------

    CoachTalentView.objects.create(
        coach=coach,
        talent=talent
    )

    # -----------------------------------------------------
    # CHECK WHETHER ALREADY SAVED
    # -----------------------------------------------------

    is_saved = CoachTalentBookmark.objects.filter(
        coach=coach,
        talent=talent
    ).exists()
    
    bookmark = CoachTalentBookmark.objects.filter(
    coach=coach,
    talent=talent
    ).first()

    is_saved = bookmark is not None

    return render(
        request,
        "coaches/talent_detail.html",
        {
            "coach": coach,
            "talent": talent,
            "is_saved": is_saved,
            "bookmark": bookmark,
        }
    )





# =========================================================
# SAVED TALENTS
# =========================================================


@login_required
def saved_talents(request):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can access saved talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET SAVED TALENTS
    # -----------------------------------------------------

    saved_talents = (
        CoachTalentBookmark.objects
        .filter(
            coach=coach
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-updated_at"
        )
    )

    # -----------------------------------------------------
    # STATISTICS
    # -----------------------------------------------------

    total_saved = saved_talents.count()

    # -----------------------------------------------------
    # FOLLOWED TALENTS
    # -----------------------------------------------------

    followed_talent_ids = set(
        CoachTalentFollow.objects
        .filter(
            coach=coach
        )
        .values_list(
            "talent_id",
            flat=True
        )
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "coaches/saved_talents.html",
        {
            "coach": coach,
            "saved_talents": saved_talents,
            "total_saved": total_saved,
            "followed_talent_ids": followed_talent_ids,
        }
    )







# =========================================================
# REMOVE SAVED TALENT
# =========================================================

@login_required
def unsave_talent(request, talent_id):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can remove saved talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # ONLY POST
    # -----------------------------------------------------

    if request.method != "POST":

        return redirect(
            "coach_view_talent",
            talent_id=talent_id
        )

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # REMOVE BOOKMARK
    # -----------------------------------------------------

    deleted, _ = CoachTalentBookmark.objects.filter(
        coach=coach,
        talent_id=talent_id
    ).delete()

    if deleted:

        messages.success(
            request,
            "Talent removed from your saved talents."
        )

    else:

        messages.info(
            request,
            "This talent was not saved."
        )

    return redirect(
        "coach_view_talent",
        talent_id=talent_id
    )


# =========================================================
# START CONVERSATION WITH TALENT
# =========================================================

@login_required
def message_talent(request, talent_id):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can message talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # ONLY POST
    # -----------------------------------------------------

    if request.method != "POST":

        return redirect(
            "coach_view_talent",
            talent_id=talent_id
        )

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET TALENT
    # -----------------------------------------------------

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    talent_user = talent.user

    # -----------------------------------------------------
    # PREVENT SELF MESSAGE
    # -----------------------------------------------------

    if talent_user == request.user:

        messages.error(
            request,
            "You cannot message yourself."
        )

        return redirect(
            "coach_view_talent",
            talent_id=talent.id
        )

    # -----------------------------------------------------
    # FIND EXISTING COACH/TALENT CONVERSATION
    # -----------------------------------------------------

    conversation = (
        Conversation.objects
        .filter(
            opportunity__isnull=True,
            participants__user=request.user
        )
        .filter(
            participants__user=talent_user
        )
        .distinct()
        .first()
    )

    # -----------------------------------------------------
    # CREATE CONVERSATION IF NEEDED
    # -----------------------------------------------------

    if not conversation:

        with transaction.atomic():

            conversation = Conversation.objects.create()

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=request.user
            )

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=talent_user
            )

    # -----------------------------------------------------
    # OPEN CONVERSATION
    # -----------------------------------------------------

    return redirect(
        "messaging:conversation",
        conversation_id=conversation.id
    )




# =========================================================
# COACH ANALYTICS
# =========================================================

@login_required
def coach_analytics(request):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can access coach analytics."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH PROFILE
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # TALENT PROFILE VIEWS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # RECENT TALENT VIEWS
    # -----------------------------------------------------

    thirty_days_ago = (
        timezone.now()
        - timedelta(days=30)
    )

    recent_talent_views = talent_views.filter(
        viewed_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # TALENTS FOLLOWED
    # -----------------------------------------------------

    followed_talents = CoachTalentFollow.objects.filter(
        coach=coach
    )

    total_followed_talents = followed_talents.count()

    # -----------------------------------------------------
    # SAVED TALENTS
    # -----------------------------------------------------

    saved_talents = CoachTalentBookmark.objects.filter(
        coach=coach
    )

    total_saved_talents = saved_talents.count()

    # -----------------------------------------------------
    # SAVED TALENTS WITH NOTES
    # -----------------------------------------------------

    talents_with_notes = saved_talents.exclude(
        notes=""
    ).count()

    # -----------------------------------------------------
    # CONVERSATIONS
    # -----------------------------------------------------

    conversation_ids = (
        ConversationParticipant.objects
        .filter(
            user=request.user
        )
        .values_list(
            "conversation_id",
            flat=True
        )
    )

    total_conversations = Conversation.objects.filter(
        id__in=conversation_ids
    ).count()

    # -----------------------------------------------------
    # MESSAGES SENT
    # -----------------------------------------------------

    messages_sent = Message.objects.filter(
        sender=request.user,
        conversation_id__in=conversation_ids
    ).count()

    # -----------------------------------------------------
    # RECENT MESSAGES
    # -----------------------------------------------------

    recent_messages = Message.objects.filter(
        sender=request.user,
        conversation_id__in=conversation_ids,
        created_at__gte=thirty_days_ago
    ).count()

    # -----------------------------------------------------
    # ANALYTICS DATA
    # -----------------------------------------------------

    analytics = {

        # Talent discovery
        "total_talent_views":
            total_talent_views,

        "unique_talents_viewed":
            unique_talents_viewed,

        "recent_talent_views":
            recent_talent_views,

        # Talent tracking
        "total_followed_talents":
            total_followed_talents,

        "total_saved_talents":
            total_saved_talents,

        "talents_with_notes":
            talents_with_notes,

        # Communication
        "total_conversations":
            total_conversations,

        "messages_sent":
            messages_sent,

        "recent_messages":
            recent_messages,
    }

    # -----------------------------------------------------
    # RECENTLY VIEWED TALENTS
    # -----------------------------------------------------

    recent_views = (
        talent_views
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-viewed_at"
        )[:5]
    )

    # -----------------------------------------------------
    # RECENTLY SAVED TALENTS
    # -----------------------------------------------------

    recent_saved = (
        saved_talents
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-created_at"
        )[:5]
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "coaches/coach_analytics.html",
        {
            "coach": coach,
            "analytics": analytics,
            "recent_views": recent_views,
            "recent_saved": recent_saved,
        }
    )
    
    
# =========================================================
# SAVE TALENT
# =========================================================

@login_required
def save_talent(request, talent_id):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can save talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH PROFILE
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET TALENT
    # -----------------------------------------------------

    from talents.models import TalentProfile

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    # -----------------------------------------------------
    # SAVE TALENT
    # -----------------------------------------------------

    bookmark, created = CoachTalentBookmark.objects.get_or_create(
        coach=coach,
        talent=talent
    )

    if created:

        messages.success(
            request,
            "Talent saved successfully."
        )

    else:

        messages.info(
            request,
            "This talent is already saved."
        )

    # -----------------------------------------------------
    # RETURN TO TALENT PROFILE
    # -----------------------------------------------------

    return redirect(
        "talent_detail",
        talent_id=talent.id
    )




# =========================================================
# UPDATE SAVED TALENT NOTES
# =========================================================

@login_required
def update_saved_talent_notes(
    request,
    bookmark_id
):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can update saved talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET BOOKMARK
    # -----------------------------------------------------

    bookmark = get_object_or_404(
        CoachTalentBookmark,
        id=bookmark_id,
        coach=coach
    )

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    if request.method == "POST":

        bookmark.notes = request.POST.get(
            "notes",
            ""
        )

        bookmark.save(
            update_fields=[
                "notes",
                "updated_at",
            ]
        )

        messages.success(
            request,
            "Talent notes updated successfully."
        )

    return redirect(
        "saved_talents"
    )


# =========================================================
# REMOVE SAVED TALENT
# =========================================================

@login_required
def remove_saved_talent(
    request,
    bookmark_id
):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can remove saved talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET BOOKMARK
    # -----------------------------------------------------

    bookmark = get_object_or_404(
        CoachTalentBookmark,
        id=bookmark_id,
        coach=coach
    )

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    bookmark.delete()

    messages.success(
        request,
        "Talent removed from saved talents."
    )

    return redirect(
        "saved_talents"
    )


# =========================================================
# FOLLOW / UNFOLLOW TALENT
# =========================================================

@login_required
def toggle_talent_follow(
    request,
    talent_id
):

    # -----------------------------------------------------
    # ONLY COACHES
    # -----------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can follow talents."
        )

        return redirect("home")

    # -----------------------------------------------------
    # GET COACH
    # -----------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -----------------------------------------------------
    # GET TALENT
    # -----------------------------------------------------

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    # -----------------------------------------------------
    # CHECK EXISTING FOLLOW
    # -----------------------------------------------------

    follow = CoachTalentFollow.objects.filter(
        coach=coach,
        talent=talent
    ).first()

    # -----------------------------------------------------
    # UNFOLLOW
    # -----------------------------------------------------

    if follow:

        follow.delete()

        messages.success(
            request,
            "You are no longer following this talent."
        )

    # -----------------------------------------------------
    # FOLLOW
    # -----------------------------------------------------

    else:

        CoachTalentFollow.objects.create(
            coach=coach,
            talent=talent
        )

        messages.success(
            request,
            "You are now following this talent."
        )

    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    return redirect(
        "talent_detail",
        talent_id=talent.id
    )


    

# =====================================================
# FOLLOW TALENT
# =====================================================

@login_required
def follow_talent(request, talent_id):

    # -------------------------------------------------
    # ONLY COACHES
    # -------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can follow talents."
        )

        return redirect("home")

    # -------------------------------------------------
    # GET COACH
    # -------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -------------------------------------------------
    # GET TALENT
    # -------------------------------------------------

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    # -------------------------------------------------
    # FOLLOW
    # -------------------------------------------------

    CoachTalentFollow.objects.get_or_create(
        coach=coach,
        talent=talent
    )

    messages.success(
        request,
        "Talent followed successfully."
    )

    return redirect("saved_talents")


# =====================================================
# UNFOLLOW TALENT
# =====================================================

@login_required
def unfollow_talent(request, talent_id):

    # -------------------------------------------------
    # ONLY COACHES
    # -------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can unfollow talents."
        )

        return redirect("home")

    # -------------------------------------------------
    # GET COACH
    # -------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -------------------------------------------------
    # GET TALENT
    # -------------------------------------------------

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    # -------------------------------------------------
    # REMOVE FOLLOW
    # -------------------------------------------------

    CoachTalentFollow.objects.filter(
        coach=coach,
        talent=talent
    ).delete()

    messages.success(
        request,
        "Talent unfollowed."
    )

    return redirect("saved_talents")


# =====================================================
# UPDATE TALENT PRIVATE NOTES
# =====================================================

@login_required
def update_talent_note(request, talent_id):

    # -------------------------------------------------
    # ONLY COACHES
    # -------------------------------------------------

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can manage talent notes."
        )

        return redirect("home")

    # -------------------------------------------------
    # GET COACH
    # -------------------------------------------------

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )

    # -------------------------------------------------
    # GET SAVED TALENT
    # -------------------------------------------------

    bookmark = get_object_or_404(
        CoachTalentBookmark,
        coach=coach,
        talent_id=talent_id
    )

    # -------------------------------------------------
    # UPDATE NOTE
    # -------------------------------------------------

    if request.method == "POST":

        bookmark.notes = request.POST.get(
            "notes",
            ""
        ).strip()

        bookmark.save(
            update_fields=[
                "notes",
                "updated_at"
            ]
        )

        messages.success(
            request,
            "Private note updated successfully."
        )

    return redirect("saved_talents")





# =====================================================

# COACH TALENT DIRECTORY

# =====================================================

@login_required
def coach_talent_directory(request):


    # ==========================================
    # ONLY COACHES
    # ==========================================

    if request.user.role != "COACH":

        messages.error(
            request,
            "Only coaches can access the talent directory."
        )

        return redirect("home")


    # ==========================================
    # GET COACH PROFILE
    # ==========================================

    coach = get_object_or_404(
        CoachProfile,
        user=request.user
    )


    # ==========================================
    # GET TALENTS
    # ==========================================

    talents = (
        TalentProfile.objects
        .select_related("user")
        .prefetch_related(
            "skills",
            "domains"
        )
        .all()
    )


    # ==========================================
    # SEARCH
    # ==========================================

    search_query = request.GET.get(
        "q",
        ""
    ).strip()


    if search_query:

        talents = talents.filter(

            Q(user__username__icontains=search_query)
            |
            Q(user__first_name__icontains=search_query)
            |
            Q(user__last_name__icontains=search_query)
            |
            Q(headline__icontains=search_query)
            |
            Q(biography__icontains=search_query)
            |
            Q(country__icontains=search_query)
            |
            Q(city__icontains=search_query)
            |
            Q(skills__name__icontains=search_query)
            |
            Q(domains__name__icontains=search_query)

        ).distinct()


    # ==========================================
    # GET SAVED TALENTS
    # ==========================================

    saved_talent_ids = set(

        CoachTalentBookmark.objects.filter(
            coach=coach
        ).values_list(
            "talent_id",
            flat=True
        )

    )


    # ==========================================
    # GET FOLLOWED TALENTS
    # ==========================================

    followed_talent_ids = set(

        CoachTalentFollow.objects.filter(
            coach=coach
        ).values_list(
            "talent_id",
            flat=True
        )

    )


    # ==========================================
    # PREPARE TALENTS
    # ==========================================

    for talent in talents:

        talent.is_saved = (
            talent.id in saved_talent_ids
        )

        talent.is_followed = (
            talent.id in followed_talent_ids
        )


    # ==========================================
    # STATISTICS
    # ==========================================

    total_talents = talents.count()


    # ==========================================
    # RENDER
    # ==========================================

    return render(
        request,
        "coaches/talent_directory.html",
        {
            "coach": coach,
            "talents": talents,
            "search_query": search_query,
            "total_talents": total_talents,
        }
    )




    




