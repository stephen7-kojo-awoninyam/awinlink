from django.db import models


class SkillCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )


    def __str__(self):

        return self.name





class Skill(models.Model):

    category = models.ForeignKey(

        SkillCategory,

        on_delete=models.CASCADE,

        related_name="skills"

    )


    name = models.CharField(

        max_length=100

    )


    class Meta:

        unique_together = (

            "category",

            "name",

        )



    def __str__(self):

        return self.name
    
    
    
    
class SkillRelationship(models.Model):

    skill = models.ForeignKey(
        "Skill",
        on_delete=models.CASCADE,
        related_name="related_skills"
    )

    related_skill = models.ForeignKey(
        "Skill",
        on_delete=models.CASCADE,
        related_name="related_to"
    )

    strength = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.00
    )

    class Meta:
        unique_together = (
            "skill",
            "related_skill",
        )

    def __str__(self):
        return (
            f"{self.skill.name} → "
            f"{self.related_skill.name}"
        )    