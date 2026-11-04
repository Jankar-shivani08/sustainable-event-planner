import hashlib
import hmac
import secrets
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import DeleteAccountForm, LoginForm, ProfileForm, RegisterForm
from .models import EmailVerificationOTP, UserProfile, UserRole
from events.models import Attendance, Event, Prediction, Recommendation, SustainabilityChecklist, WasteRecord

User = get_user_model()
OTP_MAX_ATTEMPTS = 5
OTP_TTL_MINUTES = 5
RESEND_COOLDOWN_SECONDS = 60


def _normalize_email(value):
    return (value or '').strip().lower()


def _mask_email(value):
    email = _normalize_email(value)
    if not email or '@' not in email:
        return email or 'your email'
    local_part, domain = email.split('@', 1)
    if len(local_part) <= 2:
        visible = local_part[:1]
    else:
        visible = local_part[:2]
    return f'{visible}***@{domain}'


def _generate_otp():
    return str(secrets.randbelow(10 ** 6)).zfill(6)


def _hash_otp(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _issue_verification_otp(user, email):
    normalized_email = _normalize_email(email)
    EmailVerificationOTP.objects.filter(
        email__iexact=normalized_email,
        purpose=EmailVerificationOTP.Purpose.EMAIL_VERIFICATION,
    ).delete()

    otp_code = _generate_otp()
    otp_record = EmailVerificationOTP.objects.create(
        user=user,
        email=normalized_email,
        otp_hash=_hash_otp(otp_code),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
        verified=False,
        purpose=EmailVerificationOTP.Purpose.EMAIL_VERIFICATION,
    )

    user_name = user.get_full_name() or user.username
    subject = 'Verify Your Email - Sustainable Event Planning & Waste Prediction System'
    text_body = render_to_string('accounts/email/verify_email.txt', {
        'user_name': user_name,
        'otp_code': otp_code,
    })
    html_body = render_to_string('accounts/email/verify_email.html', {
        'user_name': user_name,
        'otp_code': otp_code,
    })
    email_message = EmailMultiAlternatives(
        subject,
        text_body,
        None,
        [normalized_email],
    )
    email_message.attach_alternative(html_body, 'text/html')
    email_message.send(fail_silently=False)
    return otp_record


def _send_verification_email(user, otp_code):
    subject = 'Verify Your Email - Sustainable Event Planning & Waste Prediction System'
    user_name = user.get_full_name() or user.username
    text_body = render_to_string('accounts/email/verify_email.txt', {
        'user_name': user_name,
        'otp_code': otp_code,
    })
    html_body = render_to_string('accounts/email/verify_email.html', {
        'user_name': user_name,
        'otp_code': otp_code,
    })
    email_message = EmailMultiAlternatives(
        subject,
        text_body,
        None,
        [user.email],
    )
    email_message.attach_alternative(html_body, 'text/html')
    email_message.send(fail_silently=False)


def _otp_is_recently_sent(email):
    normalized_email = _normalize_email(email)
    latest_otp = EmailVerificationOTP.objects.filter(
        email__iexact=normalized_email,
        purpose=EmailVerificationOTP.Purpose.EMAIL_VERIFICATION,
    ).order_by('-created_at').first()
    if not latest_otp:
        return False
    return timezone.now() - latest_otp.created_at < timedelta(seconds=RESEND_COOLDOWN_SECONDS)


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            profile = getattr(request.user, 'profile', None)
            if profile is None or profile.role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('accounts:profile')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def _build_dashboard_context(user, include_all_events=False):
    events_query = Event.objects.all()
    if not include_all_events:
        events_query = events_query.filter(organizer=user)
    events = list(events_query.order_by('event_date', 'event_name'))
    event_ids = [event.pk for event in events]
    event_by_id = {str(event.pk): event for event in events}
    today = timezone.localdate()

    predictions_by_event = {}
    for prediction in Prediction.objects.filter(event_id__in=event_ids).order_by('-created_at'):
        predictions_by_event.setdefault(str(prediction.event_id), prediction)

    actual_by_event = {
        str(record.event_id): record
        for record in WasteRecord.objects.filter(event_id__in=event_ids)
    }

    predicted_total = Decimal('0')
    actual_total = Decimal('0')
    event_type_totals = {}
    predicted_categories = {name: Decimal('0') for name in ('Food', 'Plastic', 'Paper', 'Material')}
    actual_categories = {name: Decimal('0') for name in ('Food', 'Plastic', 'Paper', 'Material')}
    risk_counts = {'Low': 0, 'Medium': 0, 'High': 0}

    for event in events:
        key = str(event.pk)
        prediction = predictions_by_event.get(key)
        record = actual_by_event.get(key)
        event_type_totals.setdefault(event.event_type, {'predicted': Decimal('0'), 'actual': Decimal('0')})

        if prediction:
            prediction_total = Decimal(str(prediction.total_predicted_waste))
            predicted_total += prediction_total
            event_type_totals[event.event_type]['predicted'] += prediction_total
            if prediction.risk_level in risk_counts:
                risk_counts[prediction.risk_level] += 1
            predicted_categories['Food'] += Decimal(str(prediction.predicted_food_waste))
            predicted_categories['Plastic'] += Decimal(str(prediction.predicted_plastic_waste))
            predicted_categories['Paper'] += Decimal(str(prediction.predicted_paper_waste))
            predicted_categories['Material'] += Decimal(str(prediction.predicted_material_waste))

        if record:
            record_total = record.total_actual_waste
            actual_total += record_total
            event_type_totals[event.event_type]['actual'] += record_total
            actual_categories['Food'] += record.food_waste + record.leftover_food
            actual_categories['Plastic'] += record.plastic_waste
            actual_categories['Paper'] += record.paper_waste
            actual_categories['Material'] += (
                record.glass_waste + record.metal_waste + record.decoration_waste + record.other_waste
            )

    scored_events = []
    scored_event_ids = set()
    checklists = SustainabilityChecklist.objects.filter(event_id__in=event_ids).prefetch_related('items').order_by('-created_at')
    for checklist in checklists:
        event_key = str(checklist.event_id)
        items = list(checklist.items.all())
        if event_key in scored_event_ids or not items:
            continue
        scored_event_ids.add(event_key)
        event = event_by_id[event_key]
        scored_events.append({
            'event': event,
            'score': checklist.overall_score,
        })

    average_sustainability_score = (
        sum((Decimal(str(item['score'])) for item in scored_events), Decimal('0')) / len(scored_events)
        if scored_events else None
    )
    score_chart_events = sorted(scored_events, key=lambda item: item['event'].event_date)[-12:]

    month_starts = []
    current_month_index = today.year * 12 + today.month - 1
    for months_back in reversed(range(12)):
        year, month_index = divmod(current_month_index - months_back, 12)
        month_starts.append(date(year, month_index + 1, 1))
    month_keys = [month.strftime('%Y-%m') for month in month_starts]
    monthly_counts = {month_key: 0 for month_key in month_keys}
    for event in events:
        event_month = event.event_date.strftime('%Y-%m')
        if event_month in monthly_counts and event.event_date <= today:
            monthly_counts[event_month] += 1

    upcoming_statuses = (Event.Status.DRAFT, Event.Status.SCHEDULED, Event.Status.POSTPONED)
    upcoming_count = sum(
        event.event_date >= today and event.status in upcoming_statuses
        for event in events
    )
    event_types = sorted(event_type_totals)

    def chart_number(value):
        return float(value)

    charts = {
        'monthly_events': {
            'labels': [month.strftime('%b %Y') for month in month_starts],
            'values': [monthly_counts[key] for key in month_keys],
        },
        'event_type_waste': {
            'labels': event_types,
            'predicted': [chart_number(event_type_totals[name]['predicted']) for name in event_types],
            'actual': [chart_number(event_type_totals[name]['actual']) for name in event_types],
        },
        'total_waste': {
            'labels': ['Waste'],
            'predicted': [chart_number(predicted_total)],
            'actual': [chart_number(actual_total)],
        },
        'waste_categories': {
            'labels': list(predicted_categories),
            'predicted': [chart_number(predicted_categories[name]) for name in predicted_categories],
            'actual': [chart_number(actual_categories[name]) for name in actual_categories],
        },
        'sustainability_scores': {
            'labels': [item['event'].event_name for item in score_chart_events],
            'values': [item['score'] for item in score_chart_events],
        },
        'risk_distribution': {
            'labels': list(risk_counts),
            'values': list(risk_counts.values()),
        },
    }

    return {
        'total_events': len(events),
        'upcoming_events': upcoming_count,
        'completed_events': sum(event.status == Event.Status.COMPLETED for event in events),
        'total_attendees': Attendance.objects.filter(event_id__in=event_ids).count(),
        'predicted_waste': predicted_total,
        'actual_waste': actual_total,
        'average_sustainability_score': average_sustainability_score,
        'high_risk_events': risk_counts['High'],
        'charts': charts,
    }


def register_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:profile')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = _normalize_email(form.cleaned_data['email'])
            existing_user = User.objects.filter(email__iexact=email, profile__role=form.cleaned_data['role']).first()
            if existing_user is not None:
                request.session['pending_verification_email'] = email
                messages.info(
                    request,
                    'If the email is valid, a verification code has been sent or can be resent from the verification page.',
                )
                return redirect('accounts:verify_email')

            user = form.save(commit=False)
            user.email = email
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.is_active = False
            user.save()

            profile = user.profile
            profile.role = form.cleaned_data['role']
            profile.phone = form.cleaned_data['phone']
            profile.email_verified = False
            profile.save()

            _issue_verification_otp(user, email)
            request.session['pending_verification_email'] = email
            messages.success(request, 'Registration successful. Please verify your email to activate your account.')
            return redirect('accounts:verify_email')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def verify_email_view(request):
    email = _normalize_email(request.POST.get('email') or request.session.get('pending_verification_email'))
    if request.method == 'POST':
        otp_code = (request.POST.get('otp') or '').strip()
        if not email or not otp_code:
            messages.error(request, 'Please provide both the email and OTP.')
            return render(request, 'accounts/verify_email.html', {'email': email, 'masked_email': _mask_email(email)})

        otp_record = EmailVerificationOTP.objects.filter(
            email__iexact=email,
            purpose=EmailVerificationOTP.Purpose.EMAIL_VERIFICATION,
            verified=False,
        ).order_by('-created_at').first()

        if otp_record is None or timezone.now() > otp_record.expires_at:
            messages.error(request, 'This OTP is invalid or has expired. Please request a new one.')
            return render(request, 'accounts/verify_email.html', {'email': email, 'masked_email': _mask_email(email)})

        if otp_record.attempts >= OTP_MAX_ATTEMPTS:
            otp_record.verified = True
            otp_record.expires_at = timezone.now()
            otp_record.save(update_fields=['verified', 'expires_at'])
            messages.error(request, 'This OTP has reached the maximum number of failed attempts. Please request a new one.')
            return render(request, 'accounts/verify_email.html', {'email': email, 'masked_email': _mask_email(email)})

        if not hmac.compare_digest(_hash_otp(otp_code), otp_record.otp_hash):
            otp_record.attempts += 1
            otp_record.save(update_fields=['attempts'])
            remaining_attempts = OTP_MAX_ATTEMPTS - otp_record.attempts
            if remaining_attempts <= 0:
                otp_record.verified = True
                otp_record.expires_at = timezone.now()
                otp_record.save(update_fields=['verified', 'expires_at'])
                messages.error(request, 'This OTP has been invalidated after too many incorrect attempts. Please request a new one.')
            else:
                messages.error(request, f'Invalid OTP. You have {remaining_attempts} attempt(s) remaining.')
            return render(request, 'accounts/verify_email.html', {'email': email, 'masked_email': _mask_email(email)})

        otp_record.verified = True
        otp_record.save(update_fields=['verified'])

        # The same email can belong to several accounts, so activate the one this OTP was issued for.
        user = otp_record.user or User.objects.filter(email__iexact=email).first()
        if user is not None:
            user.is_active = True
            user.save(update_fields=['is_active'])
            profile = getattr(user, 'profile', None)
            if profile is not None:
                profile.email_verified = True
                profile.save(update_fields=['email_verified'])

        request.session['pending_verification_email'] = email
        messages.success(request, 'Email verified successfully. You can now log in.')
        return redirect('accounts:login')

    return render(request, 'accounts/verify_email.html', {
        'email': email,
        'masked_email': _mask_email(email),
    })


def resend_otp_view(request):
    email = _normalize_email(request.POST.get('email') or request.session.get('pending_verification_email'))
    if not email:
        messages.error(request, 'No pending email verification was found.')
        return redirect('accounts:login')

    user = User.objects.filter(email__iexact=email, profile__email_verified=False).order_by('-date_joined').first()
    if user is None:
        messages.info(request, 'If your email is registered, a new verification code is on the way.')
        return redirect('accounts:login')

    if _otp_is_recently_sent(email):
        messages.warning(request, 'Please wait 60 seconds before requesting a new OTP.')
        request.session['pending_verification_email'] = email
        return redirect('accounts:verify_email')

    _issue_verification_otp(user, email)
    request.session['pending_verification_email'] = email
    messages.success(request, 'A new OTP has been sent to your registered email.')
    return redirect('accounts:verify_email')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            identifier = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
            if user is None:
                messages.error(request, 'Invalid username or password.')
            elif not user.is_active or not getattr(user.profile, 'email_verified', False):
                request.session['pending_verification_email'] = user.email
                messages.error(request, 'Please verify your email before logging in.')
                return redirect('accounts:verify_email')
            else:
                auth_user = authenticate(request, username=user.username, password=password)
                if auth_user is not None:
                    login(request, auth_user)
                    messages.success(request, 'You have successfully logged in.')
                    return redirect('accounts:dashboard')
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please enter a valid username/email and password.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'accounts/profile.html', {
        'form': form,
        'profile': profile,
        'role_display': profile.get_role_display(),
    })


@login_required
@role_required(UserRole.ADMIN)
def admin_dashboard(request):
    recommendations = Recommendation.objects.select_related('event').all()[:6]
    return render(request, 'accounts/dashboard_admin.html', {
        'user': request.user,
        'recommendations': recommendations,
        'dashboard': _build_dashboard_context(request.user, include_all_events=True),
    })


@login_required
@role_required(UserRole.ORGANIZER)
def organizer_dashboard(request):
    recommendations = Recommendation.objects.select_related('event').filter(event__organizer=request.user)[:6]
    return render(request, 'accounts/dashboard_organizer.html', {
        'user': request.user,
        'recommendations': recommendations,
        'dashboard': _build_dashboard_context(request.user),
    })


@login_required
@role_required(UserRole.ATTENDEE)
def attendee_dashboard(request):
    return redirect('attendee:dashboard')


@login_required
def dashboard_redirect(request):
    role = request.user.profile.role
    if role == UserRole.ADMIN:
        return redirect('accounts:admin_dashboard')
    if role == UserRole.ORGANIZER:
        return redirect('accounts:organizer_dashboard')
    return redirect('attendee:dashboard')


def _is_last_administrator(user):
    # Count real, active accounts only, so leftover profiles of removed users don't qualify.
    other_users = User.objects.filter(is_active=True).exclude(pk=user.pk)
    if user.is_superuser and not other_users.filter(is_superuser=True).exists():
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.is_admin) and not other_users.filter(profile__role=UserRole.ADMIN).exists()


@login_required
def delete_account_view(request):
    user = request.user
    if _is_last_administrator(user):
        messages.error(request, 'You are the only administrator. Make another user an administrator before deleting this account.')
        return redirect('accounts:profile')

    if request.method == 'POST':
        form = DeleteAccountForm(user, request.POST)
        if form.is_valid():
            logout(request)
            # Cascades to the profile, OTP records and any events this user organizes.
            user.delete()
            messages.success(request, 'Your account has been permanently deleted.')
            return redirect('home')
    else:
        form = DeleteAccountForm(user)

    return render(request, 'accounts/delete_account.html', {
        'form': form,
        'organized_events_count': user.organized_events.count(),
    })
