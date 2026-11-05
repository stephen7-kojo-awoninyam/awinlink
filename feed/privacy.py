"""Linked profiles/events must remain readable when a post is delivered."""
from django.db.models import Q

from accounts.safety import blocked_user_ids
from events.visibility import visible_events_for
from talents.visibility import visible_talent_profiles_for
from .models import Post


def visible_association_posts_for(user):
    from accounts.age_safety import visible_users_for
    return Post.objects.filter(
        Q(talent__isnull=True) | Q(talent__in=visible_talent_profiles_for(user)),
        Q(event__isnull=True) | Q(event__in=visible_events_for(user)),
        author__in=visible_users_for(user),
    ).exclude(author_id__in=blocked_user_ids(user))
