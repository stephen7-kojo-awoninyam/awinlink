"""Filter a collection before pagination; never search only its first page."""
from types import SimpleNamespace

from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter

TALENT_SEARCH_FIELDS = ['user__username', 'user__first_name', 'user__last_name',
                        'headline', 'talent_area', 'talent_category', 'country']


class BoundedSearchFilter(SearchFilter):
    def get_search_terms(self, request):
        text = request.query_params.get(self.search_param, '')
        if len(text) > 200 or len(request.query_params.getlist(self.search_param)) > 1:
            raise ValidationError({'search': 'Use one search term up to 200 characters.'})
        terms = super().get_search_terms(request)
        if len(terms) > 12:
            raise ValidationError({'search': 'Use at most 12 search words.'})
        return terms


def search_queryset(request, queryset, fields):
    return BoundedSearchFilter().filter_queryset(request, queryset, SimpleNamespace(search_fields=fields))


def filter_parent(request, queryset, name):
    value = request.query_params.get(name)
    if value is None:
        return queryset
    if (len(request.query_params.getlist(name)) != 1 or not value.isascii() or not value.isdecimal()
            or len(value) > 19 or not 0 < int(value) <= 9223372036854775807):
        raise ValidationError({name: 'Use one positive record ID.'})
    return queryset.filter(**{name + '_id': int(value)})
