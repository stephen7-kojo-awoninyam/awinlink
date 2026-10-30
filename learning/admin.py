from django.contrib import admin
from django import forms

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


class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        is_free = cleaned.get("is_free", getattr(self.instance, "is_free", True))
        status = cleaned.get("status", getattr(self.instance, "status", "DRAFT"))
        if not self.instance.pk and not is_free:
            self.add_error("is_free", "Paid courses cannot be created until Learning billing is available.")
        elif self.instance.pk and is_free != self.instance.is_free:
            self.add_error("is_free", "A course's free or paid status cannot be changed after creation.")
        elif not is_free and self.instance.status != "APPROVED" and status == "APPROVED":
            self.add_error("status", "Paid courses cannot be published until Learning billing is available.")
        return cleaned



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
    form = CourseAdminForm

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
