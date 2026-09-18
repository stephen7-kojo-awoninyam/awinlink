from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


# ==========================================
# EVENT CATEGORY
# ==========================================

class EventCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )


    domain = models.ForeignKey(
        "domains.TalentDomain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_categories"
    )


    description = models.TextField(
        blank=True
    )


    def __str__(self):
        return self.name





# ==========================================
# EVENT
# ==========================================

class Event(models.Model):


    EVENT_TYPES = (

        ("COMPETITION", "Competition"),
        ("WORKSHOP", "Workshop"),
        ("BOOTCAMP", "Bootcamp"),
        ("AUDITION", "Audition"),
        ("CONFERENCE", "Conference"),
        ("TRIAL", "Talent Trial"),
        ("WEBINAR", "Webinar"),

    )



    STATUS = (

        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("CLOSED", "Closed"),
        ("CANCELLED", "Cancelled"),

    )



    organizer = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        related_name="events"

    )



    category = models.ForeignKey(

        EventCategory,

        on_delete=models.SET_NULL,

        null=True,

        related_name="events"

    )



    title = models.CharField(
        max_length=250
    )



    slug = models.SlugField(
        unique=True
    )



    description = models.TextField()



    image = models.ImageField(

        upload_to="events/images/",

        blank=True,

        null=True

    )



    event_type = models.CharField(

        max_length=30,

        choices=EVENT_TYPES

    )



    location = models.CharField(

        max_length=200

    )



    online = models.BooleanField(

        default=False

    )



    meeting_link = models.URLField(

        blank=True

    )



    start_date = models.DateTimeField()



    end_date = models.DateTimeField()



    registration_deadline = models.DateTimeField()



    capacity = models.PositiveIntegerField(

        default=0

    )



    status = models.CharField(

        max_length=20,

        choices=STATUS,

        default="DRAFT"

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

        return self.title






# ==========================================
# EVENT REGISTRATION
# ==========================================
class EventRegistration(models.Model):

    STATUS = (
        ("REGISTERED", "Registered"),
        ("APPROVED", "Approved"),
        ("ATTENDED", "Attended"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="event_registrations"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="REGISTERED",
        db_index=True
    )

    registered_at = models.DateTimeField(
        auto_now_add=True
    )

    attendance_marked = models.BooleanField(
        default=False
    )

    attendance_time = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=["event", "talent"],
                name="unique_event_talent"
            )
        ]

        ordering = [
            "-registered_at"
        ]

    def __str__(self):

        return (
            f"{self.talent.user.get_full_name()} - "
            f"{self.event.title}"
        )



# ==========================================
# EVENT FEEDBACK
# ==========================================


class EventFeedback(models.Model):


    event = models.ForeignKey(

        Event,

        on_delete=models.CASCADE,

        related_name="feedback"

    )



    reviewer = models.ForeignKey(

        settings.AUTH_USER_MODEL,

        on_delete=models.CASCADE,

        related_name="event_feedback"

    )



    rating = models.PositiveSmallIntegerField()



    comment = models.TextField(

        blank=True

    )



    created_at = models.DateTimeField(

        auto_now_add=True

    )



    class Meta:

        unique_together = (

            "event",

            "reviewer",

        )


        ordering = [

            "-created_at"

        ]



    def __str__(self):

        return f"{self.reviewer} - {self.event}"
    

    



# ==========================================
# EVENT CERTIFICATE
# ==========================================

class EventCertificate(models.Model):

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="certificates"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="event_certificates"
    )

    certificate_title = models.CharField(
        max_length=200,
        default="Certificate of Participation"
    )

    issued_by = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="issued_certificates"
    )

    certificate_code = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    issued_at = models.DateTimeField(
        auto_now_add=True
    )

    verified = models.BooleanField(
        default=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=["event", "talent"],
                name="unique_event_certificate"
            )
        ]

        ordering = [
            "-issued_at"
        ]

    def __str__(self):

        return (
            f"{self.talent} - "
            f"{self.event.title}"
        )  
    
    
    
class EventMedia(models.Model):

    MEDIA_TYPES = (

        ("IMAGE", "Image"),

        ("VIDEO", "Video"),

    )

    event = models.ForeignKey(

        Event,

        on_delete=models.CASCADE,

        related_name="media"

    )

    uploaded_by = models.ForeignKey(

        "organizations.Organization",

        on_delete=models.CASCADE,

        related_name="event_media"

    )

    media_type = models.CharField(

        max_length=10,

        choices=MEDIA_TYPES

    )

    file = models.FileField(

        upload_to="events/gallery/"

    )

    caption = models.CharField(

        max_length=255,

        blank=True

    )

    uploaded_at = models.DateTimeField(

        auto_now_add=True

    )

    class Meta:

        ordering = [

            "-uploaded_at"

        ]

    def __str__(self):

        return f"{self.event.title} - {self.media_type}"    