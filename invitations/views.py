from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from organizations.models import Organization
from talents.models import TalentProfile
from opportunities.models import Opportunity
from messaging.models import Conversation
from .models import Invitation
from notifications.utils import create_notification
from django.contrib.auth.decorators import login_required
from notifications.models import Notification
from recruitment.models import RecruitmentStage
# Create your views here.


@login_required
def invite_talent(request, opportunity_id, talent_id):


    organization = get_object_or_404(
        Organization,
        user=request.user
    )


    opportunity = get_object_or_404(
        Opportunity,
        id=opportunity_id,
        organization=organization
    )


    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )



    invitation, created = Invitation.objects.get_or_create(

        organization=organization,

        talent=talent,

        opportunity=opportunity

    )

    Notification.objects.create(

        user=talent.user,

        sender=request.user,

        notification_type="INVITATION",

        message=f"{organization.name} invited you to apply for {opportunity.title}.",

        opportunity=opportunity

    )

    # Recruitment pipeline

    RecruitmentStage.objects.update_or_create(

        organization=organization,

        talent=talent,

        opportunity=opportunity,

        defaults={

            "stage":"INVITED"

        }

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



@login_required
def accept_invitation(request, invitation_id):


    invitation = get_object_or_404(

        Invitation,

        id=invitation_id,

        talent__user=request.user

    )



    invitation.status = "ACCEPTED"

    invitation.save()



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

    Conversation.objects.get_or_create(

        talent=invitation.talent,

        organization=invitation.organization,

        opportunity=invitation.opportunity

    )



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
def decline_invitation(request, invitation_id):


    invitation = get_object_or_404(

        Invitation,

        id=invitation_id,

        talent__user=request.user

    )



    invitation.status = "DECLINED"

    invitation.save()



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


    organization = get_object_or_404(
        Organization,
        user=request.user
    )


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
         