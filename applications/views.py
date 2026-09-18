from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from opportunities.models import Opportunity
from talents.models import TalentProfile
from .models import Application
from notifications.models import Notification
from django.contrib import messages
from django.utils import timezone
from messaging.models import Conversation, ConversationParticipant
# Create your views here.


# ==========================================
# APPLY FOR OPPORTUNITY
# ==========================================

@login_required
def apply_opportunity(request, opportunity_id):

    # ==================================
    # GET OPPORTUNITY
    # ==================================

    opportunity = get_object_or_404(
        Opportunity,
        id=opportunity_id
    )


    # ==================================
    # ONLY TALENTS CAN APPLY
    # ==================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # ==================================
    # CHECK OPPORTUNITY STATUS
    # ==================================

    if not opportunity.active:

        return redirect(
            "opportunity_detail",
            opportunity_id=opportunity.id
        )


    # ==================================
    # CHECK DEADLINE
    # ==================================

    if (
        opportunity.deadline
        and opportunity.deadline < timezone.localdate()
    ):

        return redirect(
            "opportunity_detail",
            opportunity_id=opportunity.id
        )


    # ==================================
    # PREVENT DUPLICATE APPLICATION
    # ==================================

    existing_application = Application.objects.filter(
        talent=talent,
        opportunity=opportunity
    ).first()


    if existing_application:

        return redirect(
            "opportunity_detail",
            opportunity_id=opportunity.id
        )


    # ==================================
    # GET APPLICATION MESSAGE
    # ==================================

    message = ""

    if request.method == "POST":

        message = request.POST.get(
            "message",
            ""
        ).strip()


    # ==================================
    # CREATE APPLICATION
    # ==================================

    application = Application.objects.create(

        talent=talent,

        opportunity=opportunity,

        message=message

    )


    # ==================================
    # NOTIFY ORGANIZATION
    # ==================================

    Notification.objects.create(

        user=opportunity.organization.user,

        notification_type="APPLICATION",

        message=(
            f"{talent.user.get_full_name()} "
            f"applied for "
            f"{opportunity.title}"
        )

    )


    # ==================================
    # RETURN TO OPPORTUNITY
    # ==================================

    return redirect(
        "opportunity_detail",
        opportunity_id=opportunity.id
    )


    

# ==========================================
# MARK APPLICATION AS REVIEWING
# ==========================================

@login_required
def review_application(request, application_id):

    if request.method != "POST":

        return redirect(
            "organization_applications"
        )


    application = get_object_or_404(
        Application,
        id=application_id
    )


    # ==========================================
    # VERIFY ORGANIZATION OWNER
    # ==========================================

    if (
        application.opportunity.organization.user
        != request.user
    ):

        return redirect("home")


    # ==========================================
    # UPDATE STATUS
    # ==========================================

    application.status = "REVIEWING"

    application.save()


    # ==========================================
    # NOTIFY TALENT
    # ==========================================

    Notification.objects.create(

        user=application.talent.user,

        sender=request.user,

        notification_type="APPLICATION",

        message=(
            f"Your application for "
            f"{application.opportunity.title} "
            f"is now being reviewed."
        )

    )


    messages.info(
        request,
        "Application marked as reviewing."
    )


    return redirect(
        "organization_applications"
    )

    


# ==========================================
# ACCEPT APPLICATION
# ==========================================

@login_required
def accept_application(request, application_id):

    if request.method != "POST":

        return redirect(
            "organization_applications"
        )


    application = get_object_or_404(
        Application,
        id=application_id
    )


    # ==========================================
    # VERIFY ORGANIZATION OWNER
    # ==========================================

    if (
        application.opportunity.organization.user
        != request.user
    ):

        return redirect("home")


    # ==========================================
    # UPDATE APPLICATION
    # ==========================================

    application.status = "ACCEPTED"

    application.save()


    # ==========================================
    # NOTIFY TALENT
    # ==========================================

    Notification.objects.create(

        user=application.talent.user,

        sender=request.user,

        notification_type="APPLICATION",

        message=(
            f"Your application for "
            f"{application.opportunity.title} "
            f"has been accepted."
        )

    )


    # ==========================================
    # CREATE CONVERSATION
    # ==========================================

    conversation = Conversation.objects.filter(

        opportunity=application.opportunity,

        participants__user=request.user

    ).filter(

        participants__user=application.talent.user

    ).first()


    if not conversation:

        conversation = Conversation.objects.create(

            opportunity=application.opportunity

        )


        ConversationParticipant.objects.create(

            conversation=conversation,

            user=request.user

        )


        ConversationParticipant.objects.create(

            conversation=conversation,

            user=application.talent.user

        )


    messages.success(
        request,
        "Application accepted successfully."
    )


    return redirect(
        "organization_applications"
    )


# ==========================================
# REJECT APPLICATION
# ==========================================

@login_required
def reject_application(request, application_id):

    if request.method != "POST":

        return redirect(
            "organization_applications"
        )


    application = get_object_or_404(
        Application,
        id=application_id
    )


    # ==========================================
    # VERIFY ORGANIZATION OWNER
    # ==========================================

    if (
        application.opportunity.organization.user
        != request.user
    ):

        return redirect("home")


    # ==========================================
    # UPDATE APPLICATION
    # ==========================================

    application.status = "REJECTED"

    application.save()


    # ==========================================
    # NOTIFY TALENT
    # ==========================================

    Notification.objects.create(

        user=application.talent.user,

        sender=request.user,

        notification_type="APPLICATION",

        message=(
            f"Your application for "
            f"{application.opportunity.title} "
            f"has been rejected."
        )

    )


    messages.info(
        request,
        "Application rejected."
    )


    return redirect(
        "organization_applications"
    )

