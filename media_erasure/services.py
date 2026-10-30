"""Durable media retention queue with a separately gated erasure executor."""
from datetime import timedelta
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.db.models import FileField
from django.utils import timezone

from config.media_storage import PlaybackMediaStorage
from .models import MediaErasureJob, MediaLegalHold


RETENTION_DAYS = 30


def _require_active_superuser(actor_id):
    from accounts.models import User
    if not User.objects.filter(pk=actor_id, is_active=True, is_superuser=True).exists():
        raise PermissionError('Only an active superuser may manage media erasure holds or provider identities.')


def _canonical_name(name):
    normalize = getattr(default_storage, '_media_name', None)
    return normalize(name) if callable(normalize) else str(name)


def _aliases(name):
    canonical = _canonical_name(name)
    values = {canonical, str(name)}
    prefix = getattr(getattr(default_storage, 'cloudinary_storage', None), 'PREFIX', '')
    if prefix:
        values.add(f'{str(prefix).strip("/")}/{canonical}')
    configured_prefix = ''
    try:
        from django.conf import settings
        configured_prefix = settings.CLOUDINARY_STORAGE.get('PREFIX', '')
    except (AttributeError, TypeError):
        pass
    if configured_prefix:
        values.add(f'{str(configured_prefix).strip("/")}/{canonical}')
    return {item for item in values if item}


def enqueue_instance_media(instance, *, requested_by_id=None):
    """Queue all concrete FileField references on an instance, idempotently."""
    now = timezone.now()
    jobs = []
    for field in instance._meta.concrete_fields:
        if not isinstance(field, FileField):
            continue
        value = getattr(instance, field.attname, None)
        name = getattr(value, 'name', value)
        if name:
            jobs.append(_enqueue_reference(instance._meta.model, instance.pk, field.name, str(name),
                requested_by_id=requested_by_id, now=now))
    return jobs


def _enqueue_reference(model, source_pk, field_name, name, *, requested_by_id, now):
    storage = default_storage
    cloudinary = isinstance(storage, PlaybackMediaStorage)
    resource_type = ''
    # We cannot infer a legacy Cloudinary resource/delivery type or immutable
    # asset ID from a Django storage name. Require explicit inventory resolution.
    try:
        job, _ = MediaErasureJob.objects.get_or_create(
            storage_name=name, source_model=model._meta.label_lower, source_pk=str(source_pk), source_field=field_name,
            defaults={
                'storage_kind': 'CLOUDINARY' if cloudinary else 'LOCAL',
                'provider_cloud_name': settings.CLOUDINARY_STORAGE.get('CLOUD_NAME', '') if cloudinary else '',
                'resource_type': resource_type,
                'delivery_type': '',
                'requested_by_id': requested_by_id,
                'requested_at': now,
                'retain_until': now + timedelta(days=RETENTION_DAYS),
            },
        )
    except IntegrityError:
        # A concurrent request may win the unique-key insert. The nested
        # savepoint keeps the surrounding deletion transaction usable.
        with transaction.atomic():
            job = MediaErasureJob.objects.get(storage_name=name, source_model=model._meta.label_lower,
                source_pk=str(source_pk), source_field=field_name)
    return job


def delete_instance_with_retention(instance, *, requested_by_id=None):
    """Atomically queue referenced files then remove the authorized DB row."""
    model = type(instance)
    with transaction.atomic():
        locked = model._base_manager.select_for_update().get(pk=instance.pk)
        jobs = enqueue_instance_media(locked, requested_by_id=requested_by_id)
        locked.delete()
    return jobs


def save_instance_with_media_retention(instance, save_callable, *, requested_by_id=None):
    """Queue replaced file references in the same transaction as a model save."""
    model = type(instance)
    with transaction.atomic():
        locked = model._base_manager.select_for_update().get(pk=instance.pk)
        fields = [field for field in model._meta.concrete_fields if isinstance(field, FileField)]
        previous = {field.name: getattr(locked, field.attname).name for field in fields}
        result = save_callable()
        current = model._base_manager.get(pk=instance.pk)
        now = timezone.now()
        jobs = []
        for field in fields:
            old_name = previous[field.name]
            new_value = getattr(current, field.attname)
            new_name = getattr(new_value, 'name', new_value)
            if old_name and old_name != new_name:
                jobs.append(_enqueue_reference(model, instance.pk, field.name, old_name,
                    requested_by_id=requested_by_id, now=now))
    return result, jobs


def delete_event_with_retention(event, *, requested_by_id=None):
    """Queue event artwork and gallery assets before the event cascade."""
    from events.models import EventMedia
    with transaction.atomic():
        from events.models import Event
        locked = Event.objects.select_for_update().get(pk=event.pk)
        jobs = enqueue_instance_media(locked, requested_by_id=requested_by_id)
        media_rows = list(EventMedia.objects.select_for_update().filter(event_id=locked.pk).order_by('pk'))
        for media in media_rows:
            jobs.extend(enqueue_instance_media(media, requested_by_id=requested_by_id))
        locked.delete()
    return jobs


def has_live_reference(storage_name):
    """Check every installed concrete FileField for this stored object name."""
    names = _aliases(storage_name)
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if field.get_internal_type() not in {'FileField', 'ImageField'}:
                continue
            if model is MediaErasureJob and field.name == 'storage_name':
                continue
            if model._base_manager.filter(**{f'{field.name}__in': names}).exists():
                return True
    return False


def _live_reference_names(storage_names):
    """Batch one indexed lookup per media field instead of per queue row."""
    alias_to_names = {}
    for name in storage_names:
        for alias in _aliases(name):
            alias_to_names.setdefault(alias, set()).add(name)
    aliases = set(alias_to_names)
    referenced = set()
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if not isinstance(field, FileField):
                continue
            values = model._base_manager.filter(**{f'{field.name}__in': aliases}) \
                .values_list(field.name, flat=True).distinct()
            for value in values:
                referenced.update(alias_to_names.get(value, ()))
    return referenced


def has_active_hold(storage_name):
    return MediaLegalHold.objects.filter(held=True, storage_name__in=_aliases(storage_name)).exists()


def place_legal_hold(storage_name, *, reason, placed_by_id=None, provider_asset_id=''):
    _require_active_superuser(placed_by_id)
    if not isinstance(storage_name, str) or not storage_name.strip() or len(storage_name) > 1024:
        raise ValueError('A valid stored media name is required.')
    reason = str(reason or '').strip()
    if not reason or len(reason) > 500:
        raise ValueError('A legal hold reason of 1 to 500 characters is required.')
    canonical = _canonical_name(storage_name)
    with transaction.atomic():
        list(MediaErasureJob.objects.select_for_update().filter(storage_name__in=_aliases(canonical)).order_by('pk'))
        return MediaLegalHold.objects.create(storage_name=canonical, reason=reason,
            placed_by_id=placed_by_id, provider_asset_id=provider_asset_id or '')


def release_legal_hold(hold_id, *, released_by_id=None):
    _require_active_superuser(released_by_id)
    with transaction.atomic():
        hold = MediaLegalHold.objects.select_for_update().get(pk=hold_id)
        list(MediaErasureJob.objects.select_for_update().filter(
            storage_name__in=_aliases(hold.storage_name)).order_by('pk'))
        if hold.held:
            hold.held = False
            hold.released_at = timezone.now()
            hold.released_by_id = released_by_id
            hold.save(update_fields=('held', 'released_at', 'released_by_id'))
        return hold


def save_legal_hold(hold, *, actor_id):
    """Persist a superuser-authorized hold change with queue-row serialization."""
    _require_active_superuser(actor_id)
    canonical = _canonical_name(hold.storage_name)
    if not canonical or len(canonical) > 1024 or '\\' in canonical or any(
        part in {'', '.', '..'} for part in canonical.split('/')
    ):
        raise ValueError('A safe stored media name is required.')
    if not (hold.reason or '').strip() or len(hold.reason) > 500:
        raise ValueError('A legal hold reason of 1 to 500 characters is required.')
    with transaction.atomic():
        if hold.pk:
            current = MediaLegalHold.objects.select_for_update().get(pk=hold.pk)
            if (current.storage_name != canonical or current.reason != hold.reason
                    or current.provider_asset_id != hold.provider_asset_id):
                raise ValueError('Legal hold identity and reason are immutable.')
            if not current.held and hold.held:
                raise ValueError('Released legal holds cannot be reactivated; place a new hold.')
            list(MediaErasureJob.objects.select_for_update().filter(storage_name__in=_aliases(canonical)).order_by('pk'))
            if current.held and not hold.held:
                hold.released_at = timezone.now()
                hold.released_by_id = actor_id
        else:
            list(MediaErasureJob.objects.select_for_update().filter(storage_name__in=_aliases(canonical)).order_by('pk'))
            hold.storage_name = canonical
            hold.placed_by_id = actor_id
        hold.save()
    return hold


def _assess(job, now):
    aliases = _aliases(job.storage_name)
    group = MediaErasureJob.objects.filter(storage_name__in=aliases)
    latest_retention = group.aggregate(latest=Max('retain_until'))['latest'] or job.retain_until
    if has_active_hold(job.storage_name):
        return MediaErasureJob.State.HELD, 'active_legal_hold'
    if latest_retention > now:
        return MediaErasureJob.State.PENDING, 'retention_window_active'
    if has_live_reference(job.storage_name):
        return MediaErasureJob.State.SHARED, 'live_shared_reference'
    if job.storage_kind == 'CLOUDINARY':
        cloud_jobs = list(group)
        identities = {(row.provider_cloud_name, row.provider_asset_id, row.resource_type, row.delivery_type)
            for row in cloud_jobs}
        if (not cloud_jobs or any(row.storage_kind != 'CLOUDINARY' for row in cloud_jobs)
                or len(identities) != 1 or any(
            not (row.provider_asset_id and row.resource_type and row.delivery_type and row.identity_verified_at)
            for row in cloud_jobs
        )):
            return MediaErasureJob.State.UNRESOLVED, 'provider_identity_required'
    return MediaErasureJob.State.READY, 'eligible_no_deletion_performed'


def _assess_batch(jobs, now):
    """Batch reference/hold/retention queries for the bounded queue worker."""
    aliases_by_job = {job.pk: _aliases(job.storage_name) for job in jobs}
    all_aliases = set().union(*aliases_by_job.values()) if aliases_by_job else set()
    grouped = {}
    for row in MediaErasureJob.objects.filter(storage_name__in=all_aliases):
        for alias in _aliases(row.storage_name):
            grouped.setdefault(alias, []).append(row)
    latest = dict(MediaErasureJob.objects.filter(storage_name__in=all_aliases)
        .values('storage_name').annotate(value=Max('retain_until')).values_list('storage_name', 'value'))
    held = set(MediaLegalHold.objects.filter(held=True, storage_name__in=all_aliases)
        .values_list('storage_name', flat=True))
    referenced = _live_reference_names([job.storage_name for job in jobs])
    results = {}
    for job in jobs:
        aliases = aliases_by_job[job.pk]
        group = {row.pk: row for alias in aliases for row in grouped.get(alias, ())}.values()
        latest_retention = max((latest[name] for name in aliases if name in latest), default=job.retain_until)
        if aliases & held:
            result = MediaErasureJob.State.HELD, 'active_legal_hold'
        elif latest_retention > now:
            result = MediaErasureJob.State.PENDING, 'retention_window_active'
        elif job.storage_name in referenced:
            result = MediaErasureJob.State.SHARED, 'live_shared_reference'
        elif job.storage_kind == 'CLOUDINARY':
            cloud_jobs = list(group)
            identities = {(row.provider_cloud_name, row.provider_asset_id, row.resource_type, row.delivery_type)
                for row in cloud_jobs}
            if (not cloud_jobs or any(row.storage_kind != 'CLOUDINARY' for row in cloud_jobs)
                    or len(identities) != 1 or any(not (
                        row.provider_asset_id and row.resource_type and row.delivery_type and row.identity_verified_at
                    ) for row in cloud_jobs)):
                result = MediaErasureJob.State.UNRESOLVED, 'provider_identity_required'
            else:
                result = MediaErasureJob.State.READY, 'eligible_no_deletion_performed'
        else:
            result = MediaErasureJob.State.READY, 'eligible_no_deletion_performed'
        results[job.pk] = result
    return results


def process_due_jobs(*, limit=100, now=None):
    """Advance due jobs; never invoke storage/provider deletion."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer between 1 and 1000')
    now = now or timezone.now()
    updated = []
    with transaction.atomic():
        jobs = list(MediaErasureJob.objects.select_for_update(skip_locked=True)
            .exclude(state=MediaErasureJob.State.ERASED)
            .order_by('last_checked_at', 'retain_until', 'pk')[:limit])
        assessments = _assess_batch(jobs, now)
        for job in jobs:
            job.state, job.last_reason = assessments[job.pk]
            job.last_checked_at = now
            job.save(update_fields=('state', 'last_reason', 'last_checked_at'))
            updated.append(job)
    return updated


def erase_ready_jobs(*, apply=False, limit=100, now=None, operator_user_id=None):
    """Erase previously eligible assets only with explicit apply=True.

    This is a separate operation from queue processing. Each apply rechecks the
    retention group, legal holds, shared references, provider identity and
    configured Cloudinary account while holding database row locks.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer between 1 and 1000')
    if apply:
        _require_active_superuser(operator_user_id)
    now = now or timezone.now()
    results = []
    candidates = MediaErasureJob.objects.exclude(state=MediaErasureJob.State.ERASED)
    candidate_ids = list(candidates.order_by('last_checked_at', 'retain_until', 'pk')
        .values_list('pk', flat=True)[:limit])
    for job_id in candidate_ids:
        with transaction.atomic():
            job = MediaErasureJob.objects.select_for_update().get(pk=job_id)
            if job.state == MediaErasureJob.State.ERASED:
                continue
            previously_eligible = job.state in (MediaErasureJob.State.READY, MediaErasureJob.State.FAILED)
            aliases = _aliases(job.storage_name)
            group = list(MediaErasureJob.objects.select_for_update().filter(storage_name__in=aliases).order_by('pk'))
            state, reason = _assess(job, now)
            if state != MediaErasureJob.State.READY:
                for sibling in group:
                    sibling.state, sibling.last_reason, sibling.last_checked_at = state, reason, now
                    sibling.save(update_fields=('state', 'last_reason', 'last_checked_at'))
                results.append((job.pk, state, False))
                continue
            if not apply:
                results.append((job.pk, state, False))
                continue
            if not previously_eligible:
                job.state, job.last_reason, job.last_checked_at = state, reason, now
                job.save(update_fields=('state', 'last_reason', 'last_checked_at'))
                results.append((job.pk, state, False))
                continue
            try:
                if job.storage_kind == 'LOCAL':
                    path = job.storage_name
                    if ('\\' in path or any(part in {'', '.', '..'} for part in path.split('/'))):
                        raise ValueError('Unsafe local media path.')
                    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
                    resolved = local_storage.path(path)
                    root = Path(settings.MEDIA_ROOT).resolve()
                    if not Path(resolved).resolve().is_relative_to(root):
                        raise ValueError('Local media path escaped MEDIA_ROOT.')
                    local_storage.delete(path)
                elif job.storage_kind == 'CLOUDINARY':
                    if settings.CLOUDINARY_STORAGE.get('CLOUD_NAME', '') != job.provider_cloud_name:
                        raise ValueError('Cloudinary account changed since verification.')
                    from config.media_storage import PlaybackMediaStorage
                    if not isinstance(default_storage, PlaybackMediaStorage):
                        raise ValueError('Cloudinary storage is not configured.')
                    default_storage.delete_asset(job.storage_name, asset_id=job.provider_asset_id,
                        resource_type=job.resource_type, delivery_type=job.delivery_type)
                else:
                    raise ValueError('Unknown media storage backend.')
            except Exception:
                for sibling in group:
                    sibling.state = MediaErasureJob.State.FAILED
                    sibling.attempts += 1
                    sibling.last_reason = 'erasure_attempt_failed'
                    sibling.last_checked_at = now
                    sibling.save(update_fields=('state', 'attempts', 'last_reason', 'last_checked_at'))
                results.append((job.pk, MediaErasureJob.State.FAILED, False))
                continue
            for sibling in group:
                sibling.state = MediaErasureJob.State.ERASED
                sibling.attempts += 1
                sibling.last_reason = 'physical_erasure_confirmed'
                sibling.last_checked_at = now
                sibling.erased_at = now
                sibling.erased_by_id = operator_user_id
                sibling.save(update_fields=('state', 'attempts', 'last_reason', 'last_checked_at', 'erased_at', 'erased_by_id'))
            results.append((job.pk, MediaErasureJob.State.ERASED, True))
    return results


def verify_cloudinary_identity(job, *, asset_id, resource_type, delivery_type, verified_by_id):
    """Read-only provider verification; it never mutates or deletes an asset."""
    if job.storage_kind != 'CLOUDINARY' or resource_type not in {'image', 'video', 'raw'} \
            or delivery_type not in {'upload', 'private', 'authenticated'}:
        raise ValueError('Unsupported Cloudinary identity.')
    _require_active_superuser(verified_by_id)
    if not isinstance(asset_id, str) or not asset_id or len(asset_id) > 128:
        raise ValueError('A provider asset ID is required.')
    storage = default_storage
    if not isinstance(storage, PlaybackMediaStorage) or resource_type not in storage.resource_candidates(job.storage_name):
        raise ValueError('Storage or resource type does not match this media name.')
    if job.provider_cloud_name and settings.CLOUDINARY_STORAGE.get('CLOUD_NAME', '') != job.provider_cloud_name:
        raise ValueError('Configured Cloudinary account does not match the queued media provider.')
    public_id = storage._prepend_prefix(_canonical_name(job.storage_name))
    from cloudinary import api
    current = api.resource(public_id, resource_type=resource_type, type=delivery_type)
    if not asset_id or current.get('asset_id') != asset_id or current.get('public_id') != public_id:
        raise ValueError('Cloudinary metadata does not match the queued immutable identity.')
    now = timezone.now()
    with transaction.atomic():
        queued_jobs = MediaErasureJob.objects.select_for_update().filter(storage_name__in=_aliases(job.storage_name),
            storage_kind='CLOUDINARY', provider_cloud_name=job.provider_cloud_name)
        for queued in queued_jobs:
            queued.provider_asset_id = asset_id
            queued.resource_type = resource_type
            queued.delivery_type = delivery_type
            queued.identity_verified_at = now
            queued.identity_verified_by_id = verified_by_id
            queued.save(update_fields=('provider_asset_id', 'resource_type', 'delivery_type',
                'identity_verified_at', 'identity_verified_by_id'))
    job.refresh_from_db()
    return job
