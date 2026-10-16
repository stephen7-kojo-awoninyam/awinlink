from django.db import migrations
from django.db.models import Count


def reconcile_follow_data(apps, schema_editor):
    alias = schema_editor.connection.alias
    Follow = apps.get_model("connections", "Follow")
    OrganizationFollow = apps.get_model("connections", "OrganizationFollow")
    Organization = apps.get_model("organizations", "Organization")
    TalentProfile = apps.get_model("talents", "TalentProfile")

    legacy_through = Organization._meta.get_field("followers").remote_field.through
    legacy_rows = legacy_through.objects.using(alias).values_list(
        "organization_id", "user_id",
    ).iterator()
    for organization_id, user_id in legacy_rows:
        OrganizationFollow.objects.using(alias).get_or_create(
            organization_id=organization_id,
            user_id=user_id,
        )

    totals = dict(
        Follow.objects.using(alias)
        .values_list("following_id")
        .annotate(total=Count("pk"))
    )
    for talent in TalentProfile.objects.using(alias).only("pk", "user_id", "followers_count").iterator():
        count = totals.get(talent.user_id, 0)
        if talent.followers_count != count:
            TalentProfile.objects.using(alias).filter(pk=talent.pk).update(
                followers_count=count,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("connections", "0005_connection"),
        ("organizations", "0011_organization_team_invitation"),
        ("talents", "0014_talentprofile_talent_area"),
    ]

    operations = [
        migrations.RunPython(reconcile_follow_data, migrations.RunPython.noop),
    ]
