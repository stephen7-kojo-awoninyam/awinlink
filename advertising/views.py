import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from organizations.models import Organization

from .forms import AdvertisementForm, CampaignForm
from .models import Advertisement, AdvertisementEvent, Campaign, CampaignPayment
from .services import (
    CampaignTransitionError,
    InvalidTrackingToken,
    record_ad_event,
    transition_campaign,
)

logger = logging.getLogger(__name__)
PAYSTACK_API_URL = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def _organization_for_user(user):
    if user.role != "ORGANIZATION":
        return None
    return Organization.objects.filter(user=user).first()


def _owned_campaign(user, campaign_id):
    organization = _organization_for_user(user)
    if organization is None:
        raise PermissionDenied("Only organizations can manage ad campaigns.")
    return get_object_or_404(
        Campaign.objects.select_related("organization"),
        pk=campaign_id,
        organization=organization,
    )


def _get_campaign_metrics(campaign):
    counts = {
        row["event_type"]: row["total"]
        for row in AdvertisementEvent.objects.filter(
            advertisement__campaign=campaign
        )
        .values("event_type")
        .annotate(total=Count("id"))
    }
    return {
        "impressions": counts.get("IMPRESSION", 0),
        "clicks": counts.get("CLICK", 0),
        "video_views": counts.get("VIDEO_VIEW", 0),
        "spent": campaign.spent_amount,
        "remaining": campaign.remaining_budget,
    }


@login_required
def advertiser_dashboard(request):
    organization = _organization_for_user(request.user)
    if organization is None:
        messages.error(request, "Advertising campaigns are available to organizations.")
        return redirect("home_feed")
    campaigns = list(
        Campaign.objects.filter(organization=organization)
        .prefetch_related("payments")
        .order_by("-created_at")
    )
    for campaign in campaigns:
        campaign.dashboard_metrics = _get_campaign_metrics(campaign)
    return render(
        request,
        "advertising/dashboard.html",
        {"organization": organization, "campaigns": campaigns},
    )


@login_required
def campaign_create(request):
    organization = _organization_for_user(request.user)
    if organization is None:
        messages.error(request, "Only organizations can create advertising campaigns.")
        return redirect("home_feed")
    campaign_form = CampaignForm(request.POST or None)
    advertisement_form = AdvertisementForm(
        request.POST or None,
        request.FILES or None,
    )
    if (
        request.method == "POST"
        and campaign_form.is_valid()
        and advertisement_form.is_valid()
    ):
        campaign = campaign_form.save(commit=False)
        campaign.organization = organization
        campaign.currency = getattr(settings, "ADVERTISING_CURRENCY", "GHS")
        campaign.save()
        campaign_form.save_m2m()
        advertisement = advertisement_form.save(commit=False)
        advertisement.campaign = campaign
        advertisement.save()
        messages.success(
            request,
            "Campaign saved as a draft. Submit it for review when ready.",
        )
        return redirect("advertising_dashboard")
    return render(
        request,
        "advertising/campaign_form.html",
        {
            "campaign_form": campaign_form,
            "advertisement_form": advertisement_form,
        },
    )


@login_required
def campaign_edit(request, campaign_id):
    campaign = _owned_campaign(request.user, campaign_id)
    if campaign.status not in {"DRAFT", "REJECTED"}:
        messages.error(request, "Only draft or rejected campaigns can be edited.")
        return redirect("advertising_dashboard")
    advertisement = Advertisement.objects.filter(campaign=campaign).first()
    campaign_form = CampaignForm(request.POST or None, instance=campaign)
    advertisement_form = AdvertisementForm(
        request.POST or None,
        request.FILES or None,
        instance=advertisement,
    )
    if (
        request.method == "POST"
        and campaign_form.is_valid()
        and advertisement_form.is_valid()
    ):
        campaign_form.save()
        saved_advertisement = advertisement_form.save(commit=False)
        saved_advertisement.campaign = campaign
        saved_advertisement.save()
        messages.success(request, "Campaign draft updated.")
        return redirect("advertising_dashboard")
    return render(
        request,
        "advertising/campaign_form.html",
        {
            "campaign_form": campaign_form,
            "advertisement_form": advertisement_form,
            "editing": True,
        },
    )


@login_required
@require_POST
def campaign_action(request, campaign_id, action):
    campaign = _owned_campaign(request.user, campaign_id)
    target_statuses = {
        "submit": "PENDING_REVIEW",
        "activate": "ACTIVE",
        "pause": "PAUSED",
        "cancel": "CANCELLED",
    }
    new_status = target_statuses.get(action)
    if new_status is None:
        return HttpResponse(status=404)
    try:
        transition_campaign(campaign.pk, request.user, new_status)
    except CampaignTransitionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Campaign status changed to {new_status.replace('_', ' ').lower()}.",
        )
    return redirect("advertising_dashboard")


def _paystack_request(endpoint, payload=None):
    secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        raise PaystackError(
            "Paystack is not configured. Contact the platform administrator."
        )
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    api_request = Request(
        f"{PAYSTACK_API_URL}{endpoint}",
        data=body,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(api_request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise PaystackError("Could not contact Paystack. Please try again.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaystackError("Paystack returned an invalid response.") from exc
    if not isinstance(result, dict) or result.get("status") is not True:
        raise PaystackError("Paystack could not process this request.")
    return result


def _verified_transaction(payment):
    result = _paystack_request(f"/transaction/verify/{payment.reference}")
    data = result.get("data")
    if not isinstance(data, dict):
        raise PaystackError("Paystack returned incomplete payment details.")
    if (
        data.get("reference") != payment.reference
        or data.get("amount") != int(payment.amount * 100)
        or data.get("currency") != payment.currency
    ):
        raise PaystackError("Payment verification did not match the campaign charge.")
    return data


def _mark_payment_success(payment_id):
    with transaction.atomic():
        payment = CampaignPayment.objects.select_for_update().get(pk=payment_id)
        if payment.status != "SUCCESS":
            payment.status = "SUCCESS"
            payment.paid_at = timezone.now()
            payment.save(update_fields=("status", "paid_at"))
    return payment


def _mark_payment_failed(payment_id):
    with transaction.atomic():
        payment = CampaignPayment.objects.select_for_update().get(pk=payment_id)
        if payment.status == "PENDING":
            payment.status = "FAILED"
            payment.save(update_fields=("status",))
    return payment


@login_required
@require_POST
def fund_campaign(request, campaign_id):
    campaign = _owned_campaign(request.user, campaign_id)
    if campaign.status not in {"APPROVED", "ACTIVE", "PAUSED"}:
        messages.error(request, "Only approved campaigns can be funded.")
        return redirect("advertising_dashboard")
    try:
        amount = Decimal(request.POST.get("amount", ""))
    except InvalidOperation:
        messages.error(request, "Enter a valid funding amount.")
        return redirect("advertising_dashboard")
    if (
        not amount.is_finite()
        or amount <= 0
        or amount.as_tuple().exponent < -2
        or amount > campaign.remaining_to_fund
    ):
        messages.error(
            request,
            "Funding must be positive, use at most two decimal places, and fit within the campaign budget.",
        )
        return redirect("advertising_dashboard")

    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
        if (
            campaign.status not in {"APPROVED", "ACTIVE", "PAUSED"}
            or amount > campaign.remaining_to_fund
        ):
            messages.error(
                request,
                "This funding amount is no longer available for the campaign.",
            )
            return redirect("advertising_dashboard")
        payment = CampaignPayment.objects.create(
            campaign=campaign,
            reference=uuid.uuid4().hex,
            amount=amount,
            currency=campaign.currency,
        )
    try:
        result = _paystack_request(
            "/transaction/initialize",
            {
                "email": request.user.email,
                "amount": int(amount * 100),
                "currency": payment.currency,
                "reference": payment.reference,
                "callback_url": request.build_absolute_uri(
                    reverse("advertising_paystack_callback")
                ),
                "metadata": {
                    "campaign_id": campaign.pk,
                    "payment_id": payment.pk,
                },
            },
        )
    except PaystackError as exc:
        payment.status = "FAILED"
        payment.save(update_fields=("status",))
        messages.error(request, str(exc))
        return redirect("advertising_dashboard")

    data = result.get("data")
    authorization_url = data.get("authorization_url") if isinstance(data, dict) else None
    if not authorization_url:
        payment.status = "FAILED"
        payment.save(update_fields=("status",))
        messages.error(request, "Paystack did not return a checkout link.")
        return redirect("advertising_dashboard")
    payment.authorization_url = authorization_url
    payment.save(update_fields=("authorization_url",))
    return redirect(authorization_url)


@login_required
def paystack_callback(request):
    reference = request.GET.get("reference", "")
    payment = get_object_or_404(
        CampaignPayment.objects.select_related("campaign", "campaign__organization"),
        reference=reference,
        campaign__organization__user=request.user,
    )
    try:
        transaction_data = _verified_transaction(payment)
    except PaystackError as exc:
        messages.error(request, str(exc))
        return redirect("advertising_dashboard")
    if transaction_data.get("status") == "success":
        _mark_payment_success(payment.pk)
        messages.success(request, "Campaign funding payment verified.")
    elif transaction_data.get("status") in {"failed", "abandoned"}:
        _mark_payment_failed(payment.pk)
        messages.error(request, "Paystack did not complete the campaign payment.")
    else:
        messages.error(request, "Paystack has not confirmed this payment yet.")
    return redirect("advertising_dashboard")


@csrf_exempt
@require_POST
def paystack_webhook(request):
    secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        return JsonResponse({"detail": "Paystack is not configured."}, status=503)
    signature = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(
        secret_key.encode("utf-8"),
        request.body,
        hashlib.sha512,
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=401)
    try:
        event = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"detail": "Invalid webhook payload."}, status=400)
    if not isinstance(event, dict) or event.get("event") not in {
        "charge.success",
        "charge.failed",
    }:
        return JsonResponse({"status": "ignored"})
    data = event.get("data")
    if not isinstance(data, dict) or not data.get("reference"):
        return JsonResponse({"detail": "Missing payment reference."}, status=400)
    payment = CampaignPayment.objects.filter(
        reference=data["reference"],
        status="PENDING",
    ).first()
    if payment is None:
        return JsonResponse({"status": "already processed or unknown"})
    try:
        transaction_data = _verified_transaction(payment)
    except PaystackError:
        logger.exception("Paystack webhook payment verification failed.")
        return JsonResponse({"detail": "Payment verification failed."}, status=502)
    if transaction_data.get("status") == "success":
        _mark_payment_success(payment.pk)
    elif transaction_data.get("status") in {"failed", "abandoned"}:
        _mark_payment_failed(payment.pk)
    else:
        return JsonResponse({"status": "pending"})
    return JsonResponse({"status": "ok"})


@login_required
def advertisement_click(request, advertisement_id):
    advertisement = get_object_or_404(
        Advertisement.objects.select_related("campaign"),
        pk=advertisement_id,
    )
    try:
        record_ad_event(
            advertisement.pk,
            request.user,
            "CLICK",
            request.GET.get("token", ""),
        )
    except InvalidTrackingToken as exc:
        raise Http404("Invalid advertisement click link.") from exc
    return redirect(advertisement.destination_url)


@login_required
@require_POST
def advertisement_impression(request, advertisement_id):
    advertisement = get_object_or_404(Advertisement, pk=advertisement_id)
    try:
        recorded = record_ad_event(
            advertisement.pk,
            request.user,
            "IMPRESSION",
            request.POST.get("token", ""),
        )
    except InvalidTrackingToken as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    if not recorded:
        return JsonResponse(
            {"detail": "Advertisement is no longer eligible for delivery."},
            status=409,
        )
    return JsonResponse({"status": "recorded"})


@login_required
@require_POST
def advertisement_video_view(request, advertisement_id):
    advertisement = get_object_or_404(
        Advertisement.objects.select_related("campaign"),
        pk=advertisement_id,
        video__isnull=False,
    )
    try:
        recorded = record_ad_event(
            advertisement.pk,
            request.user,
            "VIDEO_VIEW",
            request.POST.get("token", ""),
        )
    except InvalidTrackingToken as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    if not recorded:
        return JsonResponse(
            {"detail": "Advertisement is no longer active."},
            status=410,
        )
    return JsonResponse({"status": "recorded"})
