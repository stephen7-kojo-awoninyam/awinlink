from django.db import models

# Create your models here.




class RecruitmentStage(models.Model):


    STAGES = (

        ("SHORTLISTED", "Shortlisted"),
        ("INVITED", "Invited"),
        ("INTERVIEW", "Interview"),
        ("SELECTED", "Selected"),
        ("REJECTED", "Rejected"),

    )


    organization = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        related_name="recruitment_stages"

    )


    talent = models.ForeignKey(

        "talents.TalentProfile",

        on_delete=models.CASCADE,

        related_name="recruitment_stages"

    )


    opportunity = models.ForeignKey(

        "opportunities.Opportunity",

        on_delete=models.CASCADE,

        related_name="recruitment_pipeline"

    )


    stage = models.CharField(

        max_length=20,

        choices=STAGES,

        default="SHORTLISTED"

    )


    notes = models.TextField(

        blank=True

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
                    "organization",
                    "talent",
                    "opportunity"
                ],
                name="unique_recruitment_candidate"
            )
        ]

        ordering = [
            "-updated_at"
        ]    


    def __str__(self):

        return f"{self.talent} - {self.stage}"