from django import template
from django.core.paginator import Paginator
from django.http import QueryDict
from organizations.roster_services import public_entries

register = template.Library()


@register.inclusion_tag("organizations/roster_badges.html", takes_context=True)
def organization_talent_badges(context, talent_id=None, organization_id=None):
    request = context.get("request")
    rows = public_entries(request.user if request else None)
    if talent_id is not None:
        rows = rows.filter(talent_id=talent_id)
    if organization_id is not None:
        rows = rows.filter(organization_id=organization_id)
    page = Paginator(rows, 50).get_page(request.GET.get("roster_page", 1) if request else 1)
    def page_url(number):
        query = request.GET.copy() if request else QueryDict(mutable=True)
        query["roster_page"] = number
        return "?" + query.urlencode()
    return {"entries": page.object_list, "show_talent": organization_id is not None,
            "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
            "next_url": page_url(page.next_page_number()) if page.has_next() else ""}
