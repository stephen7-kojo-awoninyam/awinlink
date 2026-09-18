from django.db import models

# Create your models here.

class Application(models.Model):

    STATUS_CHOICES = (

        ("PENDING", "Pending"),
        ("REVIEWING", "Reviewing"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),

    )


    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="applications"
    )


    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.CASCADE,
        related_name="applications"
    )


    message = models.TextField(
        blank=True
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
                    "talent",
                    "opportunity"
                ],
                name="unique_talent_opportunity_application"
            )

        ]


    def __str__(self):
        return f"{self.talent} - {self.opportunity}"