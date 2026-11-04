import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import UserRole
from events.models import Attendance, Event

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AttendeeDashboardTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.organizer = User.objects.create_user(username='attendeeorganizer', password='StrongPass123!')
        self.organizer.profile.role = UserRole.ORGANIZER
        self.organizer.profile.save()
        self.attendee = User.objects.create_user(
            username='attendeeuser', password='StrongPass123!', email='guest@example.com',
            first_name='Guest', last_name='User',
        )
        self.attendee.profile.role = UserRole.ATTENDEE
        self.attendee.profile.phone = '9876543210'
        self.attendee.profile.save()

        today = timezone.localdate()
        self.open_event = self._event('Open Summit', today + timedelta(days=5), Event.Status.SCHEDULED)
        self.draft_event = self._event('Draft Meetup', today + timedelta(days=5), Event.Status.DRAFT)
        self.past_event = self._event('Past Expo', today - timedelta(days=5), Event.Status.COMPLETED)

    def _event(self, name, event_date, status):
        return Event.objects.create(
            event_name=name, event_type=Event.EventType.CONFERENCE, venue='Hall A',
            event_date=event_date, start_time='09:00:00', end_time='12:00:00', duration=3,
            expected_attendees=50, organizer=self.organizer, status=status,
        )

    def test_attendee_is_redirected_to_attendee_dashboard(self):
        self.client.force_login(self.attendee)

        self.assertRedirects(self.client.get('/accounts/dashboard/'), '/attendee/dashboard/', target_status_code=200)
        self.assertRedirects(self.client.get('/accounts/dashboard/attendee/'), '/attendee/dashboard/', target_status_code=200)

    def test_dashboard_lists_open_events_and_own_registrations_with_check_in_status(self):
        Attendance.objects.create(
            event=self.past_event, attendee_name='Guest User', email='Guest@Example.com',
            is_present=True, check_in_time=timezone.now(),
        )
        Attendance.objects.create(event=self.open_event, attendee_name='Someone Else', email='other@example.com')
        self.client.force_login(self.attendee)

        response = self.client.get('/attendee/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['upcoming_events'], [self.open_event])
        self.assertEqual([item.event for item in response.context['registrations']], [self.past_event])
        self.assertEqual(response.context['checked_in_count'], 1)
        self.assertContains(response, 'Checked in')

    def test_attendee_registers_once_and_receives_qr_code(self):
        self.client.force_login(self.attendee)
        url = f'/attendee/events/{self.open_event.pk}/register/'

        self.assertRedirects(self.client.post(url), '/attendee/dashboard/', target_status_code=200)
        self.client.post(url)

        registrations = Attendance.objects.filter(event=self.open_event)
        self.assertEqual(registrations.count(), 1)
        registration = registrations.get()
        self.assertEqual(registration.email, 'guest@example.com')
        self.assertEqual(registration.attendee_name, 'Guest User')
        self.assertEqual(registration.phone, '9876543210')
        self.assertTrue(registration.qr_code.name)

    def test_cannot_register_for_draft_or_past_events(self):
        self.client.force_login(self.attendee)

        for event in (self.draft_event, self.past_event):
            response = self.client.post(f'/attendee/events/{event.pk}/register/')
            self.assertEqual(response.status_code, 404)
        self.assertFalse(Attendance.objects.exists())

    def test_organizer_cannot_open_attendee_dashboard(self):
        self.client.force_login(self.organizer)

        self.assertRedirects(self.client.get('/attendee/dashboard/'), '/accounts/profile/', fetch_redirect_response=False)

    def test_event_info_shows_register_button_for_open_event(self):
        self.client.force_login(self.attendee)

        response = self.client.get(f'/attendee/events/{self.open_event.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hall A')
        self.assertContains(response, f'/attendee/events/{self.open_event.pk}/register/')

    def test_event_info_shows_own_registration_for_past_event(self):
        registration = Attendance.objects.create(event=self.past_event, attendee_name='Guest User', email='guest@example.com')
        self.client.force_login(self.attendee)

        response = self.client.get(f'/attendee/events/{self.past_event.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(registration.registration_id))
        self.assertContains(response, 'Not checked in')

    def test_event_info_hides_events_attendee_cannot_join(self):
        self.client.force_login(self.attendee)

        for event in (self.draft_event, self.past_event):
            self.assertEqual(self.client.get(f'/attendee/events/{event.pk}/').status_code, 404)

    def test_navbar_hides_organizer_links_from_attendees(self):
        events_link = 'href="/events/"'

        self.client.force_login(self.attendee)
        self.assertNotContains(self.client.get('/accounts/profile/'), events_link)

        self.client.force_login(self.organizer)
        self.assertContains(self.client.get('/accounts/profile/'), events_link)
