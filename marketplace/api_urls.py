from django.urls import path
from . import views
from . import booking_views as bookings
from . import payment_views as payments

app_name = "marketplace_api"
urlpatterns = [
    path('bookings/<int:pk>/invoice/', payments.Invoice.as_view(), name='invoice'),
    path('bookings/<int:pk>/invoice/refunds/', payments.Refunds.as_view(), name='refunds'),
    path('bookings/<int:pk>/invoice/refunds/<int:refund_id>/', payments.RefundDecision.as_view(), name='refund-decision'),
    path('bookings/<int:pk>/invoice/transactions/', payments.Transactions.as_view(), name='transactions'),
    path('availability/', bookings.Availability.as_view(), name='availability'),
    path('availability/<int:pk>/', bookings.AvailabilityDetail.as_view(), name='availability-detail'),
    path('bookings/', bookings.Bookings.as_view(), name='bookings'),
    path('bookings/<int:pk>/', bookings.BookingDetail.as_view(), name='booking'),
    path('bookings/<int:pk>/messages/', bookings.BookingMessages.as_view(), name='booking-messages'),
    path('bookings/<int:pk>/events/', bookings.BookingEvents.as_view(), name='booking-events'),
    path('bookings/<int:pk>/submissions/', bookings.Submissions.as_view(), name='submissions'),
    path('bookings/<int:pk>/submissions/<int:submission_id>/artifact/', bookings.Artifact.as_view(), name='artifact'),
    path('bookings/<int:pk>/reviews/', bookings.Reviews.as_view(), name='review'),
    path('listings/<int:pk>/reviews/', bookings.PublicReviews.as_view(), name='public-reviews'),
    path("markets/", views.Markets.as_view(), name="markets"),
    path("listings/", views.Listings.as_view(), name="listings"),
    path("listings/<int:pk>/", views.ListingDetail.as_view(), name="listing"),
    path("offers/", views.Offers.as_view(), name="offers"),
    path("deals/<int:pk>/", views.Deal.as_view(), name="deal"),
    path("deals/<int:pk>/messages/", views.Messages.as_view(), name="messages"),
]
