from django.db import models
from django.conf import settings
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