"""Presentation ordering for optional course sections, without changing stored lesson order."""


def group_course_lessons(course, lessons=None):
    items = list(lessons if lessons is not None else course.lessons.all().order_by('order', 'pk'))
    modules = list(course.modules.all())
    if not modules:
        return items, []

    by_module = {module.pk: [] for module in modules}
    unassigned = []
    for lesson in items:
        module_id = getattr(lesson, 'module_id', None)
        if module_id in by_module:
            by_module[module_id].append(lesson)
        else:
            unassigned.append(lesson)

    sections = [
        {'module': module, 'title': module.title, 'lessons': by_module[module.pk]}
        for module in modules if by_module[module.pk]
    ]
    if unassigned:
        sections.append({'module': None, 'title': 'Other lessons', 'lessons': unassigned})
    return [lesson for section in sections for lesson in section['lessons']], sections
