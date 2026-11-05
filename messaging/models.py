from django.db import models
from django.conf import settings
# Create your models here.


# ============================================================
# CONVERSATION
# ============================================================

class Conversation(models.Model):

    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="conversations"
    )

    # --------------------------------------------------------
    # GROUP CHAT
    # --------------------------------------------------------

    is_group = models.BooleanField(
        default=False
    )

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    image = models.ImageField(
        upload_to="messages/groups/",
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_conversations"
    )

    # --------------------------------------------------------
    # TIMESTAMPS
    # --------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        indexes = [models.Index(fields=['-updated_at', '-id'], name='msg_conversation_recent_idx')]

        ordering = [
            "-updated_at"
        ]

    @property
    def last_message(self):

        return self.messages.order_by(
            "-created_at"
        ).first()

    def __str__(self):

        if self.is_group:

            return (
                f"Group: "
                f"{self.name or f'Conversation {self.id}'}"
            )

        participant_names = ", ".join(
            participant.user.get_full_name()
            or participant.user.username
            for participant in self.participants.all()
        )

        return f"Conversation: {participant_names}"


# ============================================================
# CONVERSATION PARTICIPANT
# ============================================================

class ConversationParticipant(models.Model):

    last_read_at = models.DateTimeField(null=True, blank=True)

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="participants"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_participations"
    )

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        indexes = [models.Index(fields=['user', '-conversation'], name='msg_member_user_page_idx')]

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "conversation",
                    "user"
                ],
                name="unique_conversation_participant"
            )

        ]

    def __str__(self):

        return (
            f"{self.user.username} - "
            f"Conversation {self.conversation.id}"
        )


# ============================================================
# MESSAGE
# ============================================================

class Message(models.Model):

    MESSAGE_TYPES = (

        ("TEXT", "Text"),

        ("IMAGE", "Image"),

        ("VIDEO", "Video"),

        ("FILE", "File"),

        ("AUDIO", "Audio"),

    )

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default="TEXT"
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages"
    )

    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    content = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="messages/images/",
        blank=True,
        null=True
    )

    video = models.FileField(
        upload_to="messages/videos/",
        blank=True,
        null=True
    )

    file = models.FileField(
        upload_to="messages/files/",
        blank=True,
        null=True
    )

    audio = models.FileField(
        upload_to="messages/audio/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    is_read = models.BooleanField(
        default=False
    )

    class Meta:
        indexes = [
            models.Index(fields=['conversation', '-id'], name='msg_conversation_page_idx'),
            models.Index(fields=['conversation', 'created_at'], name='msg_conversation_read_idx'),
        ]

    def __str__(self):

        if self.content:
            return self.content[:50]

        if self.image:
            return f"Image message from {self.sender.username}"

        if self.video:
            return f"Video message from {self.sender.username}"

        if self.audio:
            return f"Audio message from {self.sender.username}"

        if self.file:
            return f"File message from {self.sender.username}"

        return f"Message from {self.sender.username}"
    
    
class Call(models.Model):

    CALL_TYPES = (
        ("VOICE", "Voice"),
        ("VIDEO", "Video"),
    )

    STATUS_CHOICES = (
        ("RINGING", "Ringing"),
        ("ACTIVE", "Active"),
        ("ENDED", "Ended"),
        ("MISSED", "Missed"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="calls"
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="initiated_calls"
    )

    # Original legacy decision retained when retired statuses are normalized.
    legacy_status = models.CharField(max_length=10, blank=True, default='', editable=False)

    call_type = models.CharField(
        max_length=10,
        choices=CALL_TYPES
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="RINGING"
    )

    started_at = models.DateTimeField(
        auto_now_add=True
    )

    answered_at = models.DateTimeField(
        null=True,
        blank=True
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True
    )

    duration = models.PositiveIntegerField(
        default=0,
        help_text="Call duration in seconds"
    )

    def __str__(self):

        return (
            f"{self.call_type} call "
            f"in Conversation {self.conversation.id} "
            f"by {self.initiated_by.username}"
        )


class CallParticipant(models.Model):

    # Explicit call-only access; never grants conversation history access.
    is_guest = models.BooleanField(default=False)
    invitation_expires_at = models.DateTimeField(null=True, blank=True)

    STATUS_CHOICES = (
        ("INVITED", "Invited"),
        ("RINGING", "Ringing"),
        ("JOINED", "Joined"),
        ("REJECTED", "Rejected"),
        ("LEFT", "Left"),
        ("MISSED", "Missed"),
    )

    call = models.ForeignKey(
        Call,
        on_delete=models.CASCADE,
        related_name="participants"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_participations"
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="INVITED"
    )

    joined_at = models.DateTimeField(
        null=True,
        blank=True
    )

    left_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:

        indexes = [models.Index(fields=['user', 'status', 'call'], name='msg_incoming_call_idx')]

        constraints = [
            models.UniqueConstraint(
                fields=["call", "user"],
                name="unique_call_participant"
            )
        ]

    def __str__(self):

        return (
            f"{self.user.username} - "
            f"Call {self.call.id} - "
            f"{self.status}"
        )
