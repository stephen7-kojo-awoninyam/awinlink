from django.contrib import admin
from .models import Skill, SkillCategory
# Register your models here.

admin.site.register(SkillCategory)

admin.site.register(Skill)
