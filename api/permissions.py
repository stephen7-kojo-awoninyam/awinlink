from rest_framework.permissions import BasePermission
from organizations.permissions import has_active_organization


class IsAthlete(BasePermission):

    message = "Only athletes can access this endpoint."

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "ATHLETE"
        )


class IsOrganization(BasePermission):

    message = "Only organizations can access this endpoint."

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "ORGANIZATION"
            and has_active_organization(request.user)
        )


class IsScout(BasePermission):

    message = "Only scouts can access this endpoint."

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "SCOUT"
        )


class IsCoach(BasePermission):

    message = "Only coaches can access this endpoint."

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "COACH"
        )


class IsAdmin(BasePermission):

    message = "Only administrators can access this endpoint."

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "ADMIN"
        )
        
        
class IsTalentRecruiter(BasePermission):

    message = (
        "Only organizations, scouts, or coaches "
        "can access this endpoint."
    )

    def has_permission(self, request, view):

        return (
            request.user
            and request.user.is_authenticated
            and (request.user.role != "ORGANIZATION" or has_active_organization(request.user))
            and request.user.role in [
                "ORGANIZATION",
                "SCOUT",
                "COACH",
            ]
        )        