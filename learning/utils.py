from .models import Certificate
import uuid
import io
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from io import BytesIO




def generate_certificate(enrollment):

    # -----------------------------------------------------
    # SAFETY CHECK
    # -----------------------------------------------------

    if not enrollment:
        return None

    # -----------------------------------------------------
    # CREATE OR GET CERTIFICATE
    # -----------------------------------------------------

    certificate, created = Certificate.objects.get_or_create(
        enrollment=enrollment,
        defaults={
            "certificate_id": (
                f"AWL-{uuid.uuid4().hex[:12].upper()}"
            )
        }
    )

    # -----------------------------------------------------
    # PDF ALREADY EXISTS
    # -----------------------------------------------------

    if certificate.pdf:
        return certificate

    # -----------------------------------------------------
    # CREATE PDF IN MEMORY
    # -----------------------------------------------------

    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    # -----------------------------------------------------
    # BORDER
    # -----------------------------------------------------

    pdf.setLineWidth(2)

    pdf.rect(
        40,
        40,
        width - 80,
        height - 80
    )

    # -----------------------------------------------------
    # AWINLINK
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        16
    )

    pdf.drawCentredString(
        width / 2,
        height - 80,
        "AWINLINK"
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        28
    )

    pdf.drawCentredString(
        width / 2,
        height - 130,
        "CERTIFICATE OF COMPLETION"
    )

    # -----------------------------------------------------
    # PRESENTED TO
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        15
    )

    pdf.drawCentredString(
        width / 2,
        height - 200,
        "This certificate is proudly presented to"
    )

    # -----------------------------------------------------
    # LEARNER
    # -----------------------------------------------------

    user = enrollment.user

    learner_name = (
        user.get_full_name()
        or user.username
    )

    pdf.setFont(
        "Helvetica-Bold",
        24
    )

    pdf.drawCentredString(
        width / 2,
        height - 250,
        learner_name
    )

    # -----------------------------------------------------
    # COURSE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        15
    )

    pdf.drawCentredString(
        width / 2,
        height - 310,
        "for successfully completing"
    )

    pdf.setFont(
        "Helvetica-Bold",
        20
    )

    course_title = enrollment.course.title

    pdf.drawCentredString(
        width / 2,
        height - 355,
        course_title
    )

    # -----------------------------------------------------
    # ISSUE DATE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        11
    )

    pdf.drawCentredString(
        width / 2,
        110,
        f"Issued: {certificate.issued_at.strftime('%B %d, %Y')}"
    )

    # -----------------------------------------------------
    # CERTIFICATE ID
    # -----------------------------------------------------

    pdf.drawCentredString(
        width / 2,
        85,
        f"Certificate ID: {certificate.certificate_id}"
    )

    # -----------------------------------------------------
    # FINISH PDF
    # -----------------------------------------------------

    pdf.save()

    buffer.seek(0)

    # -----------------------------------------------------
    # SAVE PDF
    # -----------------------------------------------------

    filename = (
        f"{certificate.certificate_id}.pdf"
    )

    certificate.pdf.save(
        filename,
        ContentFile(buffer.read()),
        save=True
    )

    return certificate



# =========================================================
# GENERATE CERTIFICATE PDF
# =========================================================

def generate_certificate_pdf(certificate):

    enrollment = certificate.enrollment
    course = enrollment.course
    user = enrollment.user

    # -----------------------------------------------------
    # LEARNER NAME
    # -----------------------------------------------------

    learner_name = user.get_full_name()

    if not learner_name:
        learner_name = user.username

    # -----------------------------------------------------
    # COURSE NAME
    # -----------------------------------------------------

    course_name = course.title

    # -----------------------------------------------------
    # ISSUE DATE
    # -----------------------------------------------------

    issue_date = timezone.localtime(
        certificate.issued_at
    ).strftime("%B %d, %Y")

    # -----------------------------------------------------
    # CREATE PDF IN MEMORY
    # -----------------------------------------------------

    buffer = io.BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=landscape(A4)
    )

    width, height = landscape(A4)

    # -----------------------------------------------------
    # BORDER
    # -----------------------------------------------------

    pdf.setLineWidth(3)

    pdf.rect(
        15 * mm,
        15 * mm,
        width - (30 * mm),
        height - (30 * mm)
    )

    pdf.setLineWidth(1)

    pdf.rect(
        20 * mm,
        20 * mm,
        width - (40 * mm),
        height - (40 * mm)
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        30
    )

    pdf.drawCentredString(
        width / 2,
        height - 55 * mm,
        "CERTIFICATE OF COMPLETION"
    )

    # -----------------------------------------------------
    # PRESENTATION TEXT
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        14
    )

    pdf.drawCentredString(
        width / 2,
        height - 75 * mm,
        "This certificate is proudly presented to"
    )

    # -----------------------------------------------------
    # LEARNER NAME
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        26
    )

    pdf.drawCentredString(
        width / 2,
        height - 95 * mm,
        learner_name
    )

    # -----------------------------------------------------
    # COMPLETION TEXT
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        14
    )

    pdf.drawCentredString(
        width / 2,
        height - 115 * mm,
        "for successfully completing the course"
    )

    # -----------------------------------------------------
    # COURSE NAME
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        20
    )

    pdf.drawCentredString(
        width / 2,
        height - 132 * mm,
        course_name
    )

    # -----------------------------------------------------
    # CERTIFICATE ID
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        30 * mm,
        30 * mm,
        f"Certificate ID: {certificate.certificate_id}"
    )

    # -----------------------------------------------------
    # ISSUE DATE
    # -----------------------------------------------------

    pdf.drawRightString(
        width - 30 * mm,
        30 * mm,
        f"Issued: {issue_date}"
    )

    # -----------------------------------------------------
    # FINISH PDF
    # -----------------------------------------------------

    pdf.showPage()

    pdf.save()

    # -----------------------------------------------------
    # GET PDF CONTENT
    # -----------------------------------------------------

    pdf_data = buffer.getvalue()

    buffer.close()

    # -----------------------------------------------------
    # SAVE PDF TO CERTIFICATE MODEL
    # -----------------------------------------------------

    filename = (
        f"certificate-{certificate.certificate_id}.pdf"
    )

    certificate.pdf.save(
        filename,
        ContentFile(pdf_data),
        save=True
    )

    return certificate