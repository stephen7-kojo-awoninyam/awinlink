from django.shortcuts import render
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import (
    Post,
    PostLike,
    SavedPost,
    SharedPost,
)
from .forms import PostForm
from .forms import CommentForm
from notifications.models import Notification
# Create your views here.

@login_required
def create_post(request):


    if request.method == "POST":


        form = PostForm(

            request.POST,

            request.FILES

        )


        if form.is_valid():


            post = form.save(

                commit=False

            )


            post.author = request.user
            
                        # Check if user is a talent

            if hasattr(
                request.user,
                "talent_profile"
            ):

                post.talent = request.user.talent_profile



            # Check if user represents organization

            if hasattr(
                request.user,
                "organization_profile"
            ):

                post.organization = request.user.organization_profile


            post.save()


            return redirect(

                "home_feed"

            )



    else:


        form = PostForm()



    return render(

        request,

        "feed/create_post.html",

        {

            "form": form

        }

    )
    



@login_required
def like_post(request, post_id):

    post = get_object_or_404(
        Post,
        id=post_id
    )

    like, created = PostLike.objects.get_or_create(
        user=request.user,
        post=post
    )
    liked = True

    if created:

        # Don't notify yourself
        if post.author != request.user:

            Notification.objects.create(

                user=post.author,

                sender=request.user,

                notification_type="LIKE",

                message=f"{request.user.get_full_name()} liked your post.",

                post=post

            )

    else:

        like.delete()
        liked = False

    accept_header = request.headers.get("accept", "").lower()
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if is_ajax or "application/json" in accept_header:
        return JsonResponse({
            "status": "success",
            "liked": liked,
            "count": post.likes.count(),
        })

    return redirect("home_feed")
    
    
    





@login_required
def add_comment(request, post_id):

    post = get_object_or_404(
        Post,
        id=post_id
    )

    if request.method == "POST":

        form = CommentForm(request.POST)

        if form.is_valid():

            comment = form.save(commit=False)

            comment.user = request.user

            comment.post = post

            comment.save()

            if post.author != request.user:

                Notification.objects.create(

                    user=post.author,

                    sender=request.user,

                    notification_type="COMMENT",

                    message=f"{request.user.get_full_name()} commented on your post.",

                    post=post

                )

            accept_header = request.headers.get("accept", "").lower()
            is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

            if is_ajax or "application/json" in accept_header:
                return JsonResponse({
                    "status": "success",
                    "comment": {
                        "user": comment.user.get_full_name() or comment.user.username,
                        "text": comment.text,
                        "created_at": comment.created_at.strftime("%b %d, %Y %H:%M"),
                    },
                    "count": post.comments.count(),
                })

            return redirect("home_feed")

        accept_header = request.headers.get("accept", "").lower()
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if is_ajax or "application/json" in accept_header:
            return JsonResponse({
                "status": "error",
                "message": "Invalid comment.",
                "errors": form.errors,
            }, status=400)

    return redirect("home_feed")




# ==========================================
# SAVE / UNSAVE POST
# ==========================================

@login_required
def save_post(request, post_id):

    post = get_object_or_404(
        Post,
        id=post_id
    )

    saved_post, created = SavedPost.objects.get_or_create(
        user=request.user,
        post=post
    )

    # If already saved, remove it
    if not created:

        saved_post.delete()

    return redirect("home_feed")


# ==========================================
# SHARE / REPOST POST
# ==========================================

@login_required
def share_post(request, post_id):

    post = get_object_or_404(
        Post,
        id=post_id
    )

    if request.method == "POST":

        caption = request.POST.get(
            "caption",
            ""
        ).strip()

        SharedPost.objects.create(
            user=request.user,
            post=post,
            caption=caption
        )

        # Don't notify yourself
        if post.author != request.user:

            Notification.objects.create(

                user=post.author,

                sender=request.user,

                notification_type="SHARE",

                message=(
                    f"{request.user.get_full_name()} "
                    f"shared your post."
                ),

                post=post

            )

    return redirect("home_feed")