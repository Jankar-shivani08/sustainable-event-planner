from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.views import role_required
from events.models import Attendance, Event
from events.services import create_attendance_qr

OPEN_STATUSES = (Event.Status.SCHEDULED, Event.Status.ONGOING)


def _upcoming_events():
    return Event.objects.filter(
        event_date__gte=timezone.localdate(),
        status__in=OPEN_STATUSES,
    ).select_related('organizer').order_by('event_date', 'start_time')


@login_required
@role_required(UserRole.ATTENDEE)
def dashboard(request):
    # Attendance records are linked to attendees by email, so this also picks up
    # registrations an organizer added for this user.
    registrations = list(
        Attendance.objects.filter(email__iexact=request.user.email).select_related('event')
    )
    registrations.sort(key=lambda item: (item.event.event_date, item.event.start_time))

    return render(request, 'accounts/dashboard_attendee.html', {
        'upcoming_events': list(_upcoming_events()),
        'registrations': registrations,
        'registered_event_ids': {item.event_id for item in registrations},
        'checked_in_count': sum(item.is_present for item in registrations),
    })


@login_required
@role_required(UserRole.ATTENDEE)
def event_info(request, pk):
    event = get_object_or_404(Event.objects.select_related('organizer'), pk=pk)
    registration = Attendance.objects.filter(event=event, email__iexact=request.user.email).first()
    is_open = _upcoming_events().filter(pk=event.pk).exists()
    # Attendees only see events they can register for or are already registered for.
    if registration is None and not is_open:
        raise Http404('Event not found.')

    return render(request, 'attendee/event_info.html', {
        'event': event,
        'registration': registration,
        'is_open': is_open,
    })


@login_required
@role_required(UserRole.ATTENDEE)
@require_POST
def register_for_event(request, pk):
    event = get_object_or_404(_upcoming_events(), pk=pk)
    user = request.user

    if Attendance.objects.filter(event=event, email__iexact=user.email).exists():
        messages.info(request, f'You are already registered for {event.event_name}.')
        return redirect('attendee:dashboard')

    attendance = Attendance.objects.create(
        event=event,
        attendee_name=user.get_full_name() or user.username,
        email=user.email,
        phone=user.profile.phone,
    )
    create_attendance_qr(attendance)
    attendance.save(update_fields=['qr_code'])
    messages.success(request, f'You are registered for {event.event_name}. Your QR code is ready under My Registered Events.')
    return redirect('attendee:dashboard')
