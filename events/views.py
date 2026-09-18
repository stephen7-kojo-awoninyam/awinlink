from django.contrib import messages
from django.db.models.functions import TruncMonth
from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required


from .models import Event, EventRegistration, EventFeedback, EventCertificate, EventMedia
from .forms import EventForm, EventFeedbackForm, EventCertificateForm


from organizations.models import Organization
from talents.models import TalentProfile
from django.db import models

from notifications.models import Notification

from feed.models import Post

from django.db.models import Avg, Count, Q

from django.utils import timezone

from .services import EventRecommendationEngine, CertificateGenerator

from django.contrib.auth.decorators import user_passes_test

from .forms import EventMediaForm

import uuid



def can_create_event(user):
    """
    Only authenticated Organization accounts can
    create and manage events.

    Event certificates are issued on behalf of
    an Organization, so individual users and
    platform administrators cannot create events.
    """

    return (
        user.is_authenticated
        and user.role == "ORGANIZATION"
    )
    
def is_event_organizer(user):
    """
    Only authenticated Organization accounts can
    manage events and event-related activities.
    """

    return (
        user.is_authenticated
        and user.role == "ORGANIZATION"
    )


@login_required
@user_passes_test(can_create_event)
def create_event(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )


    if request.method == "POST":

        form = EventForm(
            request.POST,
            request.FILES
        )


        if form.is_valid():

            event = form.save(
                commit=False
            )


            event.organizer = organization

            event.status = "PUBLISHED"


            event.save()
            Post.objects.create(

                author=request.user,

                organization=organization,

                event=event,

                caption=f"{organization.name} created a new event: {event.title}",

                post_type="ANNOUNCEMENT"

            )


            return redirect(
                "organization_dashboard"
            )


    else:

        form = EventForm()


    return render(
        request,
        "events/create_event.html",
        {
            "form": form
        }
    )
    

@login_required
def register_event(request, event_id):

    # ==========================================
    # GET EVENT
    # ==========================================

    event = get_object_or_404(
        Event,
        id=event_id
    )


    # ==========================================
    # 1. CHECK EVENT STATUS
    # ==========================================

    if event.status != "PUBLISHED":

        messages.warning(
            request,
            "This event is not currently open for registration."
        )

        return redirect(
            "event_detail",
            event_id=event.id
        )


    # ==========================================
    # 2. CHECK REGISTRATION DEADLINE
    # ==========================================

    now = timezone.now()

    if event.registration_deadline <= now:

        messages.warning(
            request,
            "Registration for this event has closed."
        )

        return redirect(
            "event_detail",
            event_id=event.id
        )


    # ==========================================
    # 3. GET TALENT PROFILE
    # ==========================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # ==========================================
    # 4. CHECK IF ALREADY REGISTERED
    # ==========================================

    existing_registration = EventRegistration.objects.filter(
        event=event,
        talent=talent
    ).first()


    if existing_registration:

        if existing_registration.status == "CANCELLED":

            # Allow the talent to register again
            existing_registration.status = "REGISTERED"
            existing_registration.registered_at = timezone.now()
            existing_registration.save()

            messages.success(
                request,
                "You have successfully registered for the event again."
            )

            return redirect(
                "event_detail",
                event_id=event.id
            )


        messages.info(
            request,
            "You are already registered for this event."
        )

        return redirect(
            "event_detail",
            event_id=event.id
        )


    # ==========================================
    # 5. CHECK EVENT CAPACITY
    # ==========================================

    if event.capacity > 0:

        current_registrations = EventRegistration.objects.filter(
            event=event
        ).exclude(
            status="CANCELLED"
        ).count()


        if current_registrations >= event.capacity:

            messages.warning(
                request,
                "This event has reached its maximum capacity."
            )

            return redirect(
                "event_detail",
                event_id=event.id
            )


        # ==========================================
        # 6. CREATE REGISTRATION
        # ==========================================

    registration = EventRegistration.objects.create(

        event=event,

        talent=talent,

        status="REGISTERED"

    )


    # ==========================================
    # 7. NOTIFY ORGANIZATION
    # ==========================================

    Notification.objects.create(

        user=event.organizer.user,

        sender=request.user,

        notification_type="SYSTEM",

        message=(
            f"{request.user.get_full_name() or request.user.username} "
            f"registered for your event: {event.title}"
        )

    )


    # ==========================================
    # 8. SUCCESS MESSAGE
    # ==========================================

    messages.success(
        request,
        f"You successfully registered for {event.title}."
    )


    return redirect(
        "event_detail",
        event_id=event.id
    )
    
    
    
@login_required
def event_list(request):


    events = Event.objects.filter(

        status="PUBLISHED"

    ).order_by(

        "-created_at"

    )


    return render(

        request,

        "events/event_list.html",

        {
            "events":events
        }

    )    
    
    
@login_required
def event_detail(request, event_id):

    event = get_object_or_404(
        Event,
        id=event_id
    )

    # ==========================================
    # CURRENT USER REGISTRATION
    # ==========================================

    registered = False
    current_registration = None

    try:

        talent = TalentProfile.objects.get(
            user=request.user
        )

        current_registration = EventRegistration.objects.filter(
            event=event,
            talent=talent
        ).first()

        if current_registration:
            registered = True

    except TalentProfile.DoesNotExist:

        pass


    # ==========================================
    # EVENT FEEDBACK
    # ==========================================

    feedbacks = event.feedback.select_related(
        "reviewer"
    ).all()

    feedback_summary = event.feedback.aggregate(
        average_rating=Avg("rating"),
        total_feedback=Count("id")
    )


    # ==========================================
    # PARTICIPANTS
    # ==========================================

    participants = event.registrations.select_related(
        "talent",
        "talent__user"
    ).filter(
        status__in=[
            "REGISTERED",
            "APPROVED",
            "ATTENDED"
        ]
    )


    # ==========================================
    # CAPACITY
    # ==========================================

    total_registrations = EventRegistration.objects.filter(
        event=event
    ).exclude(
        status="CANCELLED"
    ).count()


    capacity_full = False

    if event.capacity > 0:

        capacity_full = (
            total_registrations >= event.capacity
        )


    # ==========================================
    # EVENT GALLERY
    # ==========================================

    media = event.media.all()


    # ==========================================
    # CONTEXT
    # ==========================================

    context = {

        "event": event,

        "registered": registered,

        "current_registration": current_registration,

        "participants": participants,

        "feedbacks": feedbacks,

        "feedback_summary": feedback_summary,

        "total_registrations": total_registrations,

        "capacity_full": capacity_full,

        "media": media,

    }


    return render(
        request,
        "events/event_details.html",
        context
    ) 
    
    
    
@login_required
def my_events(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    registrations = EventRegistration.objects.filter(

        talent=talent

    ).select_related(

        "event",

        "event__category"

    )



    return render(

        request,

        "events/my_events.html",

        {

            "registrations": registrations

        }

    )    
    
@login_required
def cancel_registration(request, event_id):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    registration = get_object_or_404(
        EventRegistration,
        event_id=event_id,
        talent=talent
    )

    if registration.status in ["ATTENDED", "CANCELLED"]:

        messages.warning(
            request,
            "This registration cannot be cancelled."
        )

        return redirect(
            "my_events"
        )


    registration.status = "CANCELLED"

    registration.save()


    messages.success(
        request,
        "Your event registration has been cancelled."
    )


    return redirect(
        "my_events"
    )  
    


@login_required
@user_passes_test(is_event_organizer)
def organization_events(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )


    events = Event.objects.filter(
        organizer=organization
    ).annotate(

        participants=Count(
            "registrations",
            distinct=True
        ),


        approved=Count(
            "registrations",
            filter=Q(
                registrations__status="APPROVED"
            ),
            distinct=True
        ),


        attended=Count(
            "registrations",
            filter=Q(
                registrations__status="ATTENDED"
            ),
            distinct=True
        ),


        certificates=Count(
            "certificates",
            distinct=True
        ),


        rating=Avg(
            "feedback__rating"
        )

    ).order_by(
        "-created_at"
    )



    # ==================================
    # DASHBOARD SUMMARY
    # ==================================


    total_events = events.count()



    total_participants = EventRegistration.objects.filter(

        event__organizer=organization

    ).count()



    total_approved = EventRegistration.objects.filter(

        event__organizer=organization,

        status="APPROVED"

    ).count()



    total_attendance = EventRegistration.objects.filter(

        event__organizer=organization,

        status="ATTENDED"

    ).count()



    total_certificates = EventCertificate.objects.filter(

        event__organizer=organization

    ).count()



    # ==================================
    # REGISTRATION TREND
    # ==================================


    registration_chart = EventRegistration.objects.filter(

        event__organizer=organization

    ).annotate(

        month=TruncMonth(
            "registered_at"
        )

    ).values(

        "month"

    ).annotate(

        total=Count("id")

    ).order_by(

        "month"

    )



    # ==================================
    # TOP EVENTS
    # ==================================


    top_events = events.order_by(

        "-participants"

    )[:5]



    context = {


        # Event list

        "events": events,


        # Summary cards

        "total_events": total_events,

        "total_participants": total_participants,

        "total_approved": total_approved,

        "total_attendance": total_attendance,

        "total_certificates": total_certificates,


        # Charts

        "registration_chart": list(
            registration_chart
        ),


        # Ranking

        "top_events": top_events,

    }



    return render(

        request,

        "events/organization_events.html",

        context

    )
    
    
@login_required
@user_passes_test(is_event_organizer)
def reject_registration(request, registration_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    registration = get_object_or_404(
        EventRegistration,
        id=registration_id,
        event__organizer=organization
    )

    if registration.status not in [
        "REGISTERED",
        "APPROVED"
    ]:

        messages.warning(
            request,
            "This registration cannot be rejected."
        )

        return redirect(
            "event_participants",
            event_id=registration.event.id
        )

    registration.status = "REJECTED"
    registration.save()

    # Notify talent
    if registration.talent:

        Notification.objects.create(
            user=registration.talent.user,
            sender=request.user,
            notification_type="SYSTEM",
            message=(
                f"Your registration for "
                f"{registration.event.title} "
                f"has been rejected."
            )
        )

    messages.success(
        request,
        "Participant registration rejected."
    )

    return redirect(
        "event_participants",
        event_id=registration.event.id
    )
    
    
    
@login_required
@user_passes_test(is_event_organizer)
def event_participants(request, event_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id,
        organizer=organization
    )

    registrations = EventRegistration.objects.filter(
        event=event
    ).select_related(
        "talent",
        "talent__user"
    )

    certificates = EventCertificate.objects.filter(
        event=event
    ).select_related(
        "talent",
        "talent__user"
    )

    certificate_map = {
        certificate.talent_id: certificate
        for certificate in certificates
    }

    for registration in registrations:

        registration.certificate = certificate_map.get(
            registration.talent_id
        )

    return render(
        request,
        "events/event_participants.html",
        {
            "event": event,
            "registrations": registrations
        }
    )
     

@login_required
@user_passes_test(is_event_organizer)
def mark_attendance(request, registration_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    registration = get_object_or_404(
        EventRegistration,
        id=registration_id,
        event__organizer=organization
    )

    # ==========================================
    # ONLY APPROVED PARTICIPANTS CAN ATTEND
    # ==========================================

    if registration.status != "APPROVED":

        messages.warning(
            request,
            "Only approved participants can be marked as attended."
        )

        return redirect(
            "event_participants",
            event_id=registration.event.id
        )

    # ==========================================
    # MARK ATTENDANCE
    # ==========================================

    registration.status = "ATTENDED"
    registration.attendance_marked = True
    registration.attendance_time = timezone.now()

    registration.save(
        update_fields=[
            "status",
            "attendance_marked",
            "attendance_time"
        ]
    )

    # ==========================================
    # GENERATE CERTIFICATE
    # ==========================================

    certificate = CertificateGenerator.generate(
        registration.event,
        registration.talent
    )

    # ==========================================
    # NOTIFY TALENT
    # ==========================================

    Notification.objects.create(
        user=registration.talent.user,
        sender=request.user,
        notification_type="SYSTEM",
        message=(
            f"You attended {registration.event.title}. "
            f"Your certificate has been generated."
        )
    )

    # ==========================================
    # SUCCESS MESSAGE
    # ==========================================

    messages.success(
        request,
        "Attendance marked and certificate generated."
    )

    return redirect(
        "event_participants",
        event_id=registration.event.id
    )
    
 
    
    
@login_required
@user_passes_test(is_event_organizer)
def issue_certificate(request, event_id, registration_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id,
        organizer=organization
    )

    registration = get_object_or_404(
        EventRegistration,
        id=registration_id,
        event=event,
        status="ATTENDED"
    )

    if request.method == "POST":

        form = EventCertificateForm(request.POST)

        if form.is_valid():

            certificate = form.save(
                commit=False
            )

            certificate.event = event
            certificate.talent = registration.talent
            certificate.issued_by = organization

            certificate.certificate_code = (
                f"AW-{uuid.uuid4().hex[:8].upper()}"
            )

            certificate.save()

            messages.success(
                request,
                "Certificate issued successfully."
            )

            return redirect(
                "event_participants",
                event_id=event.id
            )

    else:

        form = EventCertificateForm()

    return render(
        request,
        "events/issue_certificate.html",
        {
            "form": form,
            "event": event,
            "registration": registration
        }
    )
    
@login_required
def talent_certificates(request):


    certificates = EventCertificate.objects.filter(

        talent__user=request.user

    ).select_related(

        "event",
        "talent"

    )


    return render(

        request,

        "events/talent_certificates.html",

        {

            "certificates": certificates

        }

    )   
    
     
def verify_certificate(request, certificate_code):

    certificate = get_object_or_404(
        EventCertificate,
        certificate_code=certificate_code,
        verified=True
    )

    return render(
        request,
        "events/verify_certificate.html",
        {
            "certificate": certificate
        }
    )
    
    
    
@login_required
@user_passes_test(is_event_organizer)
def event_dashboard(request, event_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id,
        organizer=organization
    )

    # ==========================================
    # REGISTRATION STATISTICS
    # ==========================================

    total_registrations = EventRegistration.objects.filter(
        event=event
    ).count()

    approved = EventRegistration.objects.filter(
        event=event,
        status="APPROVED"
    ).count()

    rejected = EventRegistration.objects.filter(
        event=event,
        status="REJECTED"
    ).count()

    attended = EventRegistration.objects.filter(
        event=event,
        status="ATTENDED"
    ).count()

    # ==========================================
    # ATTENDANCE RATE
    # ==========================================

    eligible_attendees = EventRegistration.objects.filter(
        event=event,
        status__in=[
            "APPROVED",
            "ATTENDED"
        ]
    ).count()

    attendance_rate = 0

    if eligible_attendees > 0:

        attendance_rate = round(
            (attended / eligible_attendees) * 100,
            2
        )

    # ==========================================
    # AVERAGE RATING
    # ==========================================

    average_rating = event.feedback.aggregate(
        avg=Avg("rating")
    )["avg"]

    # ==========================================
    # CERTIFICATES
    # ==========================================

    certificates = EventCertificate.objects.filter(
        event=event
    ).count()

    # ==========================================
    # CONTEXT
    # ==========================================

    context = {

        "event": event,

        "total_registrations": total_registrations,

        "approved": approved,

        "rejected": rejected,

        "attended": attended,

        "attendance_rate": attendance_rate,

        "average_rating": average_rating,

        "certificates": certificates,

    }

    # ==========================================
    # RENDER
    # ==========================================

    return render(
        request,
        "events/event_dashboard.html",
        context
    )
    
  
    
    
@login_required
def give_feedback(request, event_id):

    event = get_object_or_404(
        Event,
        id=event_id
    )

    registration = get_object_or_404(
        EventRegistration,
        event=event,
        talent__user=request.user,
        status="ATTENDED"
    )

    if EventFeedback.objects.filter(
        event=event,
        reviewer=request.user
    ).exists():

        messages.warning(
            request,
            "You already submitted feedback."
        )

        return redirect(
            "event_detail",
            event_id=event.id
        )

    if request.method == "POST":

        form = EventFeedbackForm(
            request.POST
        )

        if form.is_valid():

            feedback = form.save(
                commit=False
            )

            feedback.event = event
            feedback.reviewer = request.user

            feedback.save()

            messages.success(
                request,
                "Feedback submitted successfully."
            )

            return redirect(
                "event_detail",
                event_id=event.id
            )

    else:

        form = EventFeedbackForm()

    return render(
        request,
        "events/give_feedback.html",
        {
            "event": event,
            "form": form
        }
    )  
    
    
    
@login_required
@user_passes_test(is_event_organizer)
def approve_registration(request, registration_id):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    registration = get_object_or_404(
        EventRegistration,
        id=registration_id,
        event__organizer=organization
    )

    # Only registered participants can be approved
    if registration.status != "REGISTERED":

        messages.warning(
            request,
            "This registration cannot be approved."
        )

        return redirect(
            "event_participants",
            event_id=registration.event.id
        )

    registration.status = "APPROVED"
    registration.save()

    # Notify talent
    if registration.talent:

        Notification.objects.create(
            user=registration.talent.user,
            sender=request.user,
            notification_type="SYSTEM",
            message=(
                f"Your registration for "
                f"{registration.event.title} "
                f"has been approved."
            )
        )

    messages.success(
        request,
        "Participant registration approved."
    )

    return redirect(
        "event_participants",
        event_id=registration.event.id
    )
    
    
    
@login_required
def recommended_events(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )


    events = Event.objects.filter(

        status="PUBLISHED"

    )


    recommendations=[]



    for event in events:


        score = EventRecommendationEngine.calculate_score(

            talent,

            event

        )


        recommendations.append({

            "event":event,

            "score":score

        })



    recommendations.sort(

        key=lambda x:x["score"],

        reverse=True

    )



    return render(

        request,

        "events/recommended_events.html",

        {

            "recommendations":recommendations[:10]

        }

    ) 
       
    
    
@login_required
@user_passes_test(is_event_organizer)
def upload_event_media(request, event_id):

    organization = get_object_or_404(

        Organization,

        user=request.user

    )


    event = get_object_or_404(

        Event,

        id=event_id,

        organizer=organization

    )


    if request.method == "POST":

        form = EventMediaForm(

            request.POST,

            request.FILES

        )

        if form.is_valid():

            media = form.save(

                commit=False

            )

            media.event = event

            media.uploaded_by = organization

            media.save()

            messages.success(

                request,

                "Media uploaded successfully."

            )

            return redirect(

                "event_gallery",

                event.id

            )

    else:

        form = EventMediaForm()


    return render(

        request,

        "events/upload_event_media.html",

        {

            "event": event,

            "form": form

        }

    )   
    
    
@login_required
def event_gallery(request, event_id):

    event = get_object_or_404(

        Event,

        id=event_id

    )


    media = event.media.all()


    return render(

        request,

        "events/event_gallery.html",

        {

            "event": event,

            "media": media

        }

    )  
    
    
    
@login_required
@user_passes_test(is_event_organizer)
def delete_event_media(request, media_id):

    organization = get_object_or_404(

        Organization,

        user=request.user

    )


    media = get_object_or_404(

        EventMedia,

        id=media_id,

        uploaded_by=organization

    )


    event_id = media.event.id

    media.delete()

    messages.success(

        request,

        "Media deleted."

    )

    return redirect(

        "event_gallery",

        event_id

    )       
    
    
    
    
    
@login_required
@user_passes_test(is_event_organizer)
def event_analytics(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    events = Event.objects.filter(
        organizer=organization
    )

    registrations = EventRegistration.objects.filter(
        event__organizer=organization
    )

    # ==========================================
    # SUMMARY
    # ==========================================

    total_events = events.count()

    total_participants = registrations.count()

    approved = registrations.filter(
        status="APPROVED"
    ).count()

    attended = registrations.filter(
        status="ATTENDED"
    ).count()

    certificates = EventCertificate.objects.filter(
        event__organizer=organization
    ).count()

    # ==========================================
    # AVERAGE RATING
    # ==========================================

    average_rating = EventFeedback.objects.filter(
        event__organizer=organization
    ).aggregate(
        avg=Avg("rating")
    )["avg"]

    # ==========================================
    # ATTENDANCE RATE
    # ==========================================

    eligible_attendees = registrations.filter(
        status__in=[
            "APPROVED",
            "ATTENDED"
        ]
    ).count()

    attendance_rate = 0

    if eligible_attendees > 0:

        attendance_rate = round(
            (attended / eligible_attendees) * 100,
            1
        )

    # ==========================================
    # TOP EVENTS
    # ==========================================

    top_events = events.annotate(
        participants=Count(
            "registrations"
        )
    ).order_by(
        "-participants"
    )[:5]

    # ==========================================
    # CONTEXT
    # ==========================================

    context = {

        "total_events": total_events,

        "total_participants": total_participants,

        "approved": approved,

        "attended": attended,

        "certificates": certificates,

        "attendance_rate": attendance_rate,

        "average_rating": average_rating,

        "top_events": top_events,

    }

    # ==========================================
    # RENDER
    # ==========================================

    return render(
        request,
        "events/event_analytics.html",
        context
    )  
    
    
@login_required
def certificate_detail(request, certificate_id):

    certificate = get_object_or_404(
        EventCertificate,
        id=certificate_id
    )

    # Only allow the certificate owner or
    # the organization that issued it to view it.

    is_owner = (
        certificate.talent.user == request.user
    )

    is_issuer = (
        certificate.issued_by.user == request.user
    )

    if not is_owner and not is_issuer:
        messages.error(
            request,
            "You are not authorized to view this certificate."
        )

        return redirect("my_certificates")

    return render(
        request,
        "events/certificate_detail.html",
        {
            "certificate": certificate
        }
    )
    
    
    
@login_required
def my_certificates(request):

    talent = TalentProfile.objects.filter(
        user=request.user
    ).first()

    if not talent:

        messages.warning(
            request,
            "You need a talent profile to view your certificates."
        )

        return redirect("dashboard")

    certificates = EventCertificate.objects.filter(
        talent=talent
    ).select_related(
        "event",
        "issued_by"
    )

    return render(
        request,
        "events/my_certificates.html",
        {
            "certificates": certificates
        }
    )   