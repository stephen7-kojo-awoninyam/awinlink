from django.shortcuts import render
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
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