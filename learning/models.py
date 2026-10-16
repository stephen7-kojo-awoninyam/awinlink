from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.utils import timezone
from django.db import transaction
from django.core.validators import MinValueValidator
import uuid


# Create your models here.


class LearningCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    icon = models.CharField(
        max_length=100,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
    
    
    
    
    
class Course(models.Model):

    LEVELS = (

        ("BEGINNER", "Beginner"),
        ("INTERMEDIATE", "Intermediate"),
        ("ADVANCED", "Advanced"),

    )
    
    STATUS = (

    ("DRAFT","Draft"),

    ("PENDING","Pending"),

    ("APPROVED","Approved"),

    ("REJECTED","Rejected"),

)
    
    rejection_reason = models.TextField(
        blank=True,
        null=True
    )    

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses"
    )


    category = models.ForeignKey(
        LearningCategory,
        on_delete=models.CASCADE,
        related_name="courses"
    )

    title = models.CharField(
        max_length=250
    )

    slug = models.SlugField(
        unique=True
    )

    description = models.TextField()

    thumbnail = models.ImageField(
        upload_to="learning/thumbnails/",
        blank=True,
        null=True
    )

    level = models.CharField(
        max_length=20,
        choices=LEVELS,
        default="BEGINNER"
    )

    duration = models.PositiveIntegerField(
        default=0,
        help_text="Minutes"
    )

    is_free = models.BooleanField(
        default=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="DRAFT",
        db_index=True
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
        return self.title
    
    
    

    
    
class CourseLike(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_likes"
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="likes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user} liked {self.course}"


class CourseComment(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_comments"
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    text = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} commented on {self.course}"


class CourseReview(models.Model):

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    rating = models.PositiveSmallIntegerField()

    review = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        unique_together = (
            "course",
            "user",
        )     
        
# =========================================================
# CERTIFICATE
# =========================================================

class Certificate(models.Model):

    enrollment = models.OneToOneField(
        "Enrollment",
        on_delete=models.CASCADE,
        related_name="certificate"
    )

    certificate_id = models.CharField(
        max_length=100,
        unique=True
    )

    issued_at = models.DateTimeField(
        auto_now_add=True
    )

    pdf = models.FileField(
        upload_to="certificates/",
        blank=True,
        null=True
    )

    def __str__(self):
        return self.certificate_id
    
class Lesson(models.Model):

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lessons"
    )

    title = models.CharField(
        max_length=250
    )

    description = models.TextField(
        blank=True
    )

    video = models.FileField(
        upload_to="learning/videos/",
        blank=True,
        null=True
    )

    notes = models.FileField(
        upload_to="learning/notes/",
        blank=True,
        null=True
    )

    order = models.PositiveIntegerField()

    duration = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title
    
    
class Enrollment(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments"
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True
    )

    completed = models.BooleanField(
        default=False
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:

        unique_together = (

            "user",

            "course",

        )

    def __str__(self):
        return f"{self.user} - {self.course}"
    
    
class LessonProgress(models.Model):

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="lesson_progress"
    )

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE
    )

    completed = models.BooleanField(
        default=False
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:

        unique_together = (

            "enrollment",

            "lesson",

        )

    def __str__(self):
        return f"{self.lesson}"
        
        
class Quiz(models.Model):

    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="quiz"
    )

    title = models.CharField(
        max_length=200
    )

    passing_score = models.PositiveIntegerField(
        default=70
    )

    def __str__(self):
        return self.title
    
    
    
    
class Question(models.Model):

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question = models.TextField()

    option_a = models.CharField(
        max_length=250
    )

    option_b = models.CharField(
        max_length=250
    )

    option_c = models.CharField(
        max_length=250
    )

    option_d = models.CharField(
        max_length=250
    )

    correct_answer = models.CharField(
        max_length=1
    )

    def __str__(self):
        return self.question[:50]
    
    
class QuizAttempt(models.Model):

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="quiz_attempts"
    )

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    score = models.PositiveIntegerField(
        default=0
    )

    total_questions = models.PositiveIntegerField(
        default=0
    )

    percentage = models.PositiveIntegerField(
        default=0
    )

    passed = models.BooleanField(
        default=False
    )

    attempted_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-attempted_at"]

    def __str__(self):
        return (
            f"{self.enrollment.user.username} - "
            f"{self.quiz.title} - "
            f"{self.percentage}%"
        )


class ClassroomRole(models.TextChoices):
    HOST = "HOST", "Host"
    COHOST = "COHOST", "Co-host"
    LEARNER = "LEARNER", "Learner"


class AdmissionState(models.TextChoices):
    WAITING = "WAITING", "Waiting"
    ADMITTED = "ADMITTED", "Admitted"
    DENIED = "DENIED", "Denied"
    REMOVED = "REMOVED", "Removed"


class ClassroomQuerySet(models.QuerySet):
    """Bulk ORM writes validate every row and roll back the entire batch."""

    def update(self, **kwargs):
        fields = []
        for name, value in kwargs.items():
            field = self.model._meta.get_field(name)
            if field.primary_key or hasattr(value, "resolve_expression"):
                raise ValidationError("Classroom updates require literal non-primary-key values.")
            fields.append(field.name)
        with transaction.atomic(using=self.db):
            self._lock_classrooms()
            rows = list(self.order_by("pk").select_for_update())
            for row in rows:
                for name, value in kwargs.items():
                    setattr(row, name, value)
                row.save(using=self.db, update_fields=fields)
            return len(rows)

    def bulk_update(self, objs, fields, batch_size=None):
        objs = list(objs)
        if not fields or any(obj.pk is None for obj in objs):
            raise ValueError("Bulk updates require saved objects and fields.")
        for name in fields:
            field = self.model._meta.get_field(name)
            if field.primary_key or not field.concrete or field.many_to_many:
                raise ValueError("Bulk updates require concrete non-primary-key fields.")
        with transaction.atomic(using=self.db):
            self.filter(pk__in=[obj.pk for obj in objs])._lock_classrooms()
            rows = {row.pk: row for row in self.filter(pk__in=[obj.pk for obj in objs]).order_by("pk").select_for_update()}
            count = len(rows)
            for obj in objs:
                if obj.pk in rows:
                    row = rows.pop(obj.pk)
                    for name in fields:
                        field = self.model._meta.get_field(name)
                        value = getattr(obj, field.attname)
                        if hasattr(value, "resolve_expression"):
                            raise ValidationError("Classroom updates require literal values.")
                        setattr(row, field.attname, value)
                    row.save(using=self.db, update_fields=fields)
            return count

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None):
        if ignore_conflicts or update_conflicts:
            raise ValidationError("Conflict-skipping classroom writes bypass validation and are unsupported.")
        objs = list(objs)
        with transaction.atomic(using=self.db):
            ids = {obj._classroom_lock_id(self.db) for obj in objs}
            list(Classroom.objects.using(self.db).filter(pk__in=ids).order_by("pk").select_for_update())
            for obj in objs:
                obj.save(using=self.db, force_insert=True)
        return objs

    def _lock_classrooms(self):
        ids = {row._classroom_lock_id(self.db) for row in self}
        list(Classroom.objects.using(self.db).filter(pk__in=ids).order_by("pk").select_for_update())


class ValidatedClassroomModel(models.Model):
    """Normal and bulk ORM writes share model validation."""

    objects = ClassroomQuerySet.as_manager()
    immutable_fields = ()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            classroom_id = self._classroom_lock_id(using)
            if classroom_id:
                Classroom.objects.using(using).select_for_update().get(pk=classroom_id)
            return self._validated_save(*args, **kwargs)

    def _classroom_lock_id(self, using):
        if self._meta.model_name == "classroom":
            return self.pk if not self._state.adding else None
        if getattr(self, "classroom_id", None):
            return self.classroom_id
        if hasattr(self, "session_id"):
            return LiveSession.objects.using(using).filter(pk=self.session_id).values_list("classroom_id", flat=True).first()
        return SessionParticipant.objects.using(using).filter(pk=self.participant_id).values_list("session__classroom_id", flat=True).first()

    def _validated_save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        if self.pk and not self._state.adding:
            current = type(self).objects.using(using).get(pk=self.pk)
            fields = kwargs.get("update_fields")
            if fields is not None:
                fields = set(fields)
                kwargs["update_fields"] = fields
                if not fields:
                    return
                # Validate the state actually written, including deferred fields.
                for field in self._meta.concrete_fields:
                    if field.name not in fields and field.attname not in fields:
                        setattr(self, field.attname, getattr(current, field.attname))
            for name in self.immutable_fields:
                if getattr(current, name) != getattr(self, name):
                    raise ValidationError({name: "This relationship or identity cannot be changed."})
            if isinstance(self, LiveSession):
                transitions = {"SCHEDULED": {"SCHEDULED", "LIVE", "CANCELLED"},
                               "LIVE": {"LIVE", "ENDED"}, "ENDED": {"ENDED"}, "CANCELLED": {"CANCELLED"}}
                if self.status not in transitions.get(current.status, set()):
                    raise ValidationError("Invalid session lifecycle transition.")
                if current.started_at is not None and self.started_at != current.started_at:
                    raise ValidationError("The recorded session start cannot be changed.")
                if current.ended_at is not None and self.ended_at != current.ended_at:
                    raise ValidationError("The recorded session end cannot be changed.")
            if isinstance(self, AttendanceInterval) and current.left_at is not None and self.left_at != current.left_at:
                raise ValidationError("A closed attendance interval cannot be reopened or changed.")
            if isinstance(self, ClassroomInvitation):
                if current.status != ClassroomInvitation.Status.PENDING and (self.status != current.status or self.responded_at != current.responded_at):
                    raise ValidationError("A completed invitation cannot be changed.")
        # Foreign-key objects supplied by callers may contain stale roles,
        # admission states or capacity. Always validate persisted relationships.
        self._state.db = using
        self._state.fields_cache.clear()
        self.full_clean()
        return super().save(*args, **kwargs)


class Classroom(ValidatedClassroomModel):
    immutable_fields = ("course_id", "created_by_id")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="classrooms")
    title = models.CharField(max_length=250)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="created_classrooms")
    is_active = models.BooleanField(default=True)
    capacity = models.PositiveIntegerField(default=50, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(capacity__gte=1), name="classroom_positive_capacity")]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.pk and self.capacity:
            reservations = SessionParticipant.objects.filter(session__classroom_id=self.pk,
                session__status__in=[LiveSession.Status.SCHEDULED, LiveSession.Status.LIVE],
                admission_state=AdmissionState.ADMITTED).values("session_id").annotate(total=models.Count("pk"))
            if reservations.filter(total__gt=self.capacity).exists():
                raise ValidationError({"capacity": "Capacity cannot be lower than an existing session's admissions."})


class ClassroomMembership(ValidatedClassroomModel):
    immutable_fields = ("classroom_id", "user_id")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="classroom_memberships")
    role = models.CharField(max_length=10, choices=ClassroomRole.choices, default=ClassroomRole.LEARNER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["classroom", "user"], name="classroom_unique_member"),
            models.UniqueConstraint(fields=["classroom"], condition=Q(role="HOST", is_active=True),
                                    name="classroom_one_active_host"),
            models.CheckConstraint(condition=Q(role__in=ClassroomRole.values), name="classroom_valid_role"),
        ]


class ClassroomInvitation(ValidatedClassroomModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        REVOKED = "REVOKED", "Revoked"
        EXPIRED = "EXPIRED", "Expired"

    immutable_fields = ("classroom_id", "recipient_id", "invited_by_id", "expires_at", "message")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="invitations")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="classroom_invitations")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name="sent_classroom_invitations")
    message = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["classroom", "recipient"], condition=Q(status="PENDING"),
                                    name="classroom_unique_pending_invite"),
            models.CheckConstraint(condition=Q(status__in=["PENDING", "ACCEPTED", "DECLINED", "REVOKED", "EXPIRED"]),
                                   name="classroom_invite_valid_status"),
            models.CheckConstraint(condition=(Q(status="PENDING", responded_at__isnull=True) |
                (~Q(status="PENDING") & Q(responded_at__isnull=False))), name="classroom_invite_response_state"),
            models.CheckConstraint(condition=Q(expires_at__gt=F("created_at")), name="classroom_invite_expiry_order"),
            models.CheckConstraint(condition=Q(responded_at__isnull=True) | Q(responded_at__gte=F("created_at")),
                                   name="classroom_invite_response_order"),
        ]


class LiveSession(ValidatedClassroomModel):
    immutable_fields = ("classroom_id", "lesson_id")
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        LIVE = "LIVE", "Live"
        ENDED = "ENDED", "Ended"
        CANCELLED = "CANCELLED", "Cancelled"

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="live_sessions")
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="live_sessions")
    title = models.CharField(max_length=250)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["SCHEDULED", "LIVE", "ENDED", "CANCELLED"]),
                                   name="session_valid_status"),
            models.CheckConstraint(condition=Q(scheduled_end__isnull=True) | (
                Q(scheduled_start__isnull=False) & Q(scheduled_end__gt=F("scheduled_start"))),
                name="session_schedule_order"),
            models.CheckConstraint(condition=Q(ended_at__isnull=True) | (
                Q(started_at__isnull=False) & Q(ended_at__gte=F("started_at"))),
                name="session_actual_order"),
            models.CheckConstraint(condition=~Q(status="LIVE") | (
                Q(started_at__isnull=False) & Q(ended_at__isnull=True)), name="session_live_timestamps"),
            models.CheckConstraint(condition=~Q(status="ENDED") | Q(ended_at__isnull=False),
                                   name="session_ended_timestamp"),
        ]

    def clean(self):
        super().clean()
        if self.classroom_id and self.lesson_id and self.lesson.course_id != self.classroom.course_id:
            raise ValidationError({"lesson": "The lesson must belong to the classroom's course."})
        if self.status in {self.Status.SCHEDULED, self.Status.CANCELLED} and (self.started_at is not None or self.ended_at is not None):
            raise ValidationError("Scheduled and cancelled sessions cannot have actual attendance times.")
        if self.pk and self.status in {self.Status.ENDED, self.Status.CANCELLED}:
            if AttendanceInterval.objects.filter(participant__session_id=self.pk, left_at__isnull=True).exists():
                raise ValidationError("Close attendance before ending or cancelling the session.")


class SessionParticipant(ValidatedClassroomModel):
    immutable_fields = ("session_id", "membership_id")
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="participants")
    membership = models.ForeignKey(ClassroomMembership, on_delete=models.PROTECT,
                                   related_name="session_participations")
    role = models.CharField(max_length=10, choices=ClassroomRole.choices, default=ClassroomRole.LEARNER)
    admission_state = models.CharField(max_length=10, choices=AdmissionState.choices,
                                       default=AdmissionState.WAITING)
    admitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "membership"], name="session_unique_participant"),
            models.UniqueConstraint(fields=["session"], condition=Q(role="HOST"), name="session_one_host"),
            models.CheckConstraint(condition=Q(role__in=ClassroomRole.values), name="participant_valid_role"),
            models.CheckConstraint(condition=Q(admission_state__in=AdmissionState.values),
                                   name="participant_valid_admission"),
            models.CheckConstraint(condition=~Q(admission_state="ADMITTED") | Q(admitted_at__isnull=False),
                                   name="participant_admitted_timestamp"),
        ]

    def clean(self):
        super().clean()
        if self.session_id and self.membership_id:
            if self.membership.classroom_id != self.session.classroom_id:
                raise ValidationError({"membership": "Membership must belong to the session's classroom."})
            if self.admission_state == AdmissionState.ADMITTED and not self.membership.is_active:
                raise ValidationError({"membership": "Inactive members cannot be admitted."})
            if self.role != self.membership.role:
                raise ValidationError({"role": "Participant role must match the classroom assignment."})
            if self.admission_state == AdmissionState.ADMITTED:
                if self.role == ClassroomRole.LEARNER and not Enrollment.objects.filter(
                    user_id=self.membership.user_id, course_id=self.session.classroom.course_id).exists():
                    raise ValidationError("Admitted learners must be enrolled in the course.")
                reserved = SessionParticipant.objects.filter(session_id=self.session_id, admission_state=AdmissionState.ADMITTED).exclude(pk=self.pk).count()
                if reserved >= self.session.classroom.capacity:
                    raise ValidationError("The session has reached classroom capacity.")
            elif self.pk and self.attendance_intervals.filter(left_at__isnull=True).exists():
                raise ValidationError("Close attendance before revoking admission.")


class AttendanceInterval(ValidatedClassroomModel):
    immutable_fields = ("participant_id", "connection_id", "joined_at")
    connection_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    signaling_channel_name = models.CharField(max_length=255, null=True, blank=True, editable=False)
    signaling_heartbeat_at = models.DateTimeField(null=True, blank=True, editable=False)
    participant = models.ForeignKey(SessionParticipant, on_delete=models.CASCADE,
                                    related_name="attendance_intervals")
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(left_at__isnull=True) | Q(left_at__gte=F("joined_at")),
                                   name="attendance_time_order"),
            models.UniqueConstraint(fields=["participant"], condition=Q(left_at__isnull=True),
                                    name="attendance_one_open_interval"),
        ]

    def clean(self):
        super().clean()
        if self.participant_id:
            participant = self.participant
            if self.left_at is None and participant.admission_state != AdmissionState.ADMITTED:
                raise ValidationError({"participant": "Only admitted participants can open attendance."})
            session = participant.session
            if self.left_at is None and participant.role != participant.membership.role:
                raise ValidationError("The participant's role assignment has changed.")
            if self.left_at is None and participant.role == ClassroomRole.LEARNER and not Enrollment.objects.filter(
                user_id=participant.membership.user_id, course_id=session.classroom.course_id).exists():
                raise ValidationError("Learner attendance requires current course enrollment.")
            if self.left_at is None and (not participant.membership.is_active or session.status != LiveSession.Status.LIVE):
                raise ValidationError("Open attendance requires an active member and a live session.")
            if session.started_at and self.joined_at and self.joined_at < session.started_at:
                raise ValidationError({"joined_at": "Attendance cannot precede the session start."})
            if session.ended_at and (self.left_at is None or self.left_at > session.ended_at):
                raise ValidationError({"left_at": "Attendance must close by the session end."})
            if self.joined_at:
                overlaps = AttendanceInterval.objects.filter(participant_id=self.participant_id).exclude(pk=self.pk)
                overlaps = overlaps.filter(Q(left_at__isnull=True) | Q(left_at__gt=self.joined_at))
                if self.left_at:
                    overlaps = overlaps.filter(joined_at__lt=self.left_at)
                if overlaps.exists():
                    raise ValidationError("Attendance intervals must not overlap.")


class SessionAuditEvent(ValidatedClassroomModel):
    class EventType(models.TextChoices):
        CLASSROOM_CREATED = "CLASSROOM_CREATED", "Classroom created"
        CLASSROOM_INVITED = "CLASSROOM_INVITED", "Classroom invited"
        INVITATION_ACCEPTED = "INVITATION_ACCEPTED", "Invitation accepted"
        INVITATION_DECLINED = "INVITATION_DECLINED", "Invitation declined"
        INVITATION_REVOKED = "INVITATION_REVOKED", "Invitation revoked"
        INVITATION_EXPIRED = "INVITATION_EXPIRED", "Invitation expired"
        REQUESTED = "REQUESTED", "Admission requested"
        CREATED = "CREATED", "Created"
        STARTED = "STARTED", "Started"
        ENDED = "ENDED", "Ended"
        CANCELLED = "CANCELLED", "Cancelled"
        ADMITTED = "ADMITTED", "Admitted"
        DENIED = "DENIED", "Denied"
        REMOVED = "REMOVED", "Removed"
        ROLE_CHANGED = "ROLE_CHANGED", "Role changed"
        JOINED = "JOINED", "Joined"
        LEFT = "LEFT", "Left"

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True, blank=True,
                                   related_name="audit_events")
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name="session_audit_events")
    participant = models.ForeignKey(SessionParticipant, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="audit_events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [models.CheckConstraint(
            condition=Q(event_type__in=["CLASSROOM_CREATED", "CLASSROOM_INVITED", "INVITATION_ACCEPTED", "INVITATION_DECLINED",
                                       "INVITATION_REVOKED", "INVITATION_EXPIRED", "REQUESTED", "CREATED", "STARTED", "ENDED", "CANCELLED", "ADMITTED",
                                       "DENIED", "REMOVED", "ROLE_CHANGED", "JOINED", "LEFT"]),
            name="session_audit_valid_type"),
            models.CheckConstraint(condition=Q(classroom__isnull=False) | Q(session__isnull=False),
                                   name="session_audit_has_scope")]

    def clean(self):
        super().clean()
        if not self.classroom_id and not self.session_id:
            raise ValidationError("Audit events require a classroom or session.")
        if self.classroom_id and self.session_id and self.classroom_id != self.session.classroom_id:
            raise ValidationError({"classroom": "Audit classroom must match the session."})
        if self.participant_id and not self.session_id:
            raise ValidationError({"session": "Participant audit events require a session."})
        if self.participant_id and self.session_id and self.participant.session_id != self.session_id:
            raise ValidationError({"participant": "Participant must belong to the audited session."})
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Audit metadata must be an object."})


class Whiteboard(ValidatedClassroomModel):
    session = models.OneToOneField(LiveSession, on_delete=models.CASCADE, related_name="whiteboard")
    revision = models.PositiveBigIntegerField(default=0)
    objects_data = models.JSONField(default=dict, blank=True)
    editors = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    immutable_fields = ("session_id",)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(revision__gte=0), name="whiteboard_revision_nonnegative")]

    def clean(self):
        super().clean()
        from .whiteboard_services import validate_document
        validate_document(self.objects_data)
        if not isinstance(self.editors, dict) or len(self.editors) > 1000 or any(
                not isinstance(i, str) or not i.isascii() or not i.isdecimal() or not 0 < int(i) <= 9223372036854775807
                or not isinstance(stamp, str) or len(stamp) > 40 for i, stamp in self.editors.items()):
            raise ValidationError("Invalid whiteboard editors.")
        if self.editors and SessionParticipant.objects.filter(pk__in=list(self.editors), session_id=self.session_id,
                role=ClassroomRole.LEARNER).count() != len(self.editors):
            raise ValidationError("Editors must be learners in this session.")


class WhiteboardOperation(ValidatedClassroomModel):
    board = models.ForeignKey(Whiteboard, on_delete=models.CASCADE, related_name="operations")
    operation_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    revision = models.PositiveBigIntegerField()
    action = models.CharField(max_length=12)
    command = models.JSONField()
    inverse = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    immutable_fields = ("board_id", "operation_id", "actor_id", "revision", "action", "command", "inverse")

    def _classroom_lock_id(self, using):
        return Whiteboard.objects.using(using).values_list("session__classroom_id", flat=True).get(pk=self.board_id)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["board", "operation_id"], name="whiteboard_operation_unique"),
            models.UniqueConstraint(fields=["board", "revision"], name="whiteboard_revision_unique"),
            models.CheckConstraint(condition=Q(revision__gt=0), name="whiteboard_operation_positive"),
            models.CheckConstraint(condition=Q(action__in=["add", "erase", "undo", "clear", "permission"]), name="whiteboard_action_valid"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.command, dict) or not isinstance(self.inverse, dict):
            raise ValidationError("Operation data must be objects.")


class ClassroomChatMessage(ValidatedClassroomModel):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="chat_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    client_id = models.UUIDField()
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    immutable_fields = ("session_id", "sender_id", "client_id", "text", "created_at")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "client_id"], name="classroom_chat_retry_unique")]

    def clean(self):
        super().clean()
        from .classroom_validation import validate_plaintext
        validate_plaintext(self.text)
