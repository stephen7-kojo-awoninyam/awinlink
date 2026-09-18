from django.contrib import admin

# Register your models here.

from .models import Opportunity, OpportunityRequirement


admin.site.register(OpportunityRequirement)
