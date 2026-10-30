"""Map the creator's active profile to an existing learning category."""
from .models import LearningCategory


def creator_course_category(user):
    if getattr(user, "role", None) == "ORGANIZATION":
        profile = getattr(user, "organization_profile", None)
        category = getattr(profile, "category", None)
        name = getattr(category, "name", "")
        name = {"Science & Technology": "Science and technology"}.get(name, name)
        return LearningCategory.objects.filter(name=name).first() if name else None
    profile_fields = {
        "ATHLETE": ("talent_profile", "talent_category"),
        "COACH": ("coach_profile", "coach_category"),
        "SCOUT": ("scout_profile", "scout_category"),
    }
    relation = profile_fields.get(getattr(user, "role", None))
    if not relation:
        return None
    profile = getattr(user, relation[0], None)
    name = {
        "SPORTS": "Sports",
        "SCIENCE_TECHNOLOGY": "Science and technology",
        "ARTS": "Arts",
        "OTHERS": "Others",
    }.get(getattr(profile, relation[1], None))
    if not name:
        return None
    return LearningCategory.objects.filter(name=name).first()
