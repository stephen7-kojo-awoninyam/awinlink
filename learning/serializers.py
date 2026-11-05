from rest_framework import serializers

from .models import (
    LearningCategory,
    Course,
    CourseModule,
    CourseReview,
    Certificate,
    Lesson,
    Enrollment,
    LessonProgress,
    Quiz,
    Question,
    QuizAttempt,
)


# ============================================================
# LEARNING CATEGORY
# ============================================================

class LessonCompletionInput(serializers.Serializer):
    completed = serializers.BooleanField(default=True)


class QuizAttemptInput(serializers.Serializer):
    answers = serializers.DictField(child=serializers.ChoiceField(choices=['A', 'B', 'C', 'D']), default=dict)


class CourseRejectionInput(serializers.Serializer):
    rejection_reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_rejection_reason(self, value):
        if not isinstance(self.initial_data.get('rejection_reason'), str):
            raise serializers.ValidationError('A rejection reason must be text.')
        return value


class LearningCategorySerializer(serializers.ModelSerializer):

    course_count = serializers.SerializerMethodField()
    is_default = serializers.SerializerMethodField()

    def get_is_default(self, obj):
        return obj.pk == self.context.get("default_category_id")

    class Meta:
        model = LearningCategory

        fields = [
            "id",
            "name",
            "description",
            "icon",
            "course_count",
            "is_default",
            "created_at",
        ]

        read_only_fields = [
            "created_at",
        ]

    def get_course_count(self, obj):
        return obj.courses.filter(
            status="APPROVED"
        ).count()


# ============================================================
# COURSE
# ============================================================

class CourseSerializer(serializers.ModelSerializer):

    creator_name = serializers.SerializerMethodField()

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    lesson_count = serializers.SerializerMethodField()

    enrollment_count = serializers.SerializerMethodField()

    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Course

        fields = [
            "id",
            "creator",
            "creator_name",
            "category",
            "category_name",
            "title",
            "slug",
            "description",
            "thumbnail",
            "level",
            "duration",
            "is_free",
            "minimum_age",
            "status",
            "rejection_reason",
            "lesson_count",
            "enrollment_count",
            "average_rating",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "creator",
            "status",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]

    def get_creator_name(self, obj):

        return (
            obj.creator.get_full_name()
            or obj.creator.username
        )

    def get_lesson_count(self, obj):
        return obj.lessons.count()

    def get_enrollment_count(self, obj):
        return obj.enrollments.count()

    def get_average_rating(self, obj):

        reviews = obj.reviews.all()

        if not reviews.exists():
            return 0

        total = sum(
            review.rating
            for review in reviews
        )

        return round(
            total / reviews.count(),
            2
        )


# ============================================================
# LESSON
# ============================================================

class LessonSerializer(serializers.ModelSerializer):

    course_title = serializers.CharField(
        source="course.title",
        read_only=True
    )
    module_title = serializers.CharField(source="module.title", read_only=True, allow_null=True)

    class Meta:
        model = Lesson

        fields = [
            "id",
            "course",
            "course_title",
            "module",
            "module_title",
            "title",
            "description",
            "video",
            "notes",
            "captions",
            "caption_language",
            "transcript",
            "order",
            "duration",
            "created_at",
        ]

        read_only_fields = [
            "created_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        course = attrs.get('course') or getattr(self.instance, 'course', None)
        module = attrs.get('module', getattr(self.instance, 'module', None))
        if module and course and module.course_id != course.pk:
            raise serializers.ValidationError({'module': 'Choose a module from this lesson course.'})
        return attrs


class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ['id', 'course', 'title', 'description', 'order', 'created_at']
        read_only_fields = ['id', 'course', 'created_at']

    def validate_order(self, value):
        if value < 1:
            raise serializers.ValidationError('Module order must be at least 1.')
        return value


class StudioQuizInput(serializers.Serializer):
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    passing_score = serializers.IntegerField(min_value=1, max_value=100, default=70)


class StudioQuestionInput(serializers.Serializer):
    question = serializers.CharField(trim_whitespace=True)
    option_a = serializers.CharField(max_length=250, trim_whitespace=True)
    option_b = serializers.CharField(max_length=250, trim_whitespace=True)
    option_c = serializers.CharField(max_length=250, trim_whitespace=True)
    option_d = serializers.CharField(max_length=250, trim_whitespace=True)
    correct_answer = serializers.ChoiceField(choices=('A', 'B', 'C', 'D'))


class StudioQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'quiz', 'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer']
        read_only_fields = ['id', 'quiz']


# ============================================================
# ENROLLMENT
# ============================================================

class EnrollmentSerializer(serializers.ModelSerializer):

    course_title = serializers.CharField(
        source="course.title",
        read_only=True
    )

    course_thumbnail = serializers.ImageField(
        source="course.thumbnail",
        read_only=True
    )

    lesson_count = serializers.SerializerMethodField()

    completed_lessons = serializers.SerializerMethodField()

    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment

        fields = [
            "id",
            "user",
            "course",
            "course_title",
            "course_thumbnail",
            "enrolled_at",
            "completed",
            "completed_at",
            "lesson_count",
            "completed_lessons",
            "progress_percentage",
        ]

        read_only_fields = [
            "user",
            "enrolled_at",
            "completed",
            "completed_at",
        ]

    def get_lesson_count(self, obj):
        return obj.course.lessons.count()

    def get_completed_lessons(self, obj):

        return obj.lesson_progress.filter(
            completed=True
        ).count()

    def get_progress_percentage(self, obj):

        total = obj.course.lessons.count()

        if total == 0:
            return 0

        completed = obj.lesson_progress.filter(
            completed=True
        ).count()

        return round(
            (completed / total) * 100,
            2
        )


# ============================================================
# LESSON PROGRESS
# ============================================================

class LessonProgressSerializer(serializers.ModelSerializer):

    lesson_title = serializers.CharField(
        source="lesson.title",
        read_only=True
    )

    class Meta:
        model = LessonProgress

        fields = [
            "id",
            "enrollment",
            "lesson",
            "lesson_title",
            "completed",
            "completed_at",
        ]

        read_only_fields = [
            "completed_at",
        ]


# ============================================================
# COURSE REVIEW
# ============================================================

class CourseReviewSerializer(serializers.ModelSerializer):

    user_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseReview

        fields = [
            "id",
            "course",
            "user",
            "user_name",
            "rating",
            "review",
            "created_at",
        ]

        read_only_fields = [
            "user",
            "created_at",
        ]

    def get_user_name(self, obj):

        return (
            obj.user.get_full_name()
            or obj.user.username
        )

    def validate_rating(self, value):

        if value < 1 or value > 5:
            raise serializers.ValidationError(
                "Rating must be between 1 and 5."
            )

        return value
# =========================================================   
# COURSE CREATE
# =========================================================

class CourseCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Course

        fields = [
            "category",
            "title",
            "slug",
            "description",
            "thumbnail",
            "level",
            "duration",
            "is_free",
            "minimum_age",
        ]

    def validate(self, attrs):
        requested_free = attrs.get("is_free", self.instance.is_free if self.instance else True)
        if self.instance is None and not requested_free:
            raise serializers.ValidationError({
                "is_free": "Paid courses cannot be created until Learning billing is available."
            })
        if self.instance is not None and "is_free" in attrs and requested_free != self.instance.is_free:
            raise serializers.ValidationError({
                "is_free": "A course's free or paid status cannot be changed after creation."
            })
        return attrs

    def create(self, validated_data):

        request = self.context.get("request")

        if request and request.user.is_authenticated:
            validated_data["creator"] = request.user

        return super().create(validated_data)    


# ============================================================
# CERTIFICATE
# ============================================================

class CertificateSerializer(serializers.ModelSerializer):

    course_id = serializers.IntegerField(source='enrollment.course_id', read_only=True)

    course_title = serializers.CharField(
        source="enrollment.course.title",
        read_only=True
    )

    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Certificate

        fields = [
            "id",
            "enrollment",
            "certificate_id",
            "course_title",
            "course_id",
            "user_name",
            "issued_at",
            "pdf",
        ]

        read_only_fields = [
            "certificate_id",
            "issued_at",
        ]

    def get_user_name(self, obj):

        return (
            obj.enrollment.user.get_full_name()
            or obj.enrollment.user.username
        )


# ============================================================
# QUIZ
# ============================================================

class QuizSerializer(serializers.ModelSerializer):

    lesson_title = serializers.CharField(
        source="lesson.title",
        read_only=True
    )

    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz

        fields = [
            "id",
            "lesson",
            "lesson_title",
            "title",
            "passing_score",
            "question_count",
        ]

    def get_question_count(self, obj):
        return obj.questions.count()


# ============================================================
# QUESTION
# ============================================================

class QuestionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question

        fields = [
            "id",
            "quiz",
            "question",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
        ]


# ============================================================
# QUIZ ATTEMPT
# ============================================================

class QuizAttemptSerializer(serializers.ModelSerializer):

    quiz_title = serializers.CharField(
        source="quiz.title",
        read_only=True
    )
    lesson_id = serializers.IntegerField(source="quiz.lesson_id", read_only=True)
    passing_score = serializers.IntegerField(source="quiz.passing_score", read_only=True)

    class Meta:
        model = QuizAttempt

        fields = [
            "id",
            "enrollment",
            "quiz",
            "quiz_title",
            "lesson_id",
            "passing_score",
            "score",
            "total_questions",
            "percentage",
            "passed",
            "attempted_at",
        ]

        read_only_fields = [
            "score",
            "total_questions",
            "percentage",
            "passed",
            "attempted_at",
        ]
