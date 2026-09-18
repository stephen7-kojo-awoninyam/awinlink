from django.db import models
from organizations.models import Organization
# Create your models here.


class Opportunity(models.Model):


    OPPORTUNITY_TYPES = (

        ("JOB", "Job"),
        ("TRIAL", "Sports Trial"),
        ("SCHOLARSHIP", "Scholarship"),
        ("AUDITION", "Audition"),
        ("COMPETITION", "Competition"),

    )


    EXPERIENCE_LEVELS = (

        ("BEGINNER", "Beginner"),
        ("INTERMEDIATE", "Intermediate"),
        ("EXPERT", "Expert"),

    )


    WORK_TYPES = (

        ("REMOTE", "Remote"),
        ("ONSITE", "On Site"),
        ("HYBRID", "Hybrid"),

    )


    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="opportunities"
    )


    title = models.CharField(
        max_length=200
    )


    description = models.TextField()


    opportunity_type = models.CharField(
        max_length=20,
        choices=OPPORTUNITY_TYPES,
        default="JOB"
    )


    domain = models.ForeignKey(
        "domains.TalentDomain",
        on_delete=models.CASCADE
    )


    skills = models.ManyToManyField(
        "skills.Skill",
        blank=True
    )


    experience_level = models.CharField(
        max_length=20,
        choices=EXPERIENCE_LEVELS,
        default="BEGINNER"
    )


    work_type = models.CharField(
        max_length=20,
        choices=WORK_TYPES,
        default="REMOTE"
    )


    location = models.CharField(
        max_length=200,
        blank=True
    )


    deadline = models.DateField(
        null=True,
        blank=True
    )


    active = models.BooleanField(
        default=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return self.title
    
    
    
    
class OpportunityRequirement(models.Model):

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="requirements"
    )


    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.CASCADE
    )


    importance = models.PositiveIntegerField(
        default=1,
        help_text="1 = low importance, 5 = very important"
    )


    def __str__(self):
        return f"{self.opportunity.title} - {self.skill.name}"