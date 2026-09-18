from django import forms

from .models import (
    LearningCategory,
    Course,
    Lesson,
    CourseReview,
    Quiz,
    Question,
)


# =========================================================
# LEARNING CATEGORY FORM
# =========================================================

class LearningCategoryForm(forms.ModelForm):

    class Meta:
        model = LearningCategory

        fields = [
            "name",
            "description",
            "icon",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Category name"
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Category description"
                }
            ),

            "icon": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Icon class or name"
                }
            ),
        }


# =========================================================
# COURSE FORM
# =========================================================

class CourseForm(forms.ModelForm):

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
        ]

        widgets = {
            "category": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Course title"
                }
            ),

            "slug": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "course-slug"
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Describe the course"
                }
            ),

            "thumbnail": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
                }
            ),

            "level": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "duration": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Duration in minutes"
                }
            ),

            "is_free": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input"
                }
            ),
        }


# =========================================================
# LESSON FORM
# =========================================================

class LessonForm(forms.ModelForm):

    class Meta:
        model = Lesson

        fields = [
            "title",
            "description",
            "video",
            "notes",
            "order",
            "duration",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Lesson title"
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Lesson description"
                }
            ),

            "video": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
                }
            ),

            "notes": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
                }
            ),

            "order": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1
                }
            ),

            "duration": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Duration in minutes"
                }
            ),
        }


# =========================================================
# COURSE REVIEW FORM
# =========================================================

class CourseReviewForm(forms.ModelForm):

    class Meta:
        model = CourseReview

        fields = [
            "rating",
            "review",
        ]

        widgets = {
            "rating": forms.Select(
                choices=[
                    (1, "1 - Poor"),
                    (2, "2 - Fair"),
                    (3, "3 - Good"),
                    (4, "4 - Very Good"),
                    (5, "5 - Excellent"),
                ],
                attrs={
                    "class": "form-select"
                }
            ),

            "review": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Share your experience with this course..."
                }
            ),
        }


# =========================================================
# QUIZ FORM
# =========================================================

class QuizForm(forms.ModelForm):

    class Meta:
        model = Quiz

        fields = [
            "title",
            "passing_score",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Quiz title"
                }
            ),

            "passing_score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1,
                    "max": 100
                }
            ),
        }


# =========================================================
# QUESTION FORM
# =========================================================

class QuestionForm(forms.ModelForm):

    class Meta:
        model = Question

        fields = [
            "question",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_answer",
        ]

        widgets = {
            "question": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Enter question"
                }
            ),

            "option_a": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Option A"
                }
            ),

            "option_b": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Option B"
                }
            ),

            "option_c": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Option C"
                }
            ),

            "option_d": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Option D"
                }
            ),

            "correct_answer": forms.Select(
                choices=[
                    ("A", "Option A"),
                    ("B", "Option B"),
                    ("C", "Option C"),
                    ("D", "Option D"),
                ],
                attrs={
                    "class": "form-select"
                }
            ),
        }