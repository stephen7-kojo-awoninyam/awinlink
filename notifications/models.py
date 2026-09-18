from django.db import models
from django.conf import settings



class Notification(models.Model):


    TYPE_CHOICES = (

        ("LIKE", "Post Like"),

        ("COMMENT", "Post Comment"),

        ("FOLLOW", "New Follow"),

        ("INVITATION", "Invitation"),

        ("APPLICATION", "Application"),

        ("MESSAGE", "Message"),

        ("SHORTLIST", "Shortlisted"),

        ("AI_MATCH", "AI Recommendation"),

        ("SYSTEM", "System"),
        
        ("SHARE", "Share"),
        
        ("CONNECTION", "Connection"),
        
        ("INCOMING_CALL", "Incoming Call"),

        ("MISSED_CALL", "Missed Call"),

    )
    

    user = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="notifications"

    )


    sender = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.SET_NULL,

        null=True,

        blank=True,

        related_name="sent_notifications"

    )


    notification_type = models.CharField(

        max_length=30,

        choices=TYPE_CHOICES,

        default="SYSTEM"

    )


    message = models.TextField()


    post = models.ForeignKey(

        "feed.Post",

        on_delete=models.CASCADE,

        null=True,

        blank=True

    )


    opportunity = models.ForeignKey(

        "opportunities.Opportunity",

        on_delete=models.CASCADE,

        null=True,

        blank=True

    )
    
    
    conversation = models.ForeignKey(
        "messaging.Conversation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications"
    )
    


    is_read = models.BooleanField(

        default=False

    )


    created_at = models.DateTimeField(

        auto_now_add=True

    )


    class Meta:

        ordering = [

            "-created_at"

        ]


    def __str__(self):

        return f"{self.user.username} - {self.notification_type}"