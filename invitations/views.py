from organizations.permissions import OrganizationCapability, require_request_organization
from organizations.permissions import require_active_organization, organization_operation
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from organizations.models import Organization
from talents.models import TalentProfile
from opportunities.models import Opportunity
from messaging.models import Conversation, ConversationParticipant
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_POST
from .models import Invitation
from notifications.utils import create_notification
from django.contrib.auth.decorators import login_required
from notifications.models import Notification
from recruitment.models import RecruitmentStage
# Create your views here.


@login_required
def invite_talent_for_opportunity(request, opportunity_id, talent_id):
    from organizations.views import invite_talent as invite_for_opportunity
    return invite_for_opportunity(request, talent_id, opportunity_id)


@login_required
@require_POST
@transaction.atomic
def accept_invitation(request, invitation_id):


    invitation = get_object_or_404(

        Invitation.objects.select_for_update(),

        id=invitation_id,

        talent__user=request.user

    )



    require_active_organization(invitation.organization)
    if invitation.status != "PENDING":
        return HttpResponseBadRequest("This invitation has already been responded to.")
    invitation.accept()



    # Move candidate to interview stage

    RecruitmentStage.objects.update_or_create(

        organization=invitation.organization,

        talent=invitation.talent,

        opportunity=invitation.opportunity,

        defaults={

            "stage": "INTERVIEW"

        }

    )



    # Create conversation automatically

    conversation = Conversation.objects.filter(
        opportunity=invitation.opportunity, is_group=False,
        participants__user=invitation.talent.user,
    ).filter(participants__user=invitation.organization.user).first()
    if conversation is None:
        conversation = Conversation.objects.create(
            opportunity=invitation.opportunity,
            created_by=invitation.organization.user,
        )
        for user in (invitation.talent.user, invitation.organization.user):
            ConversationParticipant.objects.get_or_create(conversation=conversation, user=user)



    # Notify organization

    create_notification(

        user=invitation.organization.user,

        message=(

            f"{invitation.talent.user.get_full_name()} "

            f"accepted your invitation for "

            f"{invitation.opportunity.title}"

        ),

        notification_type="INVITATION"

    )



    return redirect(

        "talent_dashboard"

    )




@login_required
@require_POST
@transaction.atomic
def decline_invitation(request, invitation_id):


    invitation = get_object_or_404(

        Invitation.objects.select_for_update(),

        id=invitation_id,

        talent__user=request.user

    )



    require_active_organization(invitation.organization)
    if invitation.status != "PENDING":
        return HttpResponseBadRequest("This invitation has already been responded to.")
    invitation.decline()



    # Notify organization

    create_notification(

        user=invitation.organization.user,

        message=(

            f"{invitation.talent.user.get_full_name()} "

            f"declined your invitation for "

            f"{invitation.opportunity.title}"

        ),

        notification_type="INVITATION_DECLINED"

    )



    return redirect(

        "talent_dashboard"

    )
    


@login_required
def invite_talent(request, talent_id):


    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )


    organization = require_request_organization(request, OrganizationCapability.MANAGE_RECRUITMENT)


    opportunities = Opportunity.objects.filter(
        organization=organization,
        active=True
    )



    if request.method == "POST":


        opportunity_id = request.POST.get(
            "opportunity"
        )


        opportunity = get_object_or_404(
            Opportunity,
            id=opportunity_id,
            organization=organization
        )



        invitation, created = Invitation.objects.get_or_create(

            organization=organization,

            talent=talent,

            opportunity=opportunity

        )



        if created:


            create_notification(

                user=talent.user,

                message=(
                    f"{organization.name} invited you "
                    f"for {opportunity.title}"
                ),

                notification_type="INVITATION"

            )
            
                    
            Conversation.objects.get_or_create(

                organization=organization,

                talent=talent,

                opportunity=opportunity

          )


        return redirect(
            "organization_dashboard"
        )



    return render(

        request,

        "invitations/invite_talent.html",

        {

            "talent": talent,

            "opportunities": opportunities

        }

    )

