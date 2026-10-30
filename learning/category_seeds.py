"""Default course categories. Seeding never changes existing categories or courses."""

COURSE_CATEGORIES = (
    ("Sports", "Sports skills, coaching, fitness and athletic development."),
    ("Science and technology", "Science, engineering, computing and innovation."),
    ("Arts", "Visual arts, music, performance, design and creative practice."),
    ("Others", "Other skills, interests and areas of learning."),
)


def seed_course_categories(model, using="default"):
    created = 0
    for name, description in COURSE_CATEGORIES:
        _, added = model.objects.using(using).get_or_create(
            name=name, defaults={"description": description}
        )
        created += added
    return created
