from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from talents.models import TalentProfile
from domains.models import TalentDomain
from accounts.models import UserBlock
from .models import Listing, Offer
from .serializers import ListingSerializer, OfferSerializer, MessageSerializer
from .permissions import active, blocked, can_offer, require_participant


class Authenticated:
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not active(request.user):
            raise PermissionDenied("Account inactive.")


def visible(user):
    blocked_ids = list(UserBlock.objects.filter(user=user).values_list("blocked_user_id", flat=True))
    blocked_ids += list(UserBlock.objects.filter(blocked_user=user).values_list("user_id", flat=True))
    return Listing.objects.select_related("talent__user", "subecosystem").filter(
        Q(talent__user=user) | Q(status="PUBLISHED", publication_consented_at__isnull=False,
                               talent__profile_visibility="PUBLIC", talent__user__is_active=True)
    ).exclude(talent__user_id__in=blocked_ids)


class MarketPagination(PageNumberPagination):
    page_size = 24


class Listings(Authenticated, generics.ListCreateAPIView):
    serializer_class = ListingSerializer
    pagination_class = MarketPagination

    def get_queryset(self):
        qs = visible(self.request.user)
        p = self.request.query_params
        if p.get("mine") == "1":
            qs = qs.filter(talent__user=self.request.user)
        for key, field in {"ecosystem": "ecosystem", "subecosystem": "subecosystem_id", "country": "talent__country__iexact", "work_type": "talent__preferred_work_type", "experience": "talent__experience_level", "skill": "talent__skills__name__icontains"}.items():
            if p.get(key):
                if key == "subecosystem" and not p[key].isdigit():
                    raise ValidationError({key: "Expected a domain ID."})
                qs = qs.filter(**{field: p[key]})
        if p.get("q"):
            qs = qs.filter(Q(title__icontains=p["q"]) | Q(description__icontains=p["q"]) | Q(talent__user__username__icontains=p["q"]))
        return qs.distinct()

    def perform_create(self, serializer):
        talent = get_object_or_404(TalentProfile, user=self.request.user)
        consent = serializer.validated_data.pop("consent", False)
        serializer.save(talent=talent, publication_consented_at=timezone.now() if consent else None)


class ListingDetail(Authenticated, generics.RetrieveUpdateAPIView):
    serializer_class = ListingSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return visible(self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.talent.user_id != self.request.user.pk:
            raise PermissionDenied("Only the talent may edit this listing.")
        consent = serializer.validated_data.pop("consent", False)
        serializer.save(**({"publication_consented_at": timezone.now()} if consent else {}))


class Markets(Authenticated, APIView):
    def get(self, request):
        return Response({"ecosystems": [{"id": k, "name": v} for k, v in TalentProfile.TALENT_CATEGORY_CHOICES],
                         "subecosystems": list(TalentDomain.objects.order_by("name").values("id", "name"))})


class Offers(Authenticated, generics.ListCreateAPIView):
    serializer_class = OfferSerializer
    pagination_class = MarketPagination

    def get_queryset(self):
        candidates = Offer.objects.select_related("listing__talent", "organization").filter(
            Q(sender=self.request.user) | Q(listing__talent__user=self.request.user))
        ids = []
        for offer in candidates:
            try:
                require_participant(self.request.user, offer)
                ids.append(offer.pk)
            except PermissionDenied:
                pass
        return candidates.filter(pk__in=ids)

    @transaction.atomic
    def perform_create(self, serializer):
        listing = get_object_or_404(visible(self.request.user).select_for_update(of=("self",)), pk=serializer.validated_data["listing"].pk)
        if listing.talent.user_id == self.request.user.pk or listing.status != "PUBLISHED":
            raise ValidationError("Select another talent's published listing.")
        if not can_offer(self.request.user, serializer.validated_data.get("organization")):
            raise PermissionDenied("A verified scout/coach or authorized organization recruiter is required.")
        organization = serializer.validated_data.get("organization")
        pending = Offer.objects.filter(listing=listing, status="PENDING", organization=organization)
        if organization is None:
            pending = pending.filter(sender=self.request.user)
        if pending.exists():
            raise ValidationError("A pending offer already exists for this listing and sender or organization.")
        try:
            with transaction.atomic():
                serializer.save(sender=self.request.user)
        except IntegrityError:
            if pending.exists():
                raise ValidationError("A pending offer already exists for this listing and sender or organization.") from None
            raise


class DecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["ACCEPT", "DECLINE", "WITHDRAW"])
    consent = serializers.BooleanField(required=False, default=False)


class Deal(Authenticated, APIView):
    def get(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        require_participant(request.user, offer)
        return Response({"offer": OfferSerializer(offer).data, "messages": MessageSerializer(offer.messages.all()[:200], many=True).data})

    @transaction.atomic
    def post(self, request, pk):
        offer = get_object_or_404(Offer.objects.select_for_update(), pk=pk)
        require_participant(request.user, offer)
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        action = data.validated_data["action"]
        if offer.status != "PENDING":
            raise ValidationError("This offer already has a final decision.")
        talent = request.user.pk == offer.listing.talent.user_id
        if (action == "WITHDRAW" and talent) or (action != "WITHDRAW" and not talent):
            raise PermissionDenied("Only the talent can accept or decline; only the sender can withdraw.")
        if action == "ACCEPT" and not data.validated_data["consent"]:
            raise ValidationError("Explicit talent consent is required to accept these terms.")
        offer.status = {"ACCEPT": "ACCEPTED", "DECLINE": "DECLINED", "WITHDRAW": "WITHDRAWN"}[action]
        offer.decided_at = timezone.now()
        if action == "ACCEPT":
            offer.talent_consented_at = offer.decided_at
        offer.save(update_fields=["status", "decided_at", "talent_consented_at"])
        return Response(OfferSerializer(offer).data)


class Messages(Authenticated, APIView):
    @transaction.atomic
    def post(self, request, pk):
        offer = get_object_or_404(Offer.objects.select_for_update(), pk=pk)
        require_participant(request.user, offer)
        if offer.status != "PENDING":
            raise ValidationError("This deal room is read-only after a decision.")
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(offer=offer, author=request.user)
        return Response(serializer.data, status=201)


@login_required
def market(request):
    return render(request, "marketplace/market.html")
