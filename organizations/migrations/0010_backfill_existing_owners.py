from django.db import migrations, transaction


def backfill_existing_owners(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "OrganizationMembership")
    database = schema_editor.connection.alias

    # Ownership, organisation suspension, and account activation are separate states.
    with transaction.atomic(using=database):
        owners = (
            Organization.objects.using(database)
            .exclude(user_id=None)
            .order_by("pk")
            .values_list("pk", "user_id")
        )
        for organization_id, user_id in owners.iterator(chunk_size=1000):
            memberships = Membership.objects.using(database)
            if memberships.filter(
                organization_id=organization_id, role="OWNER", status="ACTIVE",
            ).exclude(user_id=user_id).exists():
                raise RuntimeError(
                    f"Cannot backfill organization {organization_id}: "
                    "an active owner membership belongs to another user. "
                    "Reconcile ownership before rerunning this migration."
                )
            memberships.get_or_create(
                organization_id=organization_id,
                user_id=user_id,
                defaults={"role": "OWNER", "status": "ACTIVE"},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0009_organization_membership"),
    ]

    operations = [
        # Reversing the backfill keeps memberships, including later team changes.
        migrations.RunPython(
            backfill_existing_owners,
            reverse_code=migrations.RunPython.noop,
            hints={"model_name": "organizationmembership"},
        ),
    ]
