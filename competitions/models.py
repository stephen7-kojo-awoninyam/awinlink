from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Competition(models.Model):
    CATEGORIES = (
        ("SPORTS", "Sports"),
        ("SCIENCE_TECHNOLOGY", "Science & Technology"),
        ("ARTS", "Arts"),
        ("OTHERS", "Others"),
    )

    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted for approval"),
        ("REJECTED", "Changes requested"),
        ("APPROVED", "Approved"),
        ("PUBLISHED", "Published"),
        ("REGISTRATION_CLOSED", "Registration closed"),
        ("ONGOING", "Ongoing"),
        ("JUDGING", "Judging"),
        ("RESULTS", "Results published"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    )

    PUBLIC_STATUSES = (
        "PUBLISHED",
        "REGISTRATION_CLOSED",
        "ONGOING",
        "JUDGING",
        "RESULTS",
        "COMPLETED",
        "CANCELLED",
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="competitions",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORIES)
    discipline = models.CharField(max_length=150, blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )
    registration_start = models.DateField()
    registration_end = models.DateField()
    competition_start = models.DateField()
    competition_end = models.DateField()
    location = models.CharField(max_length=200, blank=True)
    online = models.BooleanField(default=False)
    requirements = models.TextField(blank=True)
    prizes = models.TextField(blank=True)
    rules = models.TextField(blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    @property
    def registration_open(self):
        today = timezone.localdate()
        if self.status != "PUBLISHED":
            return False
        if not self.registration_start <= today <= self.registration_end:
            return False
        if self.max_participants is not None:
            return self.participants.filter(status="REGISTERED").count() < self.max_participants
        return True

    @property
    def participant_count(self):
        return self.participants.filter(status="REGISTERED").count()


class CompetitionParticipant(models.Model):
    STATUS_CHOICES = (
        ("REGISTERED", "Registered"),
        ("WITHDRAWN", "Withdrawn"),
        ("DISQUALIFIED", "Disqualified"),
    )

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="competition_participations",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="REGISTERED",
    )
    submission = models.TextField(blank=True)
    submission_url = models.URLField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("registered_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("competition", "talent"),
                name="unique_competition_talent",
            ),
        ]

    def __str__(self):
        return f"{self.talent} - {self.competition}"


class CompetitionJudge(models.Model):
    ROLE_CHOICES = (
        ("MENTOR", "Mentor"),
        ("EVALUATOR", "Evaluator"),
        ("JUDGE", "Judge"),
    )

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE,
        related_name="judges",
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_judging_assignments",
        limit_choices_to={"role": "COACH"},
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="JUDGE")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("assigned_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("competition", "coach"),
                name="unique_competition_coach_judge",
            ),
        ]

    def __str__(self):
        return f"{self.coach} - {self.competition} ({self.role})"


class CompetitionEvaluation(models.Model):
    participant = models.ForeignKey(
        CompetitionParticipant,
        on_delete=models.CASCADE,
        related_name="evaluations",
    )
    judge = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="competition_evaluations",
    )
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        validators=(MinValueValidator(0), MaxValueValidator(100)),
    )
    feedback = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("participant", "judge"),
                name="unique_participant_competition_judge_evaluation",
            ),
        ]

    def __str__(self):
        return f"{self.judge} evaluated {self.participant}"


class CompetitionResult(models.Model):
    participant = models.OneToOneField(
        CompetitionParticipant,
        on_delete=models.CASCADE,
        related_name="result",
    )
    position = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1),),
    )
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(100)),
    )
    award = models.CharField(max_length=150, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("position", "participant__registered_at")

    def __str__(self):
        return f"{self.participant} - {self.award or self.position}"
