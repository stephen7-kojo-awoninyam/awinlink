from accounts.models import User
from notifications.models import Notification
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from datetime import timedelta
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Conversation, ConversationParticipant, Message,Call, CallParticipant
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from opportunities.models import Opportunity
from .serializers import (
    ConversationSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    CallSerializer,

)



# ============================================================
# CALL TIMEOUT
# ============================================================

CALL_RING_TIMEOUT = timedelta(seconds=30)


def expire_ringing_call(call):
    """
    Mark a ringing call as missed when nobody answers
    within the allowed ringing time.
    """

    if call.status != "RINGING":
        return False

    now = timezone.now()

    if now - call.started_at < CALL_RING_TIMEOUT:
        return False

    # --------------------------------------------------------
    # GET USERS WHO MISSED THE CALL
    # --------------------------------------------------------

    ringing_participants = list(
        CallParticipant.objects
        .filter(
            call=call,
            status="RINGING",
        )
        .select_related("user")
    )

    # --------------------------------------------------------
    # MARK CALL AS MISSED
    # --------------------------------------------------------

    call.status = "MISSED"
    call.ended_at = now

    call.save(
        update_fields=[
            "status",
            "ended_at",
        ]
    )

    # --------------------------------------------------------
    # MARK RINGING PARTICIPANTS AS MISSED
    # --------------------------------------------------------

    CallParticipant.objects.filter(
        call=call,
        status="RINGING",
    ).update(
        status="MISSED",
        left_at=now,
    )

    # --------------------------------------------------------
    # MARK CALLER AS LEFT
    # --------------------------------------------------------

    CallParticipant.objects.filter(
        call=call,
        status="JOINED",
    ).update(
        status="LEFT",
        left_at=now,
    )

    # --------------------------------------------------------
    # CREATE MISSED CALL NOTIFICATIONS
    # --------------------------------------------------------

    for participant in ringing_participants:

        Notification.objects.create(
            user=participant.user,
            sender=call.initiated_by,
            notification_type="MISSED_CALL",
            message=(
                f"You missed a "
                f"{call.call_type.lower()} call from "
                f"{call.initiated_by.get_full_name() or call.initiated_by.username}."
            ),
            conversation=call.conversation,
        )

    return True



# ============================================================
# MY CONVERSATIONS
# ============================================================

class MyConversationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        conversations = (
            Conversation.objects
            .filter(
                participants__user=request.user
            )
            .prefetch_related(
                "participants__user",
                "messages__sender",
            )
            .select_related(
                "opportunity",
            )
            .distinct()
            .order_by(
                "-updated_at"
            )
        )

        serializer = ConversationSerializer(
            conversations,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )



# ============================================================
# CREATE CONVERSATION
# ============================================================

class ConversationCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = ConversationCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        user_ids = serializer.validated_data.get(
            "user_ids",
            []
        )

        opportunity_id = serializer.validated_data.get(
            "opportunity_id"
        )

        is_group = serializer.validated_data.get(
            "is_group",
            False
        )

        name = serializer.validated_data.get(
            "name",
            ""
        ).strip()

        # ----------------------------------------------------
        # GET OPPORTUNITY
        # ----------------------------------------------------

        opportunity = None

        if opportunity_id:

            try:

                opportunity = Opportunity.objects.get(
                    id=opportunity_id
                )

            except Opportunity.DoesNotExist:

                return Response(
                    {
                        "detail": "Opportunity not found."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

        # ====================================================
        # GROUP CONVERSATION
        # ====================================================

        if is_group:

            # ------------------------------------------------
            # REMOVE DUPLICATES
            # ------------------------------------------------

            user_ids = list(
                dict.fromkeys(user_ids)
            )

            # ------------------------------------------------
            # GET USERS
            # ------------------------------------------------

            users = list(
                User.objects.filter(
                    id__in=user_ids
                )
            )

            if len(users) != len(user_ids):

                found_ids = {
                    user.id
                    for user in users
                }

                missing_ids = [
                    user_id
                    for user_id in user_ids
                    if user_id not in found_ids
                ]

                return Response(
                    {
                        "detail": "One or more users were not found.",
                        "missing_user_ids": missing_ids,
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # ------------------------------------------------
            # PREVENT SELF FROM EXPLICIT USER LIST
            #
            # The creator is automatically added.
            # ------------------------------------------------

            if request.user.id in user_ids:

                user_ids.remove(
                    request.user.id
                )

                users = [
                    user
                    for user in users
                    if user.id != request.user.id
                ]

            # ------------------------------------------------
            # GROUP MUST HAVE OTHER PARTICIPANTS
            # ------------------------------------------------

            if not users:

                return Response(
                    {
                        "detail":
                        "A group must contain at least one other participant."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ------------------------------------------------
            # CREATE GROUP
            # ------------------------------------------------

            conversation = Conversation.objects.create(
                opportunity=opportunity,
                is_group=True,
                name=name,
                created_by=request.user,
            )

            # ------------------------------------------------
            # ADD CREATOR
            # ------------------------------------------------

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=request.user
            )

            # ------------------------------------------------
            # ADD GROUP MEMBERS
            # ------------------------------------------------

            ConversationParticipant.objects.bulk_create(
                [
                    ConversationParticipant(
                        conversation=conversation,
                        user=user
                    )
                    for user in users
                ]
            )

            # ------------------------------------------------
            # RETURN GROUP
            # ------------------------------------------------

            response_serializer = ConversationSerializer(
                conversation
            )

            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        # ====================================================
        # ONE-TO-ONE CONVERSATION
        # ====================================================

        user_id = user_ids[0]

        # ----------------------------------------------------
        # GET OTHER USER
        # ----------------------------------------------------

        try:

            other_user = User.objects.get(
                id=user_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # PREVENT SELF CONVERSATION
        # ----------------------------------------------------

        if other_user == request.user:

            return Response(
                {
                    "detail": (
                        "You cannot create a "
                        "conversation with yourself."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # CHECK EXISTING ONE-TO-ONE CONVERSATION
        # ----------------------------------------------------

        user_conversations = (
            Conversation.objects
            .filter(
                participants__user=request.user
            )
            .filter(
                participants__user=other_user
            )
            .filter(
                is_group=False
            )
            .distinct()
        )

        if opportunity:

            user_conversations = (
                user_conversations
                .filter(
                    opportunity=opportunity
                )
            )

        else:

            user_conversations = (
                user_conversations
                .filter(
                    opportunity__isnull=True
                )
            )

        conversation = (
            user_conversations
            .first()
        )

        # ----------------------------------------------------
        # CREATE IF IT DOES NOT EXIST
        # ----------------------------------------------------

        if not conversation:

            conversation = Conversation.objects.create(
                opportunity=opportunity,
                is_group=False,
                created_by=request.user,
            )

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=request.user
            )

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=other_user
            )

        # ----------------------------------------------------
        # RETURN CONVERSATION
        # ----------------------------------------------------

        response_serializer = ConversationSerializer(
            conversation
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# CONVERSATION DETAIL
# ============================================================

class ConversationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):

        try:

            conversation = (
                Conversation.objects
                .prefetch_related(
                    "participants__user",
                    "messages__sender",
                )
                .select_related(
                    "opportunity",
                )
                .get(
                    id=conversation_id
                )
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # ACCESS CONTROL
        # ----------------------------------------------------

        is_participant = (
            ConversationParticipant.objects.filter(
                conversation=conversation,
                user=request.user
            ).exists()
        )

        if not is_participant:

            return Response(
                {
                    "detail": (
                        "You do not have access "
                        "to this conversation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ConversationSerializer(
            conversation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ============================================================
# CONVERSATION MESSAGES
# ============================================================

class ConversationMessagesAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):

        # ----------------------------------------------------
        # GET CONVERSATION
        # ----------------------------------------------------

        try:

            conversation = Conversation.objects.get(
                id=conversation_id
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # ACCESS CONTROL
        # ----------------------------------------------------

        if not ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user
        ).exists():

            return Response(
                {
                    "detail": (
                        "You do not have access "
                        "to this conversation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # GET MESSAGES
        # ----------------------------------------------------

        messages = (
            Message.objects
            .filter(
                conversation=conversation
            )
            .select_related(
                "sender"
            )
            .order_by(
                "created_at"
            )
        )

        serializer = MessageSerializer(
            messages,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ============================================================
# SEND MESSAGE
# ============================================================

class SendMessageAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):

        # ----------------------------------------------------
        # GET CONVERSATION
        # ----------------------------------------------------

        try:

            conversation = Conversation.objects.get(
                id=conversation_id
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # VERIFY PARTICIPANT
        # ----------------------------------------------------

        if not ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user
        ).exists():

            return Response(
                {
                    "detail": (
                        "You are not a participant "
                        "in this conversation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # VALIDATE MESSAGE
        # ----------------------------------------------------

        serializer = MessageSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        message_type = serializer.validated_data.get(
            "message_type",
            "TEXT"
        )

        content = serializer.validated_data.get(
            "content",
            ""
        )

        image = serializer.validated_data.get(
            "image"
        )

        video = serializer.validated_data.get(
            "video"
        )

        file = serializer.validated_data.get(
            "file"
        )

        audio = serializer.validated_data.get(
            "audio"
        )

        # ----------------------------------------------------
        # VALIDATE MESSAGE CONTENT
        # ----------------------------------------------------

        if message_type == "TEXT" and not content.strip():

            return Response(
                {
                    "detail": (
                        "Text messages must contain "
                        "content."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if message_type == "IMAGE" and not image:

            return Response(
                {
                    "detail": (
                        "Image messages must contain "
                        "an image."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if message_type == "VIDEO" and not video:

            return Response(
                {
                    "detail": (
                        "Video messages must contain "
                        "a video."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if message_type == "FILE" and not file:

            return Response(
                {
                    "detail": (
                        "File messages must contain "
                        "a file."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if message_type == "AUDIO" and not audio:

            return Response(
                {
                    "detail": (
                        "Audio messages must contain "
                        "an audio recording."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # CREATE MESSAGE
        # ----------------------------------------------------

        message = serializer.save(
            conversation=conversation,
            sender=request.user
        )

        # ----------------------------------------------------
        # UPDATE CONVERSATION
        # ----------------------------------------------------

        conversation.save()

        # ----------------------------------------------------
        # SERIALIZE RESPONSE
        # ----------------------------------------------------

        response_serializer = MessageSerializer(
            message
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )

# ============================================================
# MARK MESSAGE AS READ
# ============================================================

class MessageReadAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, message_id):

        try:

            message = (
                Message.objects
                .select_related(
                    "conversation"
                )
                .get(
                    id=message_id
                )
            )

        except Message.DoesNotExist:

            return Response(
                {
                    "detail": "Message not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # VERIFY PARTICIPANT
        # ----------------------------------------------------

        if not ConversationParticipant.objects.filter(
            conversation=message.conversation,
            user=request.user
        ).exists():

            return Response(
                {
                    "detail": (
                        "You do not have access "
                        "to this message."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # MARK READ
        # ----------------------------------------------------

        message.is_read = True

        message.save(
            update_fields=[
                "is_read"
            ]
        )

        serializer = MessageSerializer(
            message
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ============================================================
# MARK CONVERSATION MESSAGES AS READ
# ============================================================

class ConversationReadAllAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):

        try:

            conversation = Conversation.objects.get(
                id=conversation_id
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # VERIFY PARTICIPANT
        # ----------------------------------------------------

        if not ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user
        ).exists():

            return Response(
                {
                    "detail": (
                        "You do not have access "
                        "to this conversation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # MARK OTHER USERS' MESSAGES AS READ
        # ----------------------------------------------------

        updated = (
            Message.objects
            .filter(
                conversation=conversation,
                is_read=False
            )
            .exclude(
                sender=request.user
            )
            .update(
                is_read=True
            )
        )

        return Response(
            {
                "detail": (
                    "Conversation messages "
                    "marked as read."
                ),
                "updated_count": updated,
            },
            status=status.HTTP_200_OK
        )  
        
        
        
class StartCallAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):

        call_type = request.data.get("call_type")

        if call_type not in ["VOICE", "VIDEO"]:
            return Response(
                {
                    "detail":
                    "call_type must be either VOICE or VIDEO."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------
        # GET CONVERSATION
        # ---------------------------------------------------------

        try:
            conversation = (
                Conversation.objects
                .prefetch_related("participants__user")
                .get(id=conversation_id)
            )

        except Conversation.DoesNotExist:

            return Response(
                {"detail": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------------------
        # CHECK CONVERSATION PARTICIPATION
        # ---------------------------------------------------------

        is_participant = ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user
        ).exists()

        if not is_participant:

            return Response(
                {
                    "detail":
                    "You are not a participant in this conversation."
                },
                status=status.HTTP_403_FORBIDDEN
            )
            
            
        # ---------------------------------------------------------
        # EXPIRE OLD RINGING CALLS
        # ---------------------------------------------------------

        old_ringing_calls = Call.objects.filter(
            conversation=conversation,
            status="RINGING",
        )

        for old_call in old_ringing_calls:
            expire_ringing_call(old_call)    

        # ---------------------------------------------------------
        # CHECK ACTIVE CALL
        # ---------------------------------------------------------

        active_call = Call.objects.filter(
            conversation=conversation,
            status__in=["RINGING", "ACTIVE"]
        ).first()

        if active_call:

            return Response(
                {
                    "detail":
                    "There is already an active call in this conversation.",
                    "call_id": active_call.id,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------
        # CREATE CALL
        # ---------------------------------------------------------

        call = Call.objects.create(
            conversation=conversation,
            initiated_by=request.user,
            call_type=call_type,
            status="RINGING",
        )

        # ---------------------------------------------------------
        # CREATE CALL PARTICIPANTS
        # ---------------------------------------------------------

        conversation_participants = (
            conversation.participants
            .select_related("user")
            .all()
        )

        call_participants = []

        for participant in conversation_participants:

            if participant.user_id == request.user.id:

                participant_status = "JOINED"

            else:

                participant_status = "RINGING"

            call_participants.append(
                CallParticipant(
                    call=call,
                    user=participant.user,
                    status=participant_status,
                    joined_at=timezone.now()
                    if participant.user == request.user
                    else None,
                )
            )

        CallParticipant.objects.bulk_create(
            call_participants
        )
        
        # ---------------------------------------------------------
        # SEND GLOBAL INCOMING CALL EVENTS
        # ---------------------------------------------------------

        channel_layer = get_channel_layer()

        for participant in conversation_participants:

            if participant.user_id == request.user.id:
                continue

            async_to_sync(channel_layer.group_send)(
                f"user_{participant.user_id}",
                {
                    "type": "incoming_call",
                    "call_id": call.id,
                    "call_type": call.call_type,
                    "caller_id": request.user.id,
                    "caller_username": request.user.username,
                    "caller_first_name": request.user.first_name,
                    "caller_last_name": request.user.last_name,
                }
            )
        
        # ---------------------------------------------------------
        # CREATE INCOMING CALL NOTIFICATIONS
        # ---------------------------------------------------------

        for participant in conversation_participants:

            if participant.user_id == request.user.id:
                continue

            Notification.objects.create(
                user=participant.user,
                sender=request.user,
                notification_type="INCOMING_CALL",
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    f"is calling you by "
                    f"{call.call_type.lower()}."
                ),
                conversation=conversation,
            )

        # ---------------------------------------------------------
        # RESPONSE
        # ---------------------------------------------------------

        call = (
            Call.objects
            .select_related(
                "conversation",
                "initiated_by",
            )
            .prefetch_related(
                "participants__user",
            )
            .get(id=call.id)
        )

        serializer = CallSerializer(call)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

class AcceptCallAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):

        try:
            call = (
                Call.objects
                .select_related(
                    "conversation",
                    "initiated_by",
                )
                .prefetch_related(
                    "participants__user",
                )
                .get(id=call_id)
            )

        except Call.DoesNotExist:

            return Response(
                {"detail": "Call not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------------------
        # FIND THIS USER'S PARTICIPATION
        # ---------------------------------------------------------

        try:
            participant = CallParticipant.objects.get(
                call=call,
                user=request.user
            )

        except CallParticipant.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You are not a participant in this call."
                },
                status=status.HTTP_403_FORBIDDEN
            )
            
         # ---------------------------------------------------------
        # CHECK CALL TIMEOUT
        # ---------------------------------------------------------

        if call.status == "RINGING":

            expired = expire_ringing_call(call)

            if expired:

                return Response(
                    {
                        "detail":
                        "This call has expired because nobody answered within 30 seconds."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )   

        # ---------------------------------------------------------
        # CHECK PARTICIPANT STATUS
        # ---------------------------------------------------------

        if participant.status != "RINGING":

            return Response(
                {
                    "detail":
                    "This call is not waiting for your response."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------
        # JOIN CALL
        # ---------------------------------------------------------

        now = timezone.now()

        participant.status = "JOINED"
        participant.joined_at = now
        participant.save(
            update_fields=[
                "status",
                "joined_at",
            ]
        )
        
        # ---------------------------------------------------------
        # CLEAR INCOMING CALL NOTIFICATION
        # ---------------------------------------------------------

        Notification.objects.filter(
            user=request.user,
            sender=call.initiated_by,
            conversation=call.conversation,
            notification_type="INCOMING_CALL",
            is_read=False,
        ).update(
            is_read=True
        )

        # ---------------------------------------------------------
        # UPDATE CALL STATUS
        # ---------------------------------------------------------

        if call.status == "RINGING":

            call.status = "ACTIVE"
            call.answered_at = now

            call.save(
                update_fields=[
                    "status",
                    "answered_at",
                ]
            )

        # ---------------------------------------------------------
        # RETURN UPDATED CALL
        # ---------------------------------------------------------

        serializer = CallSerializer(call)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
class RejectCallAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):

        try:
            call = Call.objects.get(id=call_id)

        except Call.DoesNotExist:

            return Response(
                {"detail": "Call not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            participant = CallParticipant.objects.get(
                call=call,
                user=request.user
            )

        except CallParticipant.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You are not a participant in this call."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if participant.status != "RINGING":

            return Response(
                {
                    "detail":
                    "This call is not waiting for your response."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        participant.status = "REJECTED"
        participant.left_at = timezone.now()

        participant.save(
            update_fields=[
                "status",
                "left_at",
            ]
        )
        
        # ---------------------------------------------------------
        # CLEAR INCOMING CALL NOTIFICATION
        # ---------------------------------------------------------

        Notification.objects.filter(
            user=request.user,
            sender=call.initiated_by,
            conversation=call.conversation,
            notification_type="INCOMING_CALL",
            is_read=False,
        ).update(
            is_read=True
        )
        
        # ---------------------------------------------------------
        # NOTIFY OTHER CALL PARTICIPANTS THAT THIS USER REJECTED
        # ---------------------------------------------------------

        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            f"call_{call.id}",
            {
                "type": "participant_rejected",
                "user_id": request.user.id,
                "username": request.user.username,
            }
        )

        # If nobody else is still being invited/rung,
        # and no participant is active, end the call.
        remaining = CallParticipant.objects.filter(
            call=call,
            status__in=["RINGING", "JOINED"]
        ).exists()

        if not remaining:

            call.status = "ENDED"
            call.ended_at = timezone.now()

            call.save(
                update_fields=[
                    "status",
                    "ended_at",
                ]
            )

        serializer = CallSerializer(call)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )        
        

class EndCallAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):

        # =====================================================
        # GET CALL
        # =====================================================

        try:

            call = (
                Call.objects
                .select_related(
                    "conversation",
                    "initiated_by",
                )
                .prefetch_related(
                    "participants__user",
                )
                .get(id=call_id)
            )

        except Call.DoesNotExist:

            return Response(
                {
                    "detail": "Call not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =====================================================
        # CHECK PARTICIPANT
        # =====================================================

        try:

            participant = (
                CallParticipant.objects
                .get(
                    call=call,
                    user=request.user
                )
            )

        except CallParticipant.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You are not a participant in this call."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # CHECK PARTICIPANT STATUS
        # =====================================================

        if participant.status not in [
            "JOINED",
            "RINGING",
        ]:

            return Response(
                {
                    "detail":
                    "You are no longer active in this call."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        now = timezone.now()

        # =====================================================
        # END CALL FOR EVERYONE
        #
        # IMPORTANT:
        # Any participant can end the entire call.
        #
        # This works for:
        # - 1-to-1 calls
        # - group calls
        # =====================================================

        CallParticipant.objects.filter(
            call=call,
            status__in=[
                "JOINED",
                "RINGING",
                "INVITED",
            ]
        ).update(
            status="LEFT",
            left_at=now
        )

        # =====================================================
        # UPDATE CALL
        # =====================================================

        call.status = "ENDED"
        call.ended_at = now

        if call.answered_at:

            call.duration = int(
                (
                    now - call.answered_at
                ).total_seconds()
            )

        call.save(
            update_fields=[
                "status",
                "ended_at",
                "duration",
            ]
        )

        # =====================================================
        # BROADCAST CALL ENDED TO EVERYONE
        # =====================================================

        channel_layer = get_channel_layer()

        async_to_sync(
            channel_layer.group_send
        )(
            f"call_{call.id}",
            {
                "type": "call_ended",

                "call_id": call.id,

                "ended_by":
                    request.user.id,

                "ended_by_username":
                    request.user.username,
            }
        )

        # =====================================================
        # REFRESH CALL
        # =====================================================

        call = (
            Call.objects
            .select_related(
                "conversation",
                "initiated_by",
            )
            .prefetch_related(
                "participants__user",
            )
            .get(
                id=call.id
            )
        )

        # =====================================================
        # SERIALIZE
        # =====================================================

        serializer = CallSerializer(call)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
class IncomingCallsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------------------
        # EXPIRE OLD RINGING CALLS
        # ---------------------------------------------------------

        ringing_calls = Call.objects.filter(
            status="RINGING",
            started_at__lt=timezone.now() - CALL_RING_TIMEOUT,
        )

        for call in ringing_calls:
            expire_ringing_call(call)

        # ---------------------------------------------------------
        # GET CURRENT INCOMING CALLS
        # ---------------------------------------------------------

        calls = (
            Call.objects
            .filter(
                participants__user=request.user,
                participants__status="RINGING",
                status__in=["RINGING", "ACTIVE"],
            )
            .select_related(
                "conversation",
                "initiated_by",
            )
            .prefetch_related(
                "participants__user",
            )
            .distinct()
            .order_by("-started_at")
        )

        serializer = CallSerializer(
            calls,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# ============================================================
# ADD GROUP MEMBER
# ============================================================

class AddGroupMemberAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):

        # ----------------------------------------------------
        # GET CONVERSATION
        # ----------------------------------------------------

        try:

            conversation = Conversation.objects.get(
                id=conversation_id
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # MUST BE A GROUP
        # ----------------------------------------------------

        if not conversation.is_group:

            return Response(
                {
                    "detail":
                    "Members can only be added to group conversations."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # ONLY GROUP CREATOR CAN ADD MEMBERS
        # ----------------------------------------------------

        if conversation.created_by_id != request.user.id:

            return Response(
                {
                    "detail":
                    "Only the group creator can add members."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # GET USER ID
        # ----------------------------------------------------

        user_id = request.data.get("user_id")

        if not user_id:

            return Response(
                {
                    "detail":
                    "user_id is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # GET USER
        # ----------------------------------------------------

        try:

            user = User.objects.get(
                id=user_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # PREVENT ADDING CREATOR
        # ----------------------------------------------------

        if user.id == conversation.created_by_id:

            return Response(
                {
                    "detail":
                    "The group creator is already a member."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # CHECK EXISTING MEMBERSHIP
        # ----------------------------------------------------

        already_member = ConversationParticipant.objects.filter(
            conversation=conversation,
            user=user
        ).exists()

        if already_member:

            return Response(
                {
                    "detail":
                    "This user is already a member of the group."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # ADD MEMBER
        # ----------------------------------------------------

        participant = ConversationParticipant.objects.create(
            conversation=conversation,
            user=user
        )

        # ----------------------------------------------------
        # UPDATE CONVERSATION
        # ----------------------------------------------------

        conversation.save()

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return Response(
            {
                "detail":
                "User added to the group successfully.",
                "participant": {
                    "id": participant.id,
                    "user_id": user.id,
                    "username": user.username,
                }
            },
            status=status.HTTP_201_CREATED
        )


# ============================================================
# REMOVE GROUP MEMBER
# ============================================================

class RemoveGroupMemberAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, conversation_id, user_id):

        # ----------------------------------------------------
        # GET CONVERSATION
        # ----------------------------------------------------

        try:

            conversation = Conversation.objects.get(
                id=conversation_id
            )

        except Conversation.DoesNotExist:

            return Response(
                {
                    "detail": "Conversation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # MUST BE A GROUP
        # ----------------------------------------------------

        if not conversation.is_group:

            return Response(
                {
                    "detail":
                    "Members can only be removed from group conversations."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # ONLY GROUP CREATOR CAN REMOVE MEMBERS
        # ----------------------------------------------------

        if conversation.created_by_id != request.user.id:

            return Response(
                {
                    "detail":
                    "Only the group creator can remove members."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ----------------------------------------------------
        # PREVENT REMOVING CREATOR
        # ----------------------------------------------------

        if user_id == conversation.created_by_id:

            return Response(
                {
                    "detail":
                    "The group creator cannot be removed."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # GET PARTICIPANT
        # ----------------------------------------------------

        try:

            participant = ConversationParticipant.objects.get(
                conversation=conversation,
                user_id=user_id
            )

        except ConversationParticipant.DoesNotExist:

            return Response(
                {
                    "detail":
                    "This user is not a member of the group."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # REMOVE MEMBER
        # ----------------------------------------------------

        participant.delete()

        # ----------------------------------------------------
        # UPDATE CONVERSATION
        # ----------------------------------------------------

        conversation.save()

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return Response(
            {
                "detail":
                "User removed from the group successfully."
            },
            status=status.HTTP_200_OK
        )        