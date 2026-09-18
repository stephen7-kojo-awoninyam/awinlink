from django.db import models

# Create your models here.

from django.db import models
from django.conf import settings



class Post(models.Model):


    POST_TYPES = (

        ("SHOWCASE", "Talent Showcase"),

        ("TRAINING", "Training"),

        ("ACHIEVEMENT", "Achievement"),

        ("NEWS", "News"),

        ("ANNOUNCEMENT", "Announcement"),

        ("GENERAL", "General"),

    )
    
    VISIBILITY_CHOICES = (

        ("PUBLIC", "Public"),

        ("FOLLOWERS", "Followers Only"),

        ("ORGANIZATIONS", "Organizations Only"),

        ("PRIVATE", "Private"),

    )
    
    
    visibility = models.CharField(

    max_length=20,

    choices=VISIBILITY_CHOICES,

    default="PUBLIC"

    )
    
    location = models.CharField(

    max_length=100,

    blank=True

   )


    author = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="posts"

    )
    
    talent = models.ForeignKey(

        "talents.TalentProfile",

        on_delete=models.CASCADE,

        null=True,

        blank=True,

        related_name="posts"

    )


    # NEW
    organization = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        null=True,

        blank=True,

        related_name="posts"

    )
    
    event = models.ForeignKey(
        
    "events.Event",
    
    on_delete=models.CASCADE,
    
    null=True,
    
    blank=True,
    
    related_name="posts"
    
   )



    caption = models.TextField(

        blank=True

    )



    image = models.ImageField(

        upload_to="feed/images/",

        blank=True,

        null=True

    )



    video = models.FileField(

        upload_to="feed/videos/",

        blank=True,

        null=True

    )



    post_type = models.CharField(

        max_length=30,

        choices=POST_TYPES,

        default="GENERAL"

    )



    views = models.PositiveIntegerField(

        default=0

    )



    created_at = models.DateTimeField(

        auto_now_add=True

    )



    updated_at = models.DateTimeField(

        auto_now=True

    )
    
    




    class Meta:

        ordering = [

            "-created_at"

        ]




    def __str__(self):

        if self.event:
            return f"{self.event.title} - Event"

        if self.organization:
            return f"{self.organization.name} - {self.post_type}"

        if self.talent:
            return f"{self.talent.user.username} - {self.post_type}"

        return f"{self.author.username} - {self.post_type}"




class PostLike(models.Model):


    user = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,
        
        related_name="post_likes"


    )


    post = models.ForeignKey(

        Post,

        on_delete=models.CASCADE,

        related_name="likes"

    )


    created_at=models.DateTimeField(

        auto_now_add=True

    )



    class Meta:

        unique_together = (

            "user",

            "post"

        )
        
    def __str__(self):

       return f"{self.user} liked {self.post}"    




class Comment(models.Model):


    user = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE

    )


    post=models.ForeignKey(

        Post,

        on_delete=models.CASCADE,

        related_name="comments"

    )


    text=models.TextField()



    created_at=models.DateTimeField(

        auto_now_add=True

    )



    class Meta:

        ordering = [

            "-created_at"

        ]



    def __str__(self):

        return f"{self.user} commented on {self.post}"
    
    
    
    
    
    
class SavedPost(models.Model):


    user = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE

    )


    post = models.ForeignKey(

        Post,

        on_delete=models.CASCADE,

        related_name="saves"

    )


    created_at = models.DateTimeField(

        auto_now_add=True

    )


    class Meta:

        unique_together = (

            "user",

            "post",

        )    




class SharedPost(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="shares"
    )

    caption = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )