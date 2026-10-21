"""Read-only checks matching migration 0002, usable with historical models."""
from django.db.models import Count, Q


def audit_legacy_marketplace(apps, using='default'):
    listings = apps.get_model('marketplace', 'Listing').objects.using(using)
    offers = apps.get_model('marketplace', 'Offer').objects.using(using)
    valid_decision = (
        Q(status='PENDING', decided_at__isnull=True, talent_consented_at__isnull=True)
        | Q(status='ACCEPTED', decided_at__isnull=False, talent_consented_at__isnull=False)
        | Q(status__in=['DECLINED', 'WITHDRAWN'], decided_at__isnull=False, talent_consented_at__isnull=True)
    )
    queries = {
        'market_listing_valid_status': listings.exclude(status__in=['DRAFT', 'PUBLISHED', 'PAUSED']),
        'market_listing_publication_consent': listings.filter(status='PUBLISHED', publication_consented_at__isnull=True),
        'market_offer_valid_status': offers.exclude(status__in=['PENDING', 'ACCEPTED', 'DECLINED', 'WITHDRAWN']),
        'market_offer_decision_consent': offers.exclude(valid_decision),
    }
    report = {name: {'count': rows.count(), 'sample_ids': list(rows.order_by('pk').values_list('pk', flat=True)[:20])}
              for name, rows in queries.items()}
    for name, field, isnull in [('market_pending_personal_offer', 'sender_id', True),
                                ('market_pending_org_offer', 'organization_id', False)]:
        groups = (offers.filter(status='PENDING', organization__isnull=isnull)
                  .values('listing_id', field).annotate(count=Count('pk')).filter(count__gt=1)
                  .order_by('listing_id', field))
        report[name] = {'count': groups.count(), 'sample_groups': list(groups[:20])}
    return {'ready': not any(item['count'] for item in report.values()), 'checks': report}
