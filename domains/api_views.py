from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import TalentDomain
from .serializers import TalentDomainSerializer


# ============================================================
# TALENT DOMAINS
# ============================================================

class TalentDomainListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    queryset = TalentDomain.objects.all().order_by("name")

    serializer_class = TalentDomainSerializer


# ============================================================
# TALENT DOMAIN DETAIL
# ============================================================

class TalentDomainDetailAPIView(generics.RetrieveAPIView):

    permission_classes = [IsAuthenticated]

    queryset = TalentDomain.objects.all()

    serializer_class = TalentDomainSerializer

    lookup_url_kwarg = "domain_id"