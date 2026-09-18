from django.shortcuts import (
    get_object_or_404,
    redirect,
    render
)

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model

from notifications.models import Notification
from organizations.models import Organization
from messaging.models import (
    Conversation,
    ConversationParticipant
)
from .models import (
    Follow,
    OrganizationFollow,
    Connection
)


User = get_user_model()


# =========================================================
# FOLLOW USER
# =========================================================

@login_required
def follow_user(request, user_id):

    user_to_follow = get_object_or_404(
        User,
        id=user_id
    )

    # A user cannot follow themselves
    if request.user != user_to_follow:

        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=user_to_follow
        )

        # Notify only when a new follow is created
        if created:

            Notification.objects.create(
                user=user_to_follow,
                sender=request.user,
                notification_type="FOLLOW",
                message=(
                    f"{request.user.get_full_name()} "
                    f"{request.user.username} "
                    f"started following you."
                )
            )

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# UNFOLLOW USER
# =========================================================

@login_required
def unfollow_user(request, user_id):

    user_to_unfollow = get_object_or_404(
        User,
        id=user_id
    )

    Follow.objects.filter(
        follower=request.user,
        following=user_to_unfollow
    ).delete()

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# FOLLOW ORGANIZATION
# =========================================================

@login_required
def follow_organization(request, organization_id):

    organization = get_object_or_404(
        Organization,
        id=organization_id
    )

    follow, created = OrganizationFollow.objects.get_or_create(
        user=request.user,
        organization=organization
    )

    # Notify only for a new follow
    if created:

        if organization.user != request.user:

            Notification.objects.create(
                user=organization.user,
                sender=request.user,
                notification_type="FOLLOW",
                message=(
                    f"{request.user.get_full_name()} "
                    f"{request.user.username} "
                    f"started following "
                    f"{organization.name}."
                )
            )

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# UNFOLLOW ORGANIZATION
# =========================================================

@login_required
def unfollow_organization(request, organization_id):

    organization = get_object_or_404(
        Organization,
        id=organization_id
    )

    OrganizationFollow.objects.filter(
        user=request.user,
        organization=organization
    ).delete()

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# SEND CONNECTION REQUEST
# =========================================================

@login_required
def send_connection_request(request, user_id):

    receiver = get_object_or_404(
        User,
        id=user_id
    )

    # -----------------------------------------------------
    # CANNOT CONNECT WITH YOURSELF
    # -----------------------------------------------------

    if request.user == receiver:

        return redirect(
            request.META.get(
                "HTTP_REFERER",
                "/"
            )
        )

    # -----------------------------------------------------
    # CHECK REQUEST FROM CURRENT USER TO RECEIVER
    # -----------------------------------------------------

    existing_connection = Connection.objects.filter(
        sender=request.user,
        receiver=receiver
    ).first()

    # -----------------------------------------------------
    # CHECK REQUEST FROM RECEIVER TO CURRENT USER
    # -----------------------------------------------------

    reverse_connection = Connection.objects.filter(
        sender=receiver,
        receiver=request.user
    ).first()

    # =====================================================
    # CURRENT USER ALREADY SENT A REQUEST
    # =====================================================

    if existing_connection:

        # Already connected
        if existing_connection.status == "ACCEPTED":

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/"
                )
            )

        # Request already pending
        if existing_connection.status == "PENDING":

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/"
                )
            )

        # -------------------------------------------------
        # PREVIOUS REQUEST WAS REJECTED
        # -------------------------------------------------

        if existing_connection.status == "REJECTED":

            existing_connection.delete()

            Connection.objects.create(
                sender=request.user,
                receiver=receiver,
                status="PENDING"
            )

            Notification.objects.create(
                user=receiver,
                sender=request.user,
                notification_type="INVITATION",
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    f"sent you a connection request."
                )
            )

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/"
                )
            )

    # =====================================================
    # RECEIVER ALREADY SENT A REQUEST TO CURRENT USER
    # =====================================================

    if reverse_connection:

        # -------------------------------------------------
        # ALREADY CONNECTED
        # -------------------------------------------------

        if reverse_connection.status == "ACCEPTED":

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/"
                )
            )

        # -------------------------------------------------
        # THEY ALREADY SENT A PENDING REQUEST
        # -------------------------------------------------

        if reverse_connection.status == "PENDING":

            # Do NOT create another connection.
            #
            # The current user should accept or reject
            # the existing request.

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/"
                )
            )

        # -------------------------------------------------
        # THEIR PREVIOUS REQUEST WAS REJECTED
        # -------------------------------------------------

        if reverse_connection.status == "REJECTED":

            reverse_connection.delete()

    # =====================================================
    # CREATE NEW CONNECTION
    # =====================================================

    Connection.objects.create(
        sender=request.user,
        receiver=receiver,
        status="PENDING"
    )

    # =====================================================
    # NOTIFY RECEIVER
    # =====================================================

    Notification.objects.create(
        user=receiver,
        sender=request.user,
        notification_type="INVITATION",
        message=(
            f"{request.user.get_full_name() or request.user.username} "
            f"sent you a connection request."
        )
    )

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# ACCEPT CONNECTION REQUEST
# =========================================================

@login_required
def accept_connection_request(request, connection_id):

    connection = get_object_or_404(
        Connection,
        id=connection_id,
        receiver=request.user,
        status="PENDING"
    )

    connection.status = "ACCEPTED"

    connection.save()

    # -----------------------------------------------------
    # NOTIFY THE SENDER
    # -----------------------------------------------------

    Notification.objects.create(
        user=connection.sender,
        sender=request.user,
        notification_type="CONNECTION",
        message=(
            f"{request.user.get_full_name() or request.user.username} "
            f"accepted your connection request."
        )
    )

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# REJECT CONNECTION REQUEST
# =========================================================

@login_required
def reject_connection_request(request, connection_id):

    connection = get_object_or_404(
        Connection,
        id=connection_id,
        receiver=request.user,
        status="PENDING"
    )

    connection.status = "REJECTED"

    connection.save()

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# CANCEL CONNECTION REQUEST
# =========================================================

@login_required
def cancel_connection_request(request, connection_id):

    connection = get_object_or_404(
        Connection,
        id=connection_id,
        sender=request.user,
        status="PENDING"
    )

    connection.delete()

    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "/"
        )
    )


# =========================================================
# CONNECTIONS PAGE
# =========================================================

# ==========================================
# CONNECTIONS LIST
# ==========================================

# =========================================================
# CONNECTIONS & GROUPS PAGE
# =========================================================

@login_required
def connections_list(request):

    # -----------------------------------------------------
    # ACCEPTED CONNECTIONS SENT BY CURRENT USER
    # -----------------------------------------------------

    sent_accepted = Connection.objects.filter(
        sender=request.user,
        status="ACCEPTED"
    ).select_related(
        "receiver"
    )


    # -----------------------------------------------------
    # ACCEPTED CONNECTIONS RECEIVED BY CURRENT USER
    # -----------------------------------------------------

    received_accepted = Connection.objects.filter(
        receiver=request.user,
        status="ACCEPTED"
    ).select_related(
        "sender"
    )


    # -----------------------------------------------------
    # INCOMING CONNECTION REQUESTS
    # -----------------------------------------------------

    incoming_requests = Connection.objects.filter(
        receiver=request.user,
        status="PENDING"
    ).select_related(
        "sender"
    )


    # -----------------------------------------------------
    # OUTGOING CONNECTION REQUESTS
    # -----------------------------------------------------

    sent_requests = Connection.objects.filter(
        sender=request.user,
        status="PENDING"
    ).select_related(
        "receiver"
    )


    # -----------------------------------------------------
    # GROUPS THE CURRENT USER BELONGS TO
    # -----------------------------------------------------

    groups = (
        Conversation.objects
        .filter(
            is_group=True,
            participants__user=request.user
        )
        .prefetch_related(
            "participants__user"
        )
        .distinct()
        .order_by("-updated_at")
    )
        # -----------------------------------------------------
    # USERS AVAILABLE TO ADD TO GROUPS
    # -----------------------------------------------------

    available_users = User.objects.exclude(
        id=request.user.id
    ).order_by(
        "username"
    )


    return render(
        request,
        "connections/connections.html",
        {
            "sent_accepted": sent_accepted,

            "received_accepted": received_accepted,

            "incoming_requests": incoming_requests,

            "sent_requests": sent_requests,

            "groups": groups,
            
            "available_users": available_users,
        }
    )
    # ==========================================
# CREATE GROUP
# ==========================================

@login_required
def create_group(request):

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        user_ids = request.POST.getlist("user_ids")

        if not name:
            return redirect("connections_list")

        # Create the group
        conversation = Conversation.objects.create(
            is_group=True,
            name=name,
            created_by=request.user
        )

        # Creator is automatically a member
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=request.user
        )

        # Add selected members
        users = User.objects.filter(
            id__in=user_ids
        ).exclude(
            id=request.user.id
        )

        for user in users:
            ConversationParticipant.objects.create(
                conversation=conversation,
                user=user
            )

        return redirect(
            "messaging:conversation",
            conversation_id=conversation.id
        )

    return redirect("connections_list")
    
@login_required
def notification_list(request):

    # Mark all notifications as read when
    # the user opens the notifications page.
    Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(
        is_read=True
    )

    notifications = Notification.objects.filter(
        user=request.user
    ).select_related(
        "sender",
        "post",
        "opportunity",
        "conversation"
    )

    return render(
        request,
        "notifications/list.html",
        {
            "notifications": notifications
        }
    )    
    
# =========================================================
# REMOVE CONNECTION
# =========================================================

@login_required
def remove_connection(request, connection_id):

    connection = get_object_or_404(
        Connection,
        id=connection_id,
        status="ACCEPTED"
    )

    # Only people involved in the connection
    # can remove it.

    if (
        request.user != connection.sender
        and request.user != connection.receiver
    ):
        return redirect(
            "connections_list"
        )

    connection.delete()

    return redirect(
        "connections_list"
    )    