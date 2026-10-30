"""Bounded keyset lists with a compatible array body and explicit continuation.

New clients may request page_format=cursor for a results/next/previous envelope.
Existing array clients receive the same body shape plus RFC Link headers.
Never count or serialize the entire queryset to build a page.
"""
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound, ValidationError
from django.core import signing
from django.db.models import F, Q
from django.core.exceptions import ValidationError as DjangoValidationError
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import hashlib


class BoundedCursorPagination(CursorPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-pk'

    def paginate_queryset(self, queryset, request, view=None):
        self.prepare(request)
        return super().paginate_queryset(queryset, request, view)

    def prepare(self, request):
        for name in ('cursor', 'page_size'):
            if len(request.query_params.getlist(name)) > 1:
                raise ValidationError({name: 'Supply this parameter once.'})
        size = request.query_params.get('page_size')
        if size is not None and (not size.isascii() or not size.isdecimal() or len(size) > 6 or int(size) < 1):
            raise ValidationError({'page_size': 'Use a positive integer (maximum 100).'})
        filters = sorted((k, v) for k, values in request.query_params.lists()
                         if k not in {'cursor', 'page_size', 'page_format'} for v in values)
        context = hashlib.sha256(urlencode(filters).encode()).hexdigest()
        self.cursor_salt = f'api-page:{request.path}:{getattr(request.user, "pk", None)}:{context}'

    def encode_cursor(self, cursor):
        parts = urlsplit(super().encode_cursor(cursor))
        params = [(k, signing.dumps(v, salt=self.cursor_salt) if k == self.cursor_query_param else v)
                  for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        return urlunsplit(parts._replace(query=urlencode(params)))

    def decode_cursor(self, request):
        token = request.query_params.get(self.cursor_query_param)
        if token is None:
            return None
        try:
            if len(token) > 2048:
                raise signing.BadSignature()
            decoded = signing.loads(token, salt=self.cursor_salt, max_age=86400)
            if not isinstance(decoded, str):
                raise signing.BadSignature()
        except (signing.BadSignature, ValueError, TypeError):
            raise NotFound('Invalid or expired cursor.') from None
        params = request.query_params.copy()
        params[self.cursor_query_param] = decoded
        return super().decode_cursor(SimpleNamespace(query_params=params))

    def get_paginated_response(self, data):
        next_link, previous = self.get_next_link(), self.get_previous_link()
        if self.request.query_params.get('page_format') == 'cursor':
            response = Response({'results': data, 'next': next_link, 'previous': previous})
        else:
            response = Response(data)
        links = []
        if next_link:
            links.append(f'<{next_link}>; rel="next"')
        if previous:
            links.append(f'<{previous}>; rel="previous"')
        if links:
            response['Link'] = ', '.join(links)
        response['X-Page-Size'] = str(self.page_size)
        response['Access-Control-Expose-Headers'] = 'Link, X-Page-Size'
        return response


class OrderedCursorPagination(BoundedCursorPagination):
    """Compound forward seek for ranked results and ordered curricula.

    Unlike cursor offsets, equal sort values never require scanning/skipping an
    ever-growing offset. The final field must be a unique primary key.
    """
    ordering = ('pk',)

    @staticmethod
    def ordering_field(model, path):
        parts = path.lstrip('-').split('__')
        for index, part in enumerate(parts):
            field = model._meta.pk if part == 'pk' else model._meta.get_field(part)
            if index < len(parts) - 1:
                model = field.related_model
        return field

    @staticmethod
    def position_value(instance, path):
        for part in path.lstrip('-').split('__'):
            instance = getattr(instance, part)
        return None if instance is None else str(instance)

    def paginate_queryset(self, queryset, request, view=None):
        self.prepare(request)
        self.request = request
        self.page_size = self.get_page_size(request)
        self.base_url = request.build_absolute_uri()
        self.next_values = None
        token = request.query_params.get(self.cursor_query_param)
        fields = [self.ordering_field(queryset.model, name) for name in self.ordering]
        if token is not None:
            try:
                if len(token) > 2048:
                    raise signing.BadSignature()
                values = signing.loads(token, salt=self.cursor_salt + ':ordered', max_age=86400)
                if not isinstance(values, list) or len(values) != len(fields):
                    raise ValueError()
                values = [field.to_python(value) for field, value in zip(fields, values)]
                if any(value is None and not field.null for value, field in zip(values, fields)):
                    raise ValueError()
            except (signing.BadSignature, ValueError, TypeError, DjangoValidationError):
                raise NotFound('Invalid or expired cursor.') from None
            predicate, equal = Q(pk__in=[]), Q()
            for name, value, model_field in zip(self.ordering, values, fields):
                field = name.lstrip('-')
                if value is not None:
                    comparison = Q(**{field + ('__lt' if name.startswith('-') else '__gt'): value})
                    if model_field.null:
                        comparison |= Q(**{field + '__isnull': True})
                    predicate |= equal & comparison
                equal &= Q(**{field: value})
            queryset = queryset.filter(predicate)
        ordering = [(F(name.lstrip('-')).desc(nulls_last=True) if name.startswith('-')
                     else F(name).asc(nulls_last=True)) if field.null else name
                    for name, field in zip(self.ordering, fields)]
        rows = list(queryset.order_by(*ordering)[:self.page_size + 1])
        self.page = rows[:self.page_size]
        if len(rows) > self.page_size:
            self.next_values = [self.position_value(self.page[-1], name) for name in self.ordering]
        return self.page

    def get_next_link(self):
        if self.next_values is None:
            return None
        parts = urlsplit(self.base_url)
        params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != self.cursor_query_param]
        params.append((self.cursor_query_param, signing.dumps(self.next_values, salt=self.cursor_salt + ':ordered')))
        return urlunsplit(parts._replace(query=urlencode(params)))

    def get_previous_link(self):
        return None


class PagedAPIView(APIView):
    """Explicit opt-in for custom list views; permissions run before pagination."""
    pagination_class = BoundedCursorPagination

    def page(self, request, queryset):
        self.list_paginator = self.pagination_class()
        return self.list_paginator.paginate_queryset(queryset, request, view=self)

    def finalize_response(self, request, response, *args, **kwargs):
        if hasattr(self, 'list_paginator') and response.status_code == 200:
            paged = self.list_paginator.get_paginated_response(response.data)
            for key, value in paged.items():
                response[key] = value
            response.data = paged.data
        return super().finalize_response(request, response, *args, **kwargs)
