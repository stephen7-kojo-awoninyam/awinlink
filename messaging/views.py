from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.urls import reverse
from applications.models import Application
from accounts.models import User

from .models import Conversation, ConversationParticipant, Message

from talents.models import TalentProfile
from organizations.models import Organization

from opportunities.models import Opportunity

from notifications.models import Notification

from django.contrib.auth import get_user_model

from coaches.models import CoachTalentBookmark, CoachProfile

from connections.models import Connection

from django.db.models import Q


from accounts.models import User
from opportunities.models import Opportunity

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
)



# =====================================================
# CONVERSATION DETAIL
# =====================================================

@login_required
def conversation(request, conversation_id):


    # ==========================================
    # GET CONVERSATION
    # ONLY PARTICIPANTS CAN ACCESS IT
    # ==========================================

    conversation = get_object_or_404(

        Conversation.objects.filter(

            participants__user=request.user

        ).distinct(),

        id=conversation_id

    )


    # ==========================================
    # GET MESSAGES
    # ==========================================

    messages = conversation.messages.select_related(

        "sender"

    ).order_by(

        "created_at"

    )


    # ==========================================
    # MARK RECEIVED MESSAGES AS READ
    # ==========================================

    messages.filter(

        is_read=False

    ).exclude(

        sender=request.user

    ).update(

        is_read=True

    )


    # ==========================================
    # SEND MESSAGE
    # ==========================================

    if request.method == "POST":

        content = request.POST.get(

            "content",

            ""

        ).strip()


        image = request.FILES.get(

            "image"

        )


        video = request.FILES.get(

            "video"

        )


        file = request.FILES.get(

            "file"

        )


        audio = request.FILES.get(

            "audio"

        )


        # ======================================
        # CHECK MESSAGE CONTENT
        # ======================================

        if content or image or video or file or audio:

            # ==================================
            # DETERMINE MESSAGE TYPE
            # ==================================

            if audio:

                message_type = "AUDIO"

            elif video:

                message_type = "VIDEO"

            elif image:

                message_type = "IMAGE"

            elif file:

                message_type = "FILE"

            else:

                message_type = "TEXT"


            # ==================================
            # CREATE MESSAGE
            # ==================================

            Message.objects.create(

                conversation=conversation,

                sender=request.user,

                message_type=message_type,

                content=content,

                image=image,

                video=video,

                file=file,

                audio=audio

            )


            # ==================================
            # UPDATE CONVERSATION ACTIVITY
            # ==================================

            conversation.save()


        return redirect(

            "messaging:conversation",

            conversation.id

        )


    # ==========================================
    # GET OTHER PARTICIPANTS
    # ==========================================

    participants = conversation.participants.select_related(

        "user"

    ).exclude(

        user=request.user

    )


    # ==========================================
    # DETERMINE CONVERSATION DISPLAY NAME
    # ==========================================

    if conversation.is_group:

        conversation_display_name = (

            conversation.name

            or

            f"Group Conversation {conversation.id}"

        )

    else:

        other_participant = participants.first()

        if other_participant:

            other_user = other_participant.user

            conversation_display_name = (

                other_user.get_full_name()

                or

                other_user.username

            )

        else:

            conversation_display_name = "Conversation"


    # ==========================================
    # RENDER CONVERSATION
    # ==========================================

    return render(

        request,

        "messaging/conversation.html",

        {

            "conversation": conversation,

            "messages": messages,

            "participants": participants,

            "conversation_display_name":
                conversation_display_name

        }

    )







# =====================================================
# SEND MESSAGE
# =====================================================

@login_required
def send_message(request, conversation_id):

    # ==========================================
    # GET CONVERSATION
    # ONLY PARTICIPANTS CAN SEND MESSAGES
    # ==========================================

    conversation = get_object_or_404(

        Conversation.objects.filter(

            participants__user=request.user

        ).distinct(),

        id=conversation_id

    )

    if request.method == "POST":

        # ======================================
        # GET MESSAGE DATA
        # ======================================

        content = request.POST.get(
            "content",
            ""
        ).strip()

        message_type = request.POST.get(
            "message_type",
            "TEXT"
        )

        image = request.FILES.get(
            "image"
        )

        video = request.FILES.get(
            "video"
        )

        file = request.FILES.get(
            "file"
        )

        audio = request.FILES.get(
            "audio"
        )

        # ======================================
        # DETERMINE MESSAGE TYPE
        # ======================================

        if audio:

            message_type = "AUDIO"

        elif video:

            message_type = "VIDEO"

        elif image:

            message_type = "IMAGE"

        elif file:

            message_type = "FILE"

        else:

            message_type = "TEXT"

        # ======================================
        # VALIDATE MESSAGE
        # ======================================

        if message_type == "TEXT" and not content:

            return redirect(
                "messaging:conversation",
                conversation_id
            )

        if message_type == "IMAGE" and not image:

            return redirect(
                "messaging:conversation",
                conversation_id
            )

        if message_type == "VIDEO" and not video:

            return redirect(
                "messaging:conversation",
                conversation_id
            )

        if message_type == "FILE" and not file:

            return redirect(
                "messaging:conversation",
                conversation_id
            )

        if message_type == "AUDIO" and not audio:

            return redirect(
                "conversation",
                conversation_id
            )

        # ======================================
        # CREATE MESSAGE
        # ======================================

        message = Message.objects.create(

            conversation=conversation,

            sender=request.user,

            message_type=message_type,

            content=content,

            image=image,

            video=video,

            file=file,

            audio=audio

        )

        # ======================================
        # FIND OTHER PARTICIPANTS
        # ======================================

        recipients = conversation.participants.select_related(
            "user"
        ).exclude(
            user=request.user
        )

        # ======================================
        # CREATE NOTIFICATIONS
        # ======================================

        for participant in recipients:

            recipient = participant.user

            Notification.objects.create(

                user=recipient,

                sender=request.user,

                notification_type="MESSAGE",

                message=(

                    f"{request.user.get_full_name()} "

                    f"sent you a message."

                ),

                conversation=conversation

            )

        # ======================================
        # UPDATE CONVERSATION ACTIVITY
        # ======================================

        conversation.save()

    return redirect(
        "messaging:conversation",
        conversation_id
    )






# =====================================================
# CONVERSATION LIST / INBOX
# =====================================================

@login_required
def conversation_list(request):

    conversations = Conversation.objects.filter(

        participants__user=request.user

    ).prefetch_related(

        "messages",
        "participants__user"

    ).distinct().order_by(

        "-updated_at"

    )


    for conversation in conversations:

        # ==========================================
        # UNREAD MESSAGE COUNT
        # ==========================================

        conversation.unread_count = (

            conversation.messages.filter(

                is_read=False

            ).exclude(

                sender=request.user

            ).count()

        )


        # ==========================================
        # FIND OTHER PARTICIPANTS
        # ==========================================

        conversation.other_participants = list(

            conversation.participants.select_related(

                "user"

            ).exclude(

                user=request.user

            )

        )


        # ==========================================
        # GET PRIMARY OTHER PARTICIPANT
        # ==========================================

        conversation.other_participant = (

            conversation.other_participants[0]

            if conversation.other_participants

            else None

        )


        # ==========================================
        # PARTICIPANT INFORMATION
        # ==========================================

        if conversation.other_participant:

            user = conversation.other_participant.user


            # ======================================
            # PARTICIPANT NAME
            # ======================================

            conversation.participant_name = (

                user.get_full_name()

                or user.username

            )


            # ======================================
            # PARTICIPANT ROLE
            # ======================================

            conversation.participant_role = (

                user.role

                if user.role

                else ""

            )


            # ======================================
            # PARTICIPANT IMAGE
            # ======================================

            conversation.participant_image = None


            # Talent / Athlete / Coach / Scout
            # all use TalentProfile

            if hasattr(user, "talent_profile"):

                if user.talent_profile.profile_photo:

                    conversation.participant_image = (

                        user.talent_profile.profile_photo.url

                    )


            # Organization

            elif hasattr(user, "organization"):

                if user.organization.logo:

                    conversation.participant_image = (

                        user.organization.logo.url

                    )


        else:

            # ======================================
            # NO OTHER PARTICIPANT
            # ======================================

            conversation.participant_name = (

                "Unknown User"

            )

            conversation.participant_role = ""

            conversation.participant_image = None


    # ==========================================
    # RENDER CONVERSATION LIST
    # ==========================================

    return render(

        request,

        "messaging/conversations.html",

        {

            "conversations": conversations

        }

    )






# =====================================================
# START NEW CONVERSATION
# =====================================================


@login_required
def start_conversation(request, user_id, opportunity_id=None):

    # ==========================================
    # CURRENT USER
    # ==========================================

    current_user = request.user


    # ==========================================
    # GET TARGET USER
    # ==========================================

    target_user = get_object_or_404(
        User,
        id=user_id
    )


    # ==========================================
    # CANNOT MESSAGE YOURSELF
    # ==========================================

    if current_user == target_user:

        return redirect(
            "messaging:conversation_list"
        )


    # ==========================================
    # OPPORTUNITY CONVERSATION
    # ==========================================

    opportunity = None


    if opportunity_id:

        opportunity = get_object_or_404(
            Opportunity,
            id=opportunity_id
        )


        organization_user = opportunity.organization.user


        # ======================================
        # TARGET MUST BE THE OPPORTUNITY OWNER
        # ======================================

        if target_user != organization_user:

            return redirect(
                "messaging:conversation_list"
            )


        # ======================================
        # CHECK WHETHER USER CAN MESSAGE
        # ======================================

        can_message = False


        # --------------------------------------
        # ORGANIZATION OWNER
        # --------------------------------------

        if current_user == organization_user:

            can_message = True


        # --------------------------------------
        # ACCEPTED TALENT APPLICATION
        # --------------------------------------

        else:

            can_message = Application.objects.filter(
                talent__user=current_user,
                opportunity=opportunity,
                status="ACCEPTED"
            ).exists()


        # --------------------------------------
        # DENY UNAUTHORIZED ACCESS
        # --------------------------------------

        if not can_message:

            return redirect(
                "messaging:conversation_list"
            )


    # ==========================================
    # NORMAL DIRECT MESSAGE
    # ==========================================

    else:

        connected = Connection.objects.filter(
            sender=current_user,
            receiver=target_user,
            status="ACCEPTED"
        ).exists() or Connection.objects.filter(
            sender=target_user,
            receiver=current_user,
            status="ACCEPTED"
        ).exists()


        if not connected:

            return redirect(
                "connections_list"
            )


    # ==========================================
    # FIND EXISTING CONVERSATION
    # ==========================================

    conversation = (
        Conversation.objects.filter(
            opportunity=opportunity,
            participants__user=current_user
        )
        .filter(
            participants__user=target_user
        )
        .distinct()
        .first()
    )


    # ==========================================
    # CREATE CONVERSATION IF NEEDED
    # ==========================================

    if not conversation:

        conversation = Conversation.objects.create(
            opportunity=opportunity
        )


    # ==========================================
    # ADD CURRENT USER
    # ==========================================

    ConversationParticipant.objects.get_or_create(
        conversation=conversation,
        user=current_user
    )


    # ==========================================
    # ADD TARGET USER
    # ==========================================

    ConversationParticipant.objects.get_or_create(
        conversation=conversation,
        user=target_user
    )


    # ==========================================
    # OPEN CONVERSATION
    # ==========================================

    conversation_url = reverse(
        "messaging:conversation",
        args=[conversation.id]
    )

    return redirect(conversation_url)
    
# =====================================================

# START COACH → TALENT CONVERSATION

# =====================================================

@login_required
def start_coach_conversation(request, talent_id):


        # ==========================================
        # ONLY COACHES
        # ==========================================

        if request.user.role != "COACH":

           return redirect("home")


        # ==========================================
        # GET COACH
        # ==========================================

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
            )


        # ==========================================
        # GET SAVED TALENT
        # ==========================================
        # The coach can start a conversation with
        # a talent from the saved-talents list.

        bookmark = get_object_or_404(
            CoachTalentBookmark,
            coach=coach,
            talent_id=talent_id
            )


        # ==========================================
        # GET TALENT
        # ==========================================

        talent = bookmark.talent

        target_user = talent.user


        # ==========================================
        # CANNOT MESSAGE YOURSELF
        # ==========================================

        if target_user == request.user:

            return redirect(
            "conversation_list"
            )


        # ==========================================
        # FIND EXISTING CONVERSATION
        # ==========================================

        conversation = (
        Conversation.objects.filter(
        opportunity=None,
        participants__user=request.user
        )
        .filter(
        participants__user=target_user
        )
        .distinct()
        .first()
        )


        # ==========================================
        # CREATE CONVERSATION
        # ==========================================

        if not conversation:

            conversation = Conversation.objects.create(
            opportunity=None
            )


        # ==========================================
        # ADD COACH
        # ==========================================

        ConversationParticipant.objects.get_or_create(
        conversation=conversation,
        user=request.user
        )


        # ==========================================
        # ADD TALENT
        # ==========================================

        ConversationParticipant.objects.get_or_create(
        conversation=conversation,
        user=target_user
        )


        # ==========================================
        # OPEN CONVERSATION
        # ==========================================

        return redirect(
            "messaging:conversation",
            conversation.id
            )




          
        
        


            


        