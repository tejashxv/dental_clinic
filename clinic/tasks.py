from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def send_appointment_email(self, data):
    # Prepare WhatsApp phone number (digits only) for the template quick action
    raw_phone = data.get('phone', '')
    data['whatsapp_phone'] = ''.join(c for c in raw_phone if c.isdigit())

    # Plain text fallback body
    body = f"""Hello Doctor,
A new appointment has been requested through the website.

Patient Details:
- Name: {data['name']}
- Phone: {data['phone']}
- Email: {data['email']}
- Date: {data['date']}
- Time Slot: {data['time']}
- Message: {data.get('message') or 'No message provided'}

Please review and confirm with the patient."""

    # Render interactive HTML email
    html_message = render_to_string('emails/appointment_notification.html', {'data': data})

    return send_mail(
        '🚨 New Appointment Booking - Vaishnavi Dental Clinic',
        body,
        settings.DEFAULT_FROM_EMAIL,
        [settings.DOCTOR_EMAIL],
        fail_silently=False,
        html_message=html_message,
    )
