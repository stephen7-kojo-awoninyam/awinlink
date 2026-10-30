from django.db import migrations


def seed_categories(apps, schema_editor):
    category = apps.get_model("learning", "LearningCategory")
    for name, description in (
        ("Sports", "Sports skills, coaching, fitness and athletic development."),
        ("Science and technology", "Science, engineering, computing and innovation."),
        ("Arts", "Visual arts, music, performance, design and creative practice."),
        ("Others", "Other skills, interests and areas of learning."),
    ):
        category.objects.using(schema_editor.connection.alias).get_or_create(
            name=name, defaults={"description": description}
        )


class Migration(migrations.Migration):
    dependencies = [("learning", "0013_classroom_chat")]
    # Retain categories on rollback: deleting them would cascade to courses.
    operations = [migrations.RunPython(seed_categories, migrations.RunPython.noop)]
