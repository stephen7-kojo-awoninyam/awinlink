from django.db import models
from django.shortcuts import render,redirect,get_object_or_404
from analytics.models import TalentProfileView
from .models import TalentProfile
from opportunities.models import Opportunity
from recommendations.services import RecommendationEngine
from django.contrib.auth.decorators import login_required
from applications.models import Application
from invitations.models import Invitation
from messaging.models import Conversation
from notifications.models import Notification
from .services import ProfileStrengthService
from django.db.models import Q
from organizations.models import Organization
from shortlists.models import Shortlist
from analytics.models import RecommendationHistory
from .models import Experience
from .models import Certification,Achievement
from .forms import AchievementForm,TalentCategoryForm,ExperienceForm,CertificationForm,TalentProfileForm,VerificationRequestForm
from connections.models import Follow
from others.models import OtherTalentProfile
from science_technology.models import ScienceTechnologyTalentProfile
from sports.models import SportsTalentProfile
from art.models import ArtsTalentProfile
from others.forms import OtherTalentProfileForm
from science_technology.forms import ScienceTechnologyTalentProfileForm
from art.forms import ArtsTalentProfileForm
from sports.forms import SportsTalentProfileForm
from sports.models import (
    SportsTalentProfile,
    Sport,
    SportCategory,
)
# Create your views here.



@login_required
def talent_dashboard(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # =====================================
    # PROFILE STRENGTH
    # =====================================

    profile_strength = ProfileStrengthService.calculate_strength(
        talent
    )


    # =====================================
    # APPLICATIONS
    # =====================================

    applications = Application.objects.filter(
        talent=talent
    ).select_related(
        "opportunity",
        "opportunity__organization"
    ).order_by(
        "-created_at"
    )


    total_applications = applications.count()


    pending_applications = applications.filter(
        status="PENDING"
    ).count()


    accepted_applications = applications.filter(
        status="ACCEPTED"
    ).count()


    rejected_applications = applications.filter(
        status="REJECTED"
    ).count()


    # =====================================
    # CERTIFICATES
    # =====================================

    certificate_count = (
        talent.event_certificates.count()
    )


    # =====================================
    # INVITATIONS
    # =====================================

    invitations = Invitation.objects.filter(
        talent=talent
    ).select_related(
        "organization",
        "opportunity"
    ).order_by(
        "-created_at"
    )


    # =====================================
    # CONVERSATIONS
    # NEW GENERIC MESSAGING SYSTEM
    # =====================================

    conversations = Conversation.objects.filter(
        participants__user=request.user
    ).prefetch_related(
        "participants__user",
        "messages"
    ).distinct().order_by(
        "-updated_at"
    )


    # =====================================
    # UNREAD MESSAGES
    # =====================================

    unread_message_count = 0


    for conversation in conversations:

        unread_count = conversation.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).count()


        conversation.unread_count = unread_count


        unread_message_count += unread_count


    # =====================================
    # NOTIFICATIONS
    # =====================================

    notifications = Notification.objects.filter(
        user=request.user
    ).order_by(
        "-created_at"
    )[:5]


    # =====================================
    # RECOMMENDED OPPORTUNITIES
    # =====================================

    recommended_opportunities = []


    all_opportunities = Opportunity.objects.filter(
        active=True
    ).select_related(
        "organization",
        "domain"
    ).prefetch_related(
        "skills"
    )


    for opportunity in all_opportunities:

        score = RecommendationEngine.calculate_score(
            talent,
            opportunity
        )


        recommended_opportunities.append(

            {
                "opportunity": opportunity,
                "score": score
            }

        )


    # =====================================
    # SORT RECOMMENDATIONS
    # =====================================

    recommended_opportunities.sort(

        key=lambda x: x["score"],

        reverse=True

    )


    # =====================================
    # SHOW TOP 5
    # =====================================

    recommended_opportunities = (
        recommended_opportunities[:5]
    )


    # =====================================
    # RECENT APPLICATIONS
    # =====================================

    recent_applications = applications[:5]


    # =====================================
    # DASHBOARD
    # =====================================

    return render(

        request,

        "talents/dashboard.html",

        {

            "talent": talent,

            "profile_strength":
                profile_strength,

            "applications":
                applications,

            "recent_applications":
                recent_applications,

            "total_applications":
                total_applications,

            "pending_applications":
                pending_applications,

            "accepted_applications":
                accepted_applications,

            "rejected_applications":
                rejected_applications,

            "recommended_opportunities":
                recommended_opportunities,

            "invitations":
                invitations,

            "conversations":
                conversations,

            "unread_message_count":
                unread_message_count,

            "notifications":
                notifications,

            "certificate_count":
                certificate_count,

        }

    )
    
@login_required
def request_verification(request):

    # Only talent/athlete accounts can request verification
    if request.user.role != "ATHLETE":
        return redirect("dashboard")

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    if request.method == "POST":

        form = VerificationRequestForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            verification = form.save(
                commit=False
            )

            verification.talent = talent

            verification.save()

            return redirect(
                "talent_dashboard"
            )

    else:

        form = VerificationRequestForm()

    return render(
        request,
        "talents/request_verification.html",
        {
            "form": form
        }
    )


@login_required
def talent_profile(request, talent_id):

    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )

    # =====================================================
    # PORTFOLIO
    # =====================================================

    portfolio_items = talent.portfolio_items.all()

    # =====================================================
    # FOLLOWERS
    # =====================================================

    followers_count = talent.user.followers.count()

    following = Follow.objects.filter(
        follower=request.user,
        following=talent.user
    ).exists()

    # =====================================================
    # CATEGORY-SPECIFIC PROFILE
    # =====================================================

    science_technology_profile = None
    arts_profile = None
    other_profile = None

    if talent.talent_category == "SCIENCE_TECHNOLOGY":

        try:
            science_technology_profile = (
                talent.science_technology_profile
            )
        except Exception:
            science_technology_profile = None

    elif talent.talent_category == "ARTS":

        try:
            arts_profile = talent.arts_profile
        except Exception:
            arts_profile = None

    elif talent.talent_category == "OTHERS":

        try:
            other_profile = talent.other_profile
        except Exception:
            other_profile = None

    # =====================================================
    # RECORD TALENT PROFILE VIEW
    # =====================================================

    if request.user.role == "ORGANIZATION":

        try:

            organization = Organization.objects.get(
                user=request.user
            )

            TalentProfileView.objects.create(
                organization=organization,
                talent=talent
            )

        except Organization.DoesNotExist:

            pass

    # =====================================================
    # RENDER PROFILE
    # =====================================================

    return render(
        request,
        "talents/profile.html",
        {
            "talent": talent,

            "portfolio_items": portfolio_items,

            "followers_count": followers_count,

            "following": following,

            "science_technology_profile":
                science_technology_profile,

            "arts_profile":
                arts_profile,

            "other_profile":
                other_profile,

            "available": (
                talent.available
                if hasattr(talent, "available")
                else True
            ),
        }
    )
    
@login_required
def talent_search(request):


    talents = TalentProfile.objects.all()



    query = request.GET.get(
        "q"
    )


    country = request.GET.get(
        "country"
    )


    verified = request.GET.get(
        "verified"
    )



    if query:


        talents = talents.filter(

            Q(headline__icontains=query) |

            Q(biography__icontains=query) |

            Q(skills__name__icontains=query) |

            Q(domains__name__icontains=query)

        ).distinct()



    if country:


        talents = talents.filter(

            country__icontains=country

        )



    if verified == "yes":


        talents = talents.filter(

            verified=True

        )



    # -------------------------------
    # Check shortlisted talents
    # -------------------------------

    shortlisted_ids = []


    try:

        organization = Organization.objects.get(
            user=request.user
        )


        shortlisted_ids = Shortlist.objects.filter(

            organization=organization

        ).values_list(

            "talent_id",

            flat=True

        )


    except Organization.DoesNotExist:

        pass



    return render(

        request,

        "talents/search.html",

        {

            "talents": talents,

            "shortlisted_ids": shortlisted_ids

        }

    )
    
    
@login_required
def edit_profile(request):


    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    if request.method == "POST":


        form = TalentProfileForm(
            request.POST,
            request.FILES,
            instance=talent
        )


        if form.is_valid():

            form.save()


            return redirect(
                "talent_dashboard"
            )


    else:


        form = TalentProfileForm(
            instance=talent
        )


    return render(
        request,
        "talents/edit_profile.html",
        {
            "form":form
        }
    ) 
    
    
    
@login_required
def talent_analytics(request):


    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # Profile Views

    profile_views = TalentProfileView.objects.filter(
        talent=talent
    ).count()



    # Organizations interested

    organizations_interested = Shortlist.objects.filter(
        talent=talent
    ).values(
        "organization"
    ).distinct().count()



    # Applications

    applications = Application.objects.filter(
        talent=talent
    )



    # Invitations

    invitations = Invitation.objects.filter(
        talent=talent
    )



    # Recommendation matches

    recommended_matches = RecommendationHistory.objects.filter(
        talent=talent
    ).order_by(
        "-score"
    )[:10]



    # Profile strength

    profile_strength = ProfileStrengthService.calculate_strength(
        talent
    )



    context = {


        "talent": talent,


        "profile_views": profile_views,


        "organizations_interested": organizations_interested,


        "applications": applications,


        "total_applications": applications.count(),


        "accepted_applications": applications.filter(
            status="ACCEPTED"
        ).count(),



        "pending_applications": applications.filter(
            status="PENDING"
        ).count(),



        "invitations": invitations,


        "profile_strength": profile_strength,


        "recommended_matches": recommended_matches,


    }



    return render(

        request,

        "talents/analytics.html",

        context

    )       


@login_required
def add_experience(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    if request.method == "POST":


        form = ExperienceForm(

            request.POST

        )


        if form.is_valid():


            experience = form.save(

                commit=False

            )


            experience.talent = talent


            experience.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = ExperienceForm()



    return render(

        request,

        "talents/add_experience.html",

        {

            "form": form

        }

    ) 
    
    
@login_required
def delete_experience(request, experience_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    experience = get_object_or_404(

        Experience,

        id=experience_id,

        talent=talent

    )


    experience.delete()


    return redirect(

        "talent_dashboard"

    ) 
    
    

@login_required
def edit_experience(request, experience_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    experience = get_object_or_404(

        Experience,

        id=experience_id,

        talent=talent

    )



    if request.method == "POST":


        form = ExperienceForm(

            request.POST,

            instance=experience

        )


        if form.is_valid():

            form.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = ExperienceForm(

            instance=experience

        )



    return render(

        request,

        "talents/edit_experience.html",

        {

            "form": form

        }

    )     
    
    
@login_required
def add_certification(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    if request.method == "POST":


        form = CertificationForm(

            request.POST,

            request.FILES

        )


        if form.is_valid():


            certification = form.save(

                commit=False

            )


            certification.talent = talent


            certification.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = CertificationForm()



    return render(

        request,

        "talents/add_certification.html",

        {

            "form": form

        }

    )  
    
    
@login_required
def delete_certification(request, certification_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    certification = get_object_or_404(

        Certification,

        id=certification_id,

        talent=talent

    )


    certification.delete()


    return redirect(

        "talent_dashboard"

    )  
    
@login_required
def edit_certification(request, certification_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    certification = get_object_or_404(

        Certification,

        id=certification_id,

        talent=talent

    )


    if request.method == "POST":


        form = CertificationForm(

            request.POST,

            request.FILES,

            instance=certification

        )


        if form.is_valid():

            form.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = CertificationForm(

            instance=certification

        )


    return render(

        request,

        "talents/edit_certification.html",

        {

            "form": form

        }

    )   
    
@login_required
def add_achievement(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    if request.method == "POST":


        form = AchievementForm(

            request.POST,

            request.FILES

        )


        if form.is_valid():


            achievement = form.save(

                commit=False

            )


            achievement.talent = talent


            achievement.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = AchievementForm()



    return render(

        request,

        "talents/add_achievement.html",

        {
            "form": form
        }

    )   
    
@login_required
def delete_achievement(request, achievement_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    achievement = get_object_or_404(

        Achievement,

        id=achievement_id,

        talent=talent

    )


    achievement.delete()


    return redirect(

        "talent_dashboard"

    )      
    
@login_required
def edit_achievement(request, achievement_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    achievement = get_object_or_404(

        Achievement,

        id=achievement_id,

        talent=talent

    )


    if request.method == "POST":


        form = AchievementForm(

            request.POST,

            request.FILES,

            instance=achievement

        )


        if form.is_valid():

            form.save()


            return redirect(

                "talent_dashboard"

            )


    else:


        form = AchievementForm(

            instance=achievement

        )


    return render(

        request,

        "talents/edit_achievement.html",

        {
            "form": form
        }

    )   
    
    
@login_required
def talent_invitations(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    invitations = Invitation.objects.filter(

        talent=talent

    ).order_by(

        "-created_at"

    )


    return render(

        request,

        "talents/invitations.html",

        {

            "invitations": invitations

        }

    ) 
    
    
@login_required
def accept_invitation(request, invitation_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    invitation = get_object_or_404(

        Invitation,

        id=invitation_id,

        talent=talent

    )


    invitation.status = "ACCEPTED"

    invitation.save()



    # Create conversation after acceptance

    Conversation.objects.get_or_create(

        talent=talent,

        organization=invitation.organization,

        opportunity=invitation.opportunity

    )



    # Notify organization

    Notification.objects.create(

        user=invitation.organization.user,

        notification_type="SYSTEM",

        message=f"{talent.user.get_full_name()} accepted your invitation for {invitation.opportunity.title}"

    )



    return redirect(

        "talent_invitations"

    )
    
    
@login_required
def decline_invitation(request, invitation_id):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    invitation = get_object_or_404(

        Invitation,

        id=invitation_id,

        talent=talent

    )


    invitation.status = "DECLINED"

    invitation.save()



    return redirect(

        "talent_invitations"

    )  
    
    
@login_required
def profile_strength(request):

    try:

        talent = TalentProfile.objects.get(
            user=request.user
        )


    except TalentProfile.DoesNotExist:


        return render(

            request,

            "talents/profile_strength.html",

            {

                "profile_exists": False

            }

        )



    strength = ProfileStrengthService.calculate_strength(

        talent

    )


    return render(

        request,

        "talents/profile_strength.html",

        {

            "profile_exists": True,

            "talent": talent,

            "strength": strength

        }

    )    
    
    

@login_required
def talent_settings(request):

    profile = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    if request.method == "POST":

        profile.availability_status = request.POST.get(
            "availability_status"
        )

        profile.profile_visibility = request.POST.get(
            "profile_visibility"
        )

        profile.save()

        return redirect("talent_settings")

    return render(
        request,
        "talents/settings.html",
        {
            "profile": profile
        }
    )

@login_required
def role_models(request):


    role_models = TalentProfile.objects.filter(

        is_role_model=True

    ).select_related(

        "user"

    ).prefetch_related(

        "skills",

        "achievements",

        "user__posts"

    )


    return render(

        request,

        "talents/role_models.html",

        {

            "role_models": role_models

        }

    )
@login_required
def follow_talent(request, talent_id):


    talent_to_follow = get_object_or_404(

        TalentProfile,

        id=talent_id

    )


    Follow.objects.get_or_create(

        follower=request.user,

        following=talent_to_follow.user

    )


    return redirect(
        "role_models"
    )    
    
    
@login_required
def unfollow_talent(request, talent_id):


    talent = get_object_or_404(

        TalentProfile,

        id=talent_id

    )


    Follow.objects.filter(

        follower=request.user,

        following=talent.user

    ).delete()



    return redirect(
        "role_models"
    )   
    
    
    
@login_required
def select_talent_category(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    if request.method == "POST":

        form = TalentCategoryForm(
            request.POST,
            instance=talent
        )

        if form.is_valid():

            form.save()

            if talent.talent_category == "SPORTS":
                return redirect("sports_profile_setup")

            elif talent.talent_category == "SCIENCE_TECHNOLOGY":
                return redirect("technology_profile_setup")

            elif talent.talent_category == "ARTS":
                return redirect("arts_profile_setup")

            elif talent.talent_category == "OTHERS":
                return redirect("other_profile_setup")

    else:

        form = TalentCategoryForm(
            instance=talent
        )

    return render(
        request,
        "talents/select_category.html",
        {
            "form": form
        }
    )   
    
    
    
# =====================================================
# SPORTS TALENT PROFILE SETUP
# =====================================================

@login_required
def sports_profile_setup(request):
    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    # Make sure the talent selected SPORTS
    if talent.talent_category != "SPORTS":
        return redirect("select_talent_category")

    profile, created = SportsTalentProfile.objects.get_or_create(
        talent=talent
    )

    if request.method == "POST":

        form = SportsTalentProfileForm(
            request.POST,
            instance=profile
        )

        if form.is_valid():

            # -------------------------------------------------
            # Get user-entered values
            # -------------------------------------------------
            sport_name = form.cleaned_data["sport"].strip()
            category_name = form.cleaned_data["sport_category"].strip()

            # -------------------------------------------------
            # Find existing sport or create a new one
            # -------------------------------------------------
            sport = Sport.objects.filter(
                name__iexact=sport_name
            ).first()

            if sport is None:
                sport = Sport.objects.create(
                    name=sport_name
                )

            # -------------------------------------------------
            # Find existing category for this sport
            # or create a new one
            # -------------------------------------------------
            category = SportCategory.objects.filter(
                sport=sport,
                name__iexact=category_name
            ).first()

            if category is None:
                category = SportCategory.objects.create(
                    sport=sport,
                    name=category_name
                )

            # -------------------------------------------------
            # Save the sports profile
            # -------------------------------------------------
            sports_profile = form.save(commit=False)

            sports_profile.talent = talent
            sports_profile.sport = sport
            sports_profile.sport_category = category

            sports_profile.save()

            return redirect("talent_dashboard")

    else:
        form = SportsTalentProfileForm(
            instance=profile
        )

    # ---------------------------------------------------------
    # Data used by autocomplete suggestions
    # ---------------------------------------------------------
    sports = Sport.objects.all().order_by("name")

    sport_categories = (
        SportCategory.objects
        .select_related("sport")
        .all()
        .order_by("name")
    )

    return render(
        request,
        "talents/sports_profile_setup.html",
        {
            "form": form,
            "talent": talent,
            "sports": sports,
            "sport_categories": sport_categories,
        }
    )

# =====================================================
# SCIENCE & TECHNOLOGY TALENT PROFILE SETUP
# =====================================================

@login_required
def technology_profile_setup(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    # Make sure the talent selected SCIENCE & TECHNOLOGY
    if talent.talent_category != "SCIENCE_TECHNOLOGY":
        return redirect("select_talent_category")

    profile, created = (
        ScienceTechnologyTalentProfile.objects.get_or_create(
            talent=talent
        )
    )

    if request.method == "POST":

        form = ScienceTechnologyTalentProfileForm(
            request.POST,
            instance=profile
        )

        if form.is_valid():

            form.save()

            return redirect(
                "talent_dashboard"
            )

    else:

        form = ScienceTechnologyTalentProfileForm(
            instance=profile
        )

    return render(
        request,
        "talents/technology_profile_setup.html",
        {
            "form": form,
            "talent": talent,
        }
    )


# =====================================================
# ARTS TALENT PROFILE SETUP
# =====================================================

@login_required
def arts_profile_setup(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    # Make sure the talent selected ARTS
    if talent.talent_category != "ARTS":
        return redirect("select_talent_category")

    profile, created = ArtsTalentProfile.objects.get_or_create(
        talent=talent
    )

    if request.method == "POST":

        form = ArtsTalentProfileForm(
            request.POST,
            instance=profile
        )

        if form.is_valid():

            form.save()

            return redirect(
                "talent_dashboard"
            )

    else:

        form = ArtsTalentProfileForm(
            instance=profile
        )

    return render(
        request,
        "talents/arts_profile_setup.html",
        {
            "form": form,
            "talent": talent,
        }
    )


# =====================================================
# OTHER TALENT PROFILE SETUP
# =====================================================

@login_required
def other_profile_setup(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    # Make sure the talent selected OTHERS
    if talent.talent_category != "OTHERS":
        return redirect("select_talent_category")

    profile, created = OtherTalentProfile.objects.get_or_create(
        talent=talent
    )

    if request.method == "POST":

        form = OtherTalentProfileForm(
            request.POST,
            instance=profile
        )

        if form.is_valid():

            form.save()

            return redirect(
                "talent_dashboard"
            )

    else:

        form = OtherTalentProfileForm(
            instance=profile
        )

    return render(
        request,
        "talents/other_profile_setup.html",
        {
            "form": form,
            "talent": talent,
        }
    )      
    
    