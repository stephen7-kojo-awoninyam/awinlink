from django.db import migrations


def backfill(apps, schema_editor):
    Profile = apps.get_model("talents", "TalentProfile")
    Other = apps.get_model("others", "OtherTalentProfile")
    alias = schema_editor.connection.alias
    for profile in Profile.objects.using(alias).filter(talent_category="OTHERS").iterator():
        if (profile.talent_area or "").strip().casefold() not in {"", "other", "others", "talent", "other talent"}:
            continue
        other = Other.objects.using(alias).filter(talent_id=profile.pk).first()
        if other:
            for value in (other.specialization, other.field):
                area = (value or "").strip()
                if area and len(area) <= 150 and area.casefold() not in {"other", "others", "talent", "other talent"}:
                    Profile.objects.using(alias).filter(pk=profile.pk).update(talent_area=area)
                    break


class Migration(migrations.Migration):
    dependencies = [("talents", "0014_talentprofile_talent_area"), ("others", "0001_initial")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
