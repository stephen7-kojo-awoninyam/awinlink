from django.db import models
from django.conf import settings



# ==========================================
# UNIVERSAL USER FOLLOW SYSTEM
# ==========================================

class Follow(models.Model):


    follower = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="following"

    )


    following = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="followers"

    )


    created_at = models.DateTimeField(

        auto_now_add=True

    )



    class Meta:


        unique_together = (

            "follower",

            "following",

        )


        ordering = [

            "-created_at"

        ]



    def __str__(self):

        return (
            f"{self.follower.username} follows "
            f"{self.following.username}"
        )





# ==========================================
# ORGANIZATION FOLLOW SYSTEM
# ==========================================
       
        
class OrganizationFollow(models.Model):


    user = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="organization_following"

    )


    organization = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        related_name="organization_followers"

    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:

        unique_together = (

            "user",
            "organization",

        )


    def __str__(self):

        return f"{self.user} follows {self.organization}"        
    
    
    
    
    
    
    
# ==========================================
# PROFESSIONAL CONNECTION SYSTEM
# ==========================================

class Connection(models.Model):

    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_connections"
    )

    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_connections"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sender",
                    "receiver"
                ],
                name="unique_connection_request"
            )
        ]

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.sender.username} -> "
            f"{self.receiver.username} "
            f"({self.status})"
        )    