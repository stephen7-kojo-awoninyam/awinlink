from django.db import models

# Create your models here.


class PortfolioItem(models.Model):

    ITEM_TYPES = (

        ("IMAGE", "Image"),
        ("VIDEO", "Video"),
        ("DOCUMENT", "Document"),
        ("PROJECT", "Project"),
        ("CERTIFICATE", "Certificate"),
        ("ACHIEVEMENT", "Achievement"),

    )


    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="portfolio_items"
    )


    title = models.CharField(
        max_length=200
    )


    description = models.TextField(
        blank=True
    )


    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPES
    )
    image = models.ImageField(
            upload_to="portfolio/images/",
            blank=True,
            null=True
        )

    file = models.FileField(
        upload_to="portfolio/files/",
        blank=True,
        null=True
    )


    link = models.URLField(
        blank=True
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.title