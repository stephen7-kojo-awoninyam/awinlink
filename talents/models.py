from django.db import models
from django.conf import settings
# Create your models here.

class TalentProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="talent_profile"
    )

    TALENT_CATEGORY_CHOICES = (

        ("SPORTS", "Sports"),

        ("SCIENCE_TECHNOLOGY", "Science & Technology"),

        ("ARTS", "Arts"),

        ("OTHERS", "Others"),

    )

    talent_category = models.CharField(
        max_length=30,
        choices=TALENT_CATEGORY_CHOICES,
        blank=True,
        null=True
    )

    talent_area = models.CharField(
        max_length=150,
        blank=True,
        null=True
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
    
    AVAILABILITY_CHOICES = (

        ("AVAILABLE", "Available"),
        ("BUSY", "Currently Busy"),
        ("NOT_LOOKING", "Not Looking"),

    )


    VISIBILITY_CHOICES = (

        ("PUBLIC", "Public"),
        ("ORGANIZATIONS", "Organizations Only"),
        ("PRIVATE", "Private"),

    )


    availability_status = models.CharField(

        max_length=20,

        choices=AVAILABILITY_CHOICES,

        default="AVAILABLE"

    )


    profile_visibility = models.CharField(

        max_length=20,

        choices=VISIBILITY_CHOICES,

        default="PUBLIC"

    )


    preferred_work_type = models.CharField(
        max_length=20,
        choices=WORK_TYPES,
        default="REMOTE"
    )

    experience_level = models.CharField(
        max_length=20,
        choices=EXPERIENCE_LEVELS,
        default="BEGINNER"
    )
        
    domains = models.ManyToManyField(
    "domains.TalentDomain",
    blank=True
         )
    skills = models.ManyToManyField(
    "skills.Skill",
    blank=True
        )
    headline = models.CharField(
        max_length=200,
        blank=True
    )

    biography = models.TextField(
        blank=True
    )

    country = models.CharField(
        max_length=100,
        blank=True
    )

    city = models.CharField(
        max_length=100,
        blank=True
    )

    profile_photo = models.ImageField(
        upload_to="talents/profile/",
        blank=True,
        null=True
    )

    cover_photo = models.ImageField(
        upload_to="talents/cover/",
        blank=True,
        null=True
    )

    verified = models.BooleanField(
        default=False
    )
    
    # ==========================
    # Role Model System
    # ==========================

    is_role_model = models.BooleanField(

        default=False

    )


    role_model_category = models.CharField(

        max_length=100,

        blank=True

    )


    followers_count = models.PositiveIntegerField(

        default=0

    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    @property
    def display_identity(self):
        identities = {
            "SPORTS": "Athlete",
            "SCIENCE_TECHNOLOGY": "Technology Professional",
            "ARTS": "Artist",
            "OTHERS": "Talent",
        }

        return identities.get(
            self.talent_category,
            "Talent"
        )

    def __str__(self):
        return self.user.username
    
    
    
# ==========================
# Role Model Assignment
# ==========================


class RoleModelAssignment(models.Model):

    STATUS_CHOICES = (

        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("PAUSED", "Paused"),
        ("COMPLETED", "Completed"),
        ("REVOKED", "Revoked"),

    )

    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="role_model_assignments"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    score = models.PositiveIntegerField(
        default=0
    )

    category = models.CharField(
        max_length=100,
        blank=True
    )

    reason = models.TextField(
        blank=True
    )

    admin_notes = models.TextField(
        blank=True
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_model_assignments_made"
    )
    
    reviewed_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="role_model_assignments_reviewed"
    )
    ASSIGNMENT_TYPE_CHOICES = (
    ("QUALIFIED", "Qualification Based"),
    ("MANUAL", "Manual Assignment"),
    )
    
    assignment_type = models.CharField(
    max_length=20,
    choices=ASSIGNMENT_TYPE_CHOICES,
    default="QUALIFIED"
    )

    assigned_at = models.DateTimeField(
        null=True,
        blank=True
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    revoked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        ordering = ["-created_at"]

    def __str__(self):

        return f"{self.talent} - {self.status}"    
    


class VerificationRequest(models.Model):


    STATUS_CHOICES = (

        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),

    )


    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="verification_requests"
    )


    document = models.FileField(
        upload_to="verification_documents/"
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


    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )



    def __str__(self):

        return f"{self.talent} - {self.status}"



# ==========================
# Talent Achievements
# ==========================

   
class Achievement(models.Model):

    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="achievements"
    )


    title = models.CharField(
        max_length=200
    )


    description = models.TextField(
        blank=True
    )


    date_received = models.DateField(
        null=True,
        blank=True
    )


    image = models.ImageField(
        upload_to="achievements/",
        null=True,
        blank=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return self.title
    
class Certification(models.Model):


    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="certifications"
    )


    name = models.CharField(
        max_length=200
    )


    issuing_organization = models.CharField(
        max_length=200
    )


    issue_date = models.DateField(
        null=True,
        blank=True
    )


    certificate_file = models.FileField(
        upload_to="certifications/",
        null=True,
        blank=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return self.name         
    
    
class Experience(models.Model):


    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="experiences"
    )


    company = models.CharField(
        max_length=200
    )


    role = models.CharField(
        max_length=200
    )


    description = models.TextField(
        blank=True
    )


    start_date = models.DateField()


    end_date = models.DateField(
        null=True,
        blank=True
    )


    currently_working = models.BooleanField(
        default=False
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return f"{self.role} at {self.company}"    