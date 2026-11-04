import io

import qrcode
from django.core.files.base import ContentFile
from django.utils import timezone


def create_attendance_qr(attendance):
    payload = str(attendance.registration_id)
    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    attendance.qr_code.save(
        f'{attendance.registration_id}.png',
        ContentFile(buffer.getvalue()),
        save=False,
    )


def check_in_attendee(attendance):
    if not attendance.is_present:
        attendance.is_present = True
        attendance.check_in_time = timezone.now()
        attendance.save(update_fields=['is_present', 'check_in_time'])
    return attendance