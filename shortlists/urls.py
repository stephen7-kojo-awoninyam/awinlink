from django.urls import path
from . import views


urlpatterns = [
        path(
            "",
            views.organization_shortlist,
            name="organization_shortlist"
        ),
        path(
            "toggle-star/<int:talent_id>/",
            views.toggle_star,
            name="toggle_star"
        ),
        
        path(
            "update-notes/<int:talent_id>/",
            views.update_notes,
            name="update_notes"
        ),
        path(
        "add/<int:talent_id>/",
        views.add_to_shortlist,
        name="add_to_shortlist"
       ),
        path(
        "remove/<int:talent_id>/",
        views.remove_from_shortlist,
        name="remove_from_shortlist"
       ),
]