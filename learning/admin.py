from django.contrib import admin

# Register your models here.
from .models import (
    LearningCategory,
    Course,
    Lesson,
    Enrollment,
    LessonProgress,
    Quiz,
    Question,
)



@admin.register(LearningCategory)
class LearningCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "created_at",
    )

    search_fields = (
        "name",
    )
    
    
class LessonInline(admin.TabularInline):

    model = Lesson

    extra = 1
    
    
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "creator",
        "category",
        "level",
        "status",
        "is_free",
        "created_at",
    )

    list_filter = (
        "category",
        "level",
        "status",
        "is_free",
    )

    search_fields = (
        "title",
        "description",
        "creator__username",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }

    inlines = [
        LessonInline
    ]
    
    
@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "course",
        "order",
        "duration",
    )

    list_filter = (
        "course",
    )

    ordering = (
        "course",
        "order",
    )
    
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "course",
        "completed",
        "enrolled_at",
    )

    list_filter = (
        "completed",
    )
    
    
@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):

    list_display = (
        "lesson",
        "enrollment",
        "completed",
    )

    list_filter = (
        "completed",
    )
    
    
class QuestionInline(admin.TabularInline):

    model = Question

    extra = 1
    
@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "lesson",
        "passing_score",
    )

    inlines = [
        QuestionInline
    ]
    
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):

    list_display = (
        "question",
        "quiz",
        "correct_answer",
    )                                
