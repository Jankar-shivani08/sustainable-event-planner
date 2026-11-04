import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from events.models import Event

from .models import EmailVerificationOTP, UserProfile, UserRole

User = get_user_model()
PASSWORD = 'StrongPass123!'


class DeleteAccountTests(TestCase):
    def _user(self, username, role):
        user = User.objects.create_user(username=username, password=PASSWORD, email=f'{username}@example.com')
        user.profile.role = role
        user.profile.save()
        return user

    def test_profile_page_links_to_delete_account(self):
        self.client.force_login(self._user('linkattendee', UserRole.ATTENDEE))

        self.assertContains(self.client.get('/accounts/profile/'), 'href="/accounts/profile/delete/"')

    def test_correct_password_deletes_account_and_logs_out(self):
        user = self._user('leavingattendee', UserRole.ATTENDEE)
        self.client.force_login(user)

        response = self.client.post('/accounts/profile/delete/', {'password': PASSWORD})

        self.assertRedirects(response, '/', target_status_code=200)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(UserProfile.objects.filter(user_id=user.pk).exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_wrong_password_keeps_account(self):
        user = self._user('stayingattendee', UserRole.ATTENDEE)
        self.client.force_login(user)

        response = self.client.post('/accounts/profile/delete/', {'password': 'wrong-password'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect password')
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_organizer_is_warned_and_their_events_are_deleted(self):
        organizer = self._user('leavingorganizer', UserRole.ORGANIZER)
        Event.objects.create(
            event_name='Organizer Event', event_type=Event.EventType.SEMINAR, venue='Hall C',
            event_date='2026-12-01', start_time='09:00:00', end_time='11:00:00', duration=2,
            expected_attendees=40, organizer=organizer,
        )
        self.client.force_login(organizer)

        self.assertContains(self.client.get('/accounts/profile/delete/'), 'Delete the 1 event you organize')
        self.client.post('/accounts/profile/delete/', {'password': PASSWORD})

        self.assertFalse(Event.objects.filter(event_name='Organizer Event').exists())

    def test_only_administrator_cannot_delete_account(self):
        admin = self._user('onlyadmin', UserRole.ADMIN)
        self.client.force_login(admin)

        response = self.client.post('/accounts/profile/delete/', {'password': PASSWORD})

        self.assertRedirects(response, '/accounts/profile/', target_status_code=200)
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_leftover_or_inactive_admins_do_not_count_as_another_admin(self):
        admin = self._user('realadmin', UserRole.ADMIN)
        inactive_admin = self._user('inactiveadmin', UserRole.ADMIN)
        inactive_admin.is_active = False
        inactive_admin.save()
        removed_admin = self._user('removedadmin', UserRole.ADMIN)
        # Simulate a user removed directly in MongoDB, which leaves its profile behind.
        connection.database[User._meta.db_table].delete_one({'_id': removed_admin.pk})
        self.client.force_login(admin)

        self.client.post('/accounts/profile/delete/', {'password': PASSWORD})

        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_administrator_can_delete_when_another_admin_exists(self):
        admin = self._user('firstadmin', UserRole.ADMIN)
        self._user('secondadmin', UserRole.ADMIN)
        self.client.force_login(admin)

        self.client.post('/accounts/profile/delete/', {'password': PASSWORD})

        self.assertFalse(User.objects.filter(pk=admin.pk).exists())

    def test_login_required(self):
        response = self.client.get('/accounts/profile/delete/')

        self.assertRedirects(response, '/accounts/login/?next=/accounts/profile/delete/', fetch_redirect_response=False)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='resetuser', password=PASSWORD, email='reset@example.com', first_name='Reset')

    def _request_reset(self, email):
        return self.client.post('/accounts/password-reset/', {'email': email})

    def _reset_link(self):
        return re.search(r'https?://[^/]+(/accounts/password-reset/\S+/)', mail.outbox[0].body).group(1)

    def test_login_page_links_to_forgot_password(self):
        self.assertContains(self.client.get('/accounts/login/'), 'href="/accounts/password-reset/"')

    def test_registered_email_receives_reset_link(self):
        response = self._request_reset('Reset@Example.com')

        self.assertRedirects(response, '/accounts/password-reset/sent/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['reset@example.com'])
        self.assertIn('Reset Your Password', mail.outbox[0].subject)
        self.assertTrue(self._reset_link())

    def test_unknown_or_unverified_email_gets_no_email_but_same_page(self):
        self.user.is_active = False
        self.user.save()

        for email in ('reset@example.com', 'nobody@example.com'):
            self.assertRedirects(self._request_reset(email), '/accounts/password-reset/sent/')
        self.assertEqual(mail.outbox, [])

    def test_reset_link_sets_new_password_and_works_only_once(self):
        self._request_reset('reset@example.com')
        link = self._reset_link()

        # Django swaps the token in the URL for one held in the session.
        form_url = self.client.get(link).url
        response = self.client.post(form_url, {'new_password1': 'BrandNewPass456!', 'new_password2': 'BrandNewPass456!'})

        self.assertRedirects(response, '/accounts/password-reset/complete/')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertContains(self.client.get(link), 'invalid or has expired')

    def test_mismatched_new_passwords_show_error(self):
        self._request_reset('reset@example.com')
        form_url = self.client.get(self._reset_link()).url

        response = self.client.post(form_url, {'new_password1': 'BrandNewPass456!', 'new_password2': 'Different789!'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'text-danger')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


class SharedEmailTests(TestCase):
    EMAIL = 'shared@example.com'

    def _register(self, username, role, email=EMAIL):
        return self.client.post('/accounts/register/', {
            'username': username, 'first_name': 'Shared', 'last_name': 'Person', 'email': email,
            'phone': '9876543210', 'role': role, 'password1': PASSWORD, 'password2': PASSWORD,
        })

    def _latest_otp(self):
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)

    def test_same_email_can_register_one_account_per_role(self):
        for username, role in (('sharedadmin', UserRole.ADMIN), ('sharedorganizer', UserRole.ORGANIZER), ('sharedattendee', UserRole.ATTENDEE)):
            self.assertRedirects(self._register(username, role), '/accounts/verify-email/', target_status_code=200)

        accounts = User.objects.filter(email=self.EMAIL)
        self.assertEqual(accounts.count(), 3)
        self.assertEqual(set(accounts.values_list('profile__role', flat=True)), {UserRole.ADMIN, UserRole.ORGANIZER, UserRole.ATTENDEE})

    def test_same_email_and_same_role_is_rejected(self):
        self._register('firstorganizer', UserRole.ORGANIZER)

        response = self._register('secondorganizer', UserRole.ORGANIZER, email='Shared@Example.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already has an account with the Organizer role')
        self.assertFalse(User.objects.filter(username='secondorganizer').exists())

    def test_otp_activates_the_account_it_was_sent_for(self):
        self._register('verifiedattendee', UserRole.ATTENDEE)
        self.client.post('/accounts/verify-email/', {'email': self.EMAIL, 'otp': self._latest_otp()})
        self._register('neworganizer', UserRole.ORGANIZER)

        self.client.post('/accounts/verify-email/', {'email': self.EMAIL, 'otp': self._latest_otp()})

        organizer = User.objects.get(username='neworganizer')
        self.assertTrue(organizer.is_active)
        self.assertTrue(organizer.profile.email_verified)
        self.assertTrue(User.objects.get(username='verifiedattendee').is_active)

    def test_second_unverified_account_is_not_activated_by_another_accounts_otp(self):
        self._register('pendingattendee', UserRole.ATTENDEE)
        self._register('pendingorganizer', UserRole.ORGANIZER)

        self.client.post('/accounts/verify-email/', {'email': self.EMAIL, 'otp': self._latest_otp()})

        self.assertTrue(User.objects.get(username='pendingorganizer').is_active)
        self.assertFalse(User.objects.get(username='pendingattendee').is_active)

    def test_resend_targets_the_unverified_account(self):
        self._register('doneattendee', UserRole.ATTENDEE)
        self.client.post('/accounts/verify-email/', {'email': self.EMAIL, 'otp': self._latest_otp()})
        self._register('waitingorganizer', UserRole.ORGANIZER)
        EmailVerificationOTP.objects.update(created_at=timezone.now() - timedelta(minutes=2))

        self.client.post('/accounts/verify-email/resend/', {'email': self.EMAIL})
        self.client.post('/accounts/verify-email/', {'email': self.EMAIL, 'otp': self._latest_otp()})

        self.assertEqual(EmailVerificationOTP.objects.get().user.username, 'waitingorganizer')
        self.assertTrue(User.objects.get(username='waitingorganizer').is_active)

    def test_password_reset_sends_one_link_per_account(self):
        for username, role in (('resetorganizer', UserRole.ORGANIZER), ('resetattendee', UserRole.ATTENDEE)):
            user = User.objects.create_user(username=username, password=PASSWORD, email=self.EMAIL)
            user.profile.role = role
            user.profile.save()

        self.client.post('/accounts/password-reset/', {'email': self.EMAIL})

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({'resetorganizer', 'resetattendee'}, {name for message in mail.outbox for name in ('resetorganizer', 'resetattendee') if name in message.body})

    def test_profile_cannot_switch_to_a_role_the_email_already_has(self):
        organizer = User.objects.create_user(username='profileorganizer', password=PASSWORD, email=self.EMAIL)
        organizer.profile.role = UserRole.ORGANIZER
        organizer.profile.save()
        attendee = User.objects.create_user(username='profileattendee', password=PASSWORD, email=self.EMAIL)
        attendee.profile.role = UserRole.ATTENDEE
        attendee.profile.save()
        self.client.force_login(attendee)

        response = self.client.post('/accounts/profile/', {'role': UserRole.ORGANIZER, 'phone': '', 'organization': '', 'bio': ''})

        self.assertContains(response, 'already has another account with the Organizer role')
        attendee.profile.refresh_from_db()
        self.assertEqual(attendee.profile.role, UserRole.ATTENDEE)
