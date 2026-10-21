from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MarketInvoice, MarketRefund, MarketTransaction
from .views import Authenticated, MarketPagination
from . import payment_services as services


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Unexpected fields; amounts, fees and transaction state are server controlled.']})
        return super().to_internal_value(data)


class RefundInput(StrictInput):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(max_length=3000)
    idempotency_key = serializers.UUIDField()


class DecisionInput(StrictInput):
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'])
    reason = serializers.CharField(max_length=3000)


class VoidInput(StrictInput):
    action = serializers.ChoiceField(choices=['VOID'])
    reason = serializers.CharField(max_length=3000)


class InvoiceData(serializers.ModelSerializer):
    remaining_amount = serializers.SerializerMethodField()
    mode = serializers.SerializerMethodField()
    collection = serializers.SerializerMethodField()

    class Meta:
        model = MarketInvoice
        fields = ['id', 'reference', 'booking_id', 'status', 'amount', 'currency', 'fee_bps', 'fee_amount',
            'talent_amount', 'credited_amount', 'credited_fee', 'remaining_amount', 'snapshot', 'issued_by_id',
            'issued_at', 'mode', 'collection']

    def get_remaining_amount(self, row):
        return format(row.amount-row.credited_amount if row.status != 'VOID' else 0, '.2f')

    def get_mode(self, row):
        return 'RECORD_ONLY'

    def get_collection(self, row):
        return 'NONE'


class RefundData(serializers.ModelSerializer):
    mode = serializers.CharField(read_only=True, default='RECORD_ONLY')

    class Meta:
        model = MarketRefund
        fields = ['id', 'invoice_id', 'idempotency_key', 'amount', 'reason', 'status', 'requested_by_id',
            'requested_at', 'decided_by_id', 'decided_at', 'decision_reason', 'mode']


class TransactionData(serializers.ModelSerializer):
    mode = serializers.CharField(read_only=True, default='RECORD_ONLY')

    class Meta:
        model = MarketTransaction
        fields = ['id', 'reference', 'invoice_id', 'refund_id', 'kind', 'amount', 'fee_amount',
            'talent_amount', 'currency', 'actor_id', 'reason', 'created_at', 'mode']


class FinancialAPI(Authenticated, APIView):
    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def invoice(self, request, pk):
        return services.locked_invoice(pk, request.user)[1]

    def page(self, request, rows, serializer):
        pager = MarketPagination()
        return pager.get_paginated_response(serializer(pager.paginate_queryset(rows, request), many=True).data)


class Invoice(FinancialAPI):
    def get(self, request, pk):
        return Response(InvoiceData(self.invoice(request, pk)).data)

    def post(self, request, pk):
        value = StrictInput(data=request.data); value.is_valid(raise_exception=True)
        invoice, created = services.issue(pk, request.user)
        return Response(InvoiceData(invoice).data, status=201 if created else 200)

    def patch(self, request, pk):
        value = VoidInput(data=request.data); value.is_valid(raise_exception=True)
        return Response(InvoiceData(services.void(pk, request.user, value.validated_data['reason'])).data)


class Refunds(FinancialAPI):
    def get(self, request, pk):
        return self.page(request, self.invoice(request, pk).refunds.all(), RefundData)

    def post(self, request, pk):
        value = RefundInput(data=request.data); value.is_valid(raise_exception=True)
        refund, created = services.request_refund(pk, request.user, **value.validated_data)
        return Response(RefundData(refund).data, status=201 if created else 200)


class RefundDecision(FinancialAPI):
    def post(self, request, pk, refund_id):
        value = DecisionInput(data=request.data); value.is_valid(raise_exception=True)
        refund = services.decide_refund(pk, request.user, refund_id, **value.validated_data)
        return Response(RefundData(refund).data)


class Transactions(FinancialAPI):
    def get(self, request, pk):
        return self.page(request, self.invoice(request, pk).transactions.all(), TransactionData)
