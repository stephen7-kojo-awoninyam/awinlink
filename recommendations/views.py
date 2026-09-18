from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from opportunities.models import Opportunity

from .services import RecommendationEngine



# Create your views here.


@login_required
def recommendations(request, opportunity_id):

    opportunity = get_object_or_404(
        Opportunity,
        id=opportunity_id
    )


    # Make sure the logged-in user owns this opportunity

    if opportunity.organization.user != request.user:

        return render(
            request,
            "403.html"
        )


    organization = opportunity.organization

    results = RecommendationEngine.generate_for_organization(
        organization,
        opportunity
    )


    return render(
        request,
        "recommendations/results.html",
        {
            "opportunity": opportunity,
            "results": results
        }
    )