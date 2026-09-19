from django.db.models import Q
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from connections.models import (
    Follow,
    OrganizationFollow,
    Connection,
)

from feed.models import Post, SavedPost, SharedPost
from opportunities.models import Opportunity
from recommendations.services import RecommendationEngine
from talents.models import TalentProfile
from organizations.models import Organization
from domains.models import TalentDomain
from skills.models import Skill

from events.models import Event
from learning.models import Course as LearningContent



# =====================================
# PUBLIC HOME PAGE
# =====================================
def home(request):

    if request.user.is_authenticated:
        return redirect("home_feed")

    return render(
        request,
        "core/home.html"
    )


# =====================================
# AWINLINK HOME FEED
# =====================================

@login_required
def home_feed(request):

    # ==================================
    # USERS I FOLLOW
    # ==================================

    following_users = Follow.objects.filter(
        follower=request.user
    ).values_list(
        "following_id",
        flat=True
    )


    # ==================================
    # ORGANIZATIONS I FOLLOW
    # ==================================

    following_organizations = OrganizationFollow.objects.filter(
        user=request.user
    ).values_list(
        "organization__user_id",
        flat=True
    )


    # ==================================
    # MY PROFESSIONAL CONNECTIONS
    # ==================================

    sent_connections = Connection.objects.filter(
        sender=request.user,
        status="ACCEPTED"
    ).values_list(
        "receiver_id",
        flat=True
    )


    received_connections = Connection.objects.filter(
        receiver=request.user,
        status="ACCEPTED"
    ).values_list(
        "sender_id",
        flat=True
    )


    connection_users = (
        list(sent_connections)
        +
        list(received_connections)
    )


    # ==================================
    # FEED AUTHORS
    # ==================================

    feed_authors = (
        list(following_users)
        +
        connection_users
        +
        list(following_organizations)
    )


    # Remove duplicates
    feed_authors = list(
        set(feed_authors)
    )


    # ==================================
    # POSTS
    # ==================================

    posts = Post.objects.filter(

        Q(
            author=request.user
        )

        |

        Q(
            author_id__in=feed_authors,
            visibility="PUBLIC"
        )

        |

        Q(
            author_id__in=following_users,
            visibility="FOLLOWERS"
        )

        |

        Q(
            author_id__in=following_organizations,
            visibility="ORGANIZATIONS"
        )

    ).select_related(

        "author",
        "talent",
        "organization",
        "event"

    ).distinct().order_by(

        "-created_at"

    )


    # ==================================
    # SHARED / REPOSTED POSTS
    # ==================================

    shared_posts = SharedPost.objects.filter(

        # The person who shared it is in our network
        user_id__in=feed_authors

    ).filter(

        # ==================================
        # ORIGINAL POST VISIBILITY
        # ==================================

        Q(
            post__visibility="PUBLIC"
        )

        |

        Q(
            post__author_id__in=following_users,
            post__visibility="FOLLOWERS"
        )

        |

        Q(
            post__author_id__in=following_organizations,
            post__visibility="ORGANIZATIONS"
        )

    ).select_related(

        "user",
        "post",
        "post__author",
        "post__talent",
        "post__organization",
        "post__event"

    )


    # ==================================
    # MY SHARED / REPOSTED POSTS
    # ==================================

    my_shared_posts = SharedPost.objects.filter(

        user=request.user

    ).select_related(

        "user",
        "post",
        "post__author",
        "post__talent",
        "post__organization",
        "post__event"

    )


    # ==================================
    # COMBINE SHARED POSTS
    # ==================================

    shared_posts = (

        shared_posts

        |

        my_shared_posts

    ).distinct().order_by(

        "-created_at"

    )


    # ==================================
    # BUILD UNIFIED FEED
    # ==================================

    feed_items = []


    # Original posts

    for post in posts:

        feed_items.append({

            "type": "POST",

            "object": post,

            "created_at": post.created_at

        })


    # Shared posts

    for shared_post in shared_posts:

        feed_items.append({

            "type": "SHARE",

            "object": shared_post,

            "created_at": shared_post.created_at

        })


    # ==================================
    # SORT ENTIRE FEED
    # ==================================
    # ==================================
    # PERSONALIZED FEED RANKING
    # ==================================

    for item in feed_items:

        if item["type"] == "POST":

            item["score"] = RecommendationEngine.score_post_for_user(
                request.user,
                item["object"]
            )

        elif item["type"] == "SHARE":

            shared_post = item["object"]

            # Score the original post
            item["score"] = RecommendationEngine.score_post_for_user(
                request.user,
                shared_post.post
            )

            # Small bonus for the person who shared it
            if shared_post.user_id in feed_authors:
                item["score"] += 10

    # ==================================
    # SORT BY PERSONALIZED SCORE
    # ==================================

    feed_items.sort(
        key=lambda item: (
            item["score"],
            item["created_at"]
        ),
        reverse=True
    )


    # ==================================
    # SAVED POSTS
    # ==================================

    saved_post_ids = set(

        SavedPost.objects.filter(

            user=request.user,

            post__in=posts

        ).values_list(

            "post_id",

            flat=True

        )

    )


    # ==================================
    # EVENTS
    # ==================================

    events = Event.objects.filter(

        status="PUBLISHED"

    ).select_related(

        "organizer",
        "category"

    ).order_by(

        "-created_at"

    )[:5]


    # ==================================
    # LEARNING CONTENT
    # ==================================

    learning_content = LearningContent.objects.filter(
        status="APPROVED"
    ).select_related(
        "category",
        "creator"
    ).order_by(
        "-created_at"
    )[:5]


    # ==================================
    # OPPORTUNITIES
    # ==================================

    # ==================================
    # RECOMMENDED OPPORTUNITIES
    # ==================================

    opportunity_candidates = Opportunity.objects.filter(
        active=True
    ).select_related(
        "organization"
    )


    # ==================================
    # SCORE OPPORTUNITIES
    # ==================================

    opportunity_scores = []

    for opportunity in opportunity_candidates:

        score = RecommendationEngine.score_opportunity_for_user(
            request.user,
            opportunity
        )

        opportunity.recommendation_score = score

        opportunity_scores.append(
            opportunity
        )


    # ==================================
    # SORT OPPORTUNITIES
    # ==================================

    opportunity_scores.sort(
        key=lambda opportunity: (
            opportunity.recommendation_score,
            opportunity.created_at
        ),
        reverse=True
    )


    # ==================================
    # TOP 5 OPPORTUNITIES
    # ==================================

    opportunities = opportunity_scores[:5]


    # ==================================
    # RECOMMENDED TALENTS
    # ==================================

    # ==================================
    # RECOMMENDED TALENTS
    # ==================================

    # Talents Stephen already follows
    followed_talent_ids = Follow.objects.filter(
        follower=request.user
    ).values_list(
        "following_id",
        flat=True
    )


    # Talents Stephen is already connected to
    connected_talent_ids = Connection.objects.filter(
        Q(
            sender=request.user,
            status="ACCEPTED"
        )
        |
        Q(
            receiver=request.user,
            status="ACCEPTED"
        )
    ).values_list(
        "sender_id",
        "receiver_id"
    )


    connected_user_ids = set()

    for sender_id, receiver_id in connected_talent_ids:

        if sender_id != request.user.id:
            connected_user_ids.add(sender_id)

        if receiver_id != request.user.id:
            connected_user_ids.add(receiver_id)


    # ==================================
    # TALENT CANDIDATES
    # ==================================

    talent_candidates = TalentProfile.objects.exclude(
        user=request.user
    ).exclude(
        user_id__in=followed_talent_ids
    ).exclude(
        user_id__in=connected_user_ids
    ).select_related(
        "user"
    )


    # ==================================
    # SCORE TALENTS
    # ==================================

    talent_scores = []

    for talent in talent_candidates:

        score = RecommendationEngine.score_talent_for_user(
            request.user,
            talent
        )

        talent.recommendation_score = score

        talent_scores.append(talent)


    # ==================================
    # SORT TALENTS
    # ==================================

    talent_scores.sort(
        key=lambda talent: (
            talent.recommendation_score,
            talent.created_at
        ),
        reverse=True
    )


    recommended_talents = talent_scores[:5]
    # =====================================
    # CONNECTION STATUS
    # =====================================

    for talent in recommended_talents:

        connection = Connection.objects.filter(
            sender=request.user,
            receiver=talent.user
        ).first()

        if not connection:

            connection = Connection.objects.filter(
                sender=talent.user,
                receiver=request.user
            ).first()

        # Attach connection directly to talent
        talent.connection = connection

    # ==================================
    # RECOMMENDED ORGANIZATIONS
    # ==================================

    # ==================================
    # RECOMMENDED ORGANIZATIONS
    # ==================================

    # Organizations Stephen already follows
    followed_organization_ids = OrganizationFollow.objects.filter(
        user=request.user
    ).values_list(
        "organization_id",
        flat=True
    )


    # ==================================
    # ORGANIZATION CANDIDATES
    # ==================================

    organization_candidates = Organization.objects.exclude(
        user=request.user
    ).exclude(
        id__in=followed_organization_ids
    ).select_related(
        "category",
        "domain"
    )


    # ==================================
    # SCORE ORGANIZATIONS
    # ==================================

    organization_scores = []

    for organization in organization_candidates:

        score = RecommendationEngine.score_organization_for_user(
            request.user,
            organization
        )

        organization.recommendation_score = score

        organization_scores.append(
            organization
        )


    # ==================================
    # SORT ORGANIZATIONS
    # ==================================

    organization_scores.sort(
        key=lambda organization: (
            organization.recommendation_score,
            organization.created_at
        ),
        reverse=True
    )


    recommended_organizations = organization_scores[:5]


    # ==================================
    # CONTEXT
    # ==================================

    context = {

        "feed_items": feed_items,

        "events": events,

        "learning_content": learning_content,

        "opportunities": opportunities,

        "recommended_talents": recommended_talents,

        "recommended_organizations": recommended_organizations,

        "saved_post_ids": saved_post_ids,
        
   

    }


    return render(

        request,

        "core/home_feed.html",

        context

    )

# =====================================
# EXPLORE
# =====================================

@login_required
def explore(request):

    trending_posts = Post.objects.order_by(
        "-views",
        "-created_at"
    )[:10]


    featured_talents = TalentProfile.objects.filter(
        verified=True
    ).select_related(
        "user"
    ).order_by(
        "-created_at"
    )[:8]


    featured_organizations = Organization.objects.filter(
        verified=True
    ).order_by(
        "-created_at"
    )[:8]


    opportunities = Opportunity.objects.filter(
        active=True
    ).order_by(
        "-created_at"
    )[:8]


    events = Event.objects.filter(
        status="PUBLISHED"
    ).order_by(
        "-created_at"
    )[:8]


    learning_content = LearningContent.objects.filter(
        published=True
    ).order_by(
        "-created_at"
    )[:8]


    domains = TalentDomain.objects.all()


    skills = Skill.objects.all().order_by(
        "name"
    )[:20]


    context = {

        "trending_posts": trending_posts,

        "featured_talents": featured_talents,

        "featured_organizations": featured_organizations,

        "opportunities": opportunities,

        "events": events,

        "learning_content": learning_content,

        "domains": domains,

        "skills": skills,

    }


    return render(
        request,
        "core/explore.html",
        context
    )

