from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm

from .models import UserProfile, UserRole

User = get_user_model()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    phone = forms.CharField(max_length=20, required=True)
    role = forms.ChoiceField(
        choices=(
            (UserRole.ADMIN, UserRole.ADMIN.label),
            (UserRole.ORGANIZER, UserRole.ORGANIZER.label),
            (UserRole.ATTENDEE, UserRole.ATTENDEE.label),
        ),
        initial=UserRole.ORGANIZER,
    )

    class Meta:
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'phone',
            'role',
            'password1',
            'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_classes = {
            'username': 'form-control',
            'first_name': 'form-control',
            'last_name': 'form-control',
            'email': 'form-control',
            'phone': 'form-control',
            'role': 'form-select',
            'password1': 'form-control',
            'password2': 'form-control',
        }
        for field_name, css_class in field_classes.items():
            field = self.fields.get(field_name)
            if field is not None:
                field.widget.attrs.setdefault('class', css_class)
                field.widget.attrs.setdefault('placeholder', {
                    'username': 'Enter username',
                    'first_name': 'First name',
                    'last_name': 'Last name',
                    'email': 'name@example.com',
                    'phone': '+1 555 123 4567',
                    'password1': 'Enter password',
                    'password2': 'Confirm password',
                }.get(field_name, ''))

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        role = cleaned_data.get('role')
        # One email may hold one account per role, e.g. an Organizer and an Attendee account.
        if email and role and User.objects.filter(email__iexact=email, profile__role=role).exists():
            self.add_error('email', f'This email already has an account with the {UserRole(role).label} role. Use a different email or choose another role.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = False

        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data['role']
            profile.phone = self.cleaned_data['phone']
            profile.email_verified = False
            profile.save()

        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('role', 'phone', 'organization', 'bio')
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}),
            'organization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Example: EventPro'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell us a little about yourself'}),
        }

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if not role:
            raise forms.ValidationError('Please select a valid role.')
        user = self.instance.user
        if User.objects.filter(email__iexact=user.email, profile__role=role).exclude(pk=user.pk).exists():
            raise forms.ValidationError(f'Your email already has another account with the {UserRole(role).label} role.')
        return role


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label='Confirm your password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.user.check_password(password):
            raise forms.ValidationError('Incorrect password. Your account was not deleted.')
        return password


class PasswordResetRequestForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].label = 'Registered Email'
        self.fields['email'].widget.attrs.update({'class': 'form-control', 'placeholder': 'name@example.com'})


class NewPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, placeholder in (('new_password1', 'Enter new password'), ('new_password2', 'Confirm new password')):
            self.fields[field_name].widget.attrs.update({'class': 'form-control', 'placeholder': placeholder})
