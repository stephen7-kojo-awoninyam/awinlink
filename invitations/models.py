from django.db import models
from django.utils import timezone



class Invitation(models.Model):


    STATUS = (

        ("PENDING","Pending"),
        ("ACCEPTED","Accepted"),
        ("DECLINED","Declined"),

    )


    organization = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        related_name="sent_invitations"

    )


    talent = models.ForeignKey(

        "talents.TalentProfile",

        on_delete=models.CASCADE,

        related_name="received_invitations"

    )


    opportunity = models.ForeignKey(

        "opportunities.Opportunity",

        on_delete=models.CASCADE,

        related_name="talent_invitations"

    )


    message = models.TextField(

        blank=True

    )


    status = models.CharField(

        max_length=20,

        choices=STATUS,

        default="PENDING"

    )


    created_at = models.DateTimeField(

        auto_now_add=True

    )


    responded_at = models.DateTimeField(

        null=True,

        blank=True

    )



    def accept(self):

        self.status="ACCEPTED"
        self.responded_at=timezone.now()
        self.save()



    def decline(self):

        self.status="DECLINED"
        self.responded_at=timezone.now()
        self.save()



    def __str__(self):

        return f"{self.organization.name} -> {self.talent.user.username}"