"""Offline-testable, identity-preserving Cloudinary delivery-type migration.

No deletion, upload, database updates, or automatic rollback to public delivery.
The caller persists checkpoints before/after each remote mutation.
"""
from cloudinary.exceptions import NotFound
from urllib.parse import unquote, urlsplit
import re

from .media_storage import PlaybackMediaStorage


class MigrationConflict(ValueError):
    pass


def allowed_id(public_id, prefix):
    if not isinstance(public_id, str):
        return False
    root = prefix.strip('/')
    relative = public_id[len(root) + 1:] if root and public_id.startswith(root + '/') else public_id if not root else ''
    return (relative.startswith(PlaybackMediaStorage.PRIVATE_PREFIXES)
            and all(part not in {'', '.', '..'} for part in public_id.split('/'))
            and '\\' not in public_id and '://' not in public_id)


def identity(asset):
    values = {key: asset.get(key) for key in ('asset_id', 'public_id', 'resource_type', 'bytes', 'etag')}
    if (not all(isinstance(values[key], str) and values[key] for key in ('asset_id', 'public_id', 'etag'))
            or values['resource_type'] not in {'image', 'raw', 'video'}
            or type(values['bytes']) is not int or values['bytes'] <= 0):
        raise MigrationConflict('Missing asset identity, size or checksum; manual review required.')
    return values


def inventory(api, prefix, prefixes=None):
    """Include orphaned provider files as well as files referenced by the database."""
    selected = prefixes or PlaybackMediaStorage.PRIVATE_PREFIXES
    if any(value not in PlaybackMediaStorage.PRIVATE_PREFIXES for value in selected):
        raise MigrationConflict('Only private namespaces can be migrated.')
    seen = set()
    for namespace in selected:
        for resource, delivery_type in ((resource, kind) for resource in ('image', 'raw', 'video')
                                        for kind in ('upload', 'private')):
            cursor = None
            cursors = set()
            while True:
                options = dict(prefix='/'.join(filter(None, (prefix.strip('/'), namespace))),
                               resource_type=resource, type=delivery_type, max_results=500)
                if cursor:
                    options['next_cursor'] = cursor
                page = api.resources(**options)
                for asset in page.get('resources', []):
                    record = identity(asset)
                    if (not allowed_id(record['public_id'], prefix) or record['resource_type'] != resource
                            or asset.get('type') != delivery_type or not record['public_id'].startswith(options['prefix'])):
                        raise MigrationConflict('Provider inventory is outside the selected scope.')
                    key = (resource, delivery_type, record['public_id'])
                    if key not in seen:
                        seen.add(key)
                        yield {**record, 'delivery_type': delivery_type, 'state': 'planned'}
                cursor = page.get('next_cursor')
                if not cursor:
                    break
                if cursor in cursors:
                    raise MigrationConflict('Repeated provider pagination cursor.')
                cursors.add(cursor)


def lookup(api, record, delivery_type):
    try:
        return api.resource(record['public_id'], resource_type=record['resource_type'], type=delivery_type)
    except NotFound:
        return None


def matches(asset, record):
    return asset is not None and identity(asset) == identity(record)


def migrate_record(api, uploader, record, prefix, checkpoint):
    if not allowed_id(record['public_id'], prefix):
        raise MigrationConflict('Asset is outside private namespaces.')
    identity(record)
    source_type = record.get('delivery_type')
    if source_type not in {'upload', 'private'}:
        raise MigrationConflict('Unsupported source delivery type.')
    source = lookup(api, record, source_type)
    target = lookup(api, record, 'authenticated')
    if source is None:
        # A previous request may have succeeded before the process lost its reply.
        if record.get('state') not in {'moving', 'origin_private_cdn_pending'} or not matches(target, record):
            raise MigrationConflict('Source missing or unaudited authenticated target; manual review required.')
    else:
        if not matches(source, record) or target is not None:
            raise MigrationConflict('Source changed or authenticated target exists; refusing overwrite.')
        record['state'] = 'moving'
        checkpoint()
        uploader.rename(record['public_id'], record['public_id'], resource_type=record['resource_type'],
                        type=source_type, to_type='authenticated', overwrite=False, invalidate=True)
        target = lookup(api, record, 'authenticated')
        if not matches(target, record) or lookup(api, record, source_type) is not None:
            raise MigrationConflict('Post-migration identity or public-origin verification failed; stop and investigate.')
    record['state'] = 'origin_private_cdn_pending'
    checkpoint()


def check_exposed_urls(api, session, records, cloud, urls):
    """Check supplied historical URLs without following redirects or accepting other hosts.

    This records observations, not a global assertion that every CDN edge is purged.
    Validate the entire input before any network request.
    """
    if not isinstance(urls, list) or not urls or len(urls) > 1000:
        raise MigrationConflict('Supply between one and 1000 historical URLs.')
    prepared = []
    for url in urls:
        if not isinstance(url, str) or len(url) > 4096 or any(ord(char) < 32 for char in url):
            raise MigrationConflict('Invalid historical URL.')
        parsed = urlsplit(url)
        parts = unquote(parsed.path).split('/', 4)
        if (parsed.scheme != 'https' or parsed.hostname != 'res.cloudinary.com'
                or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment
                or len(parts) != 5 or parts[1] != cloud):
            raise MigrationConflict('Only this cloud’s HTTPS Cloudinary delivery URLs may be checked.')
        candidates = []
        for record in records:
            if parts[2:4] != [record['resource_type'], record['delivery_type']]:
                continue
            tail, public_id = parts[4], record['public_id']
            exact = tail == public_id or tail.endswith('/' + public_id)
            formatted = record['resource_type'] != 'raw' and re.search(
                r'(?:^|/)' + re.escape(public_id) + r'\.[a-zA-Z0-9]{1,10}$', tail)
            if exact or formatted:
                candidates.append(record)
        if len(candidates) != 1 or candidates[0]['state'] != 'origin_private_cdn_pending':
            raise MigrationConflict('URL does not identify exactly one migrated manifest asset.')
        prepared.append((url, candidates[0]))
    # The source must remain absent and the original bytes must still be private.
    checked = set()
    for _, record in prepared:
        key = record['resource_type'], record['public_id']
        if key not in checked:
            if lookup(api, record, record['delivery_type']) is not None or not matches(lookup(api, record, 'authenticated'), record):
                raise MigrationConflict('Origin privacy or byte identity changed; manual review required.')
            checked.add(key)
    observations = []
    for url, _ in prepared:
        response = session.get(url, stream=True, allow_redirects=False, timeout=(3, 10),
                               headers={'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'})
        try:
            observations.append(dict(url=url, status=response.status_code,
                                     denied=response.status_code in (401, 403, 404)))
        finally:
            response.close()
    return observations
