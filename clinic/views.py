import json
import socket
from base64 import b64encode
from urllib import parse, request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .tasks import send_appointment_email


def home(request):
    return render(request, 'home.html')


@require_POST
def book_appointment(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid appointment payload.'}, status=400)

    data = {
        'name': payload.get('name', '').strip(),
        'phone': payload.get('phone', '').strip(),
        'email': payload.get('email', '').strip(),
        'date': payload.get('date', '').strip(),
        'time': payload.get('time', '').strip(),
        'message': payload.get('message', '').strip(),
    }
    missing = [label for label, value in data.items() if label != 'message' and not value]
    if missing:
        return JsonResponse({'ok': False, 'error': 'Please complete all required fields.'}, status=400)

    email_queued = _queue_doctor_email(data)
    whatsapp_message = _build_whatsapp_message(data)
    whatsapp_sent = _send_twilio_whatsapp(whatsapp_message)
    whatsapp_url = _build_whatsapp_url(whatsapp_message)

    return JsonResponse({
        'ok': True,
        'email_queued': email_queued,
        'whatsapp_sent': whatsapp_sent,
        'whatsapp_url': whatsapp_url,
    })


def _queue_doctor_email(data):
    if not settings.CELERY_TASK_ALWAYS_EAGER and not _celery_broker_available():
        return False

    try:
        send_appointment_email.delay(data)
        return True
    except Exception:
        return False


def _celery_broker_available():
    broker_url = urlparse(settings.CELERY_BROKER_URL)
    if broker_url.scheme in {'memory', 'filesystem'}:
        return True
    if not broker_url.hostname:
        return False

    default_ports = {
        'redis': 6379,
        'rediss': 6379,
        'amqp': 5672,
        'amqps': 5671,
    }
    port = broker_url.port or default_ports.get(broker_url.scheme)
    if not port:
        return True

    try:
        with socket.create_connection((broker_url.hostname, port), timeout=0.75):
            return True
    except OSError:
        return False


def _build_whatsapp_message(data):
    return (
        '*Vaishnavi Dental Clinic - New Appointment Request*\n'
        f"\u2022 *Patient:* {data['name']}\n"
        f"\u2022 *Phone:* {data['phone']}\n"
        f"\u2022 *Date:* {data['date']}\n"
        f"\u2022 *Time:* {data['time']}"
    )


def _send_twilio_whatsapp(message):
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_FROM]):
        return False

    doctor_number = _doctor_whatsapp_number()
    sender_number = settings.TWILIO_WHATSAPP_FROM.removeprefix('whatsapp:').strip()
    form_data = parse.urlencode({
        'From': f'whatsapp:{sender_number}',
        'To': f'whatsapp:+{doctor_number}',
        'Body': message,
    }).encode('utf-8')
    api_url = f'https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json'
    api_request = urlrequest.Request(api_url, data=form_data, method='POST')
    credentials = f'{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}'.encode('utf-8')
    api_request.add_header('Authorization', f'Basic {b64encode(credentials).decode("ascii")}')
    api_request.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urlrequest.urlopen(api_request, timeout=8) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError):
        return False


def _build_whatsapp_url(message):
    encoded_message = parse.quote(message)
    return f'https://api.whatsapp.com/send?phone={_doctor_whatsapp_number()}&text={encoded_message}'


def _doctor_whatsapp_number():
    return ''.join(character for character in settings.DOCTOR_WHATSAPP if character.isdigit())

# Create your views here.
