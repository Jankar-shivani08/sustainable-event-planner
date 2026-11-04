from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    ORGANIZER = 'ORGANIZER', 'Organizer'
    ATTENDEE = 'ATTENDEE', 'Attendee'


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.ATTENDEE,
    )
    phone = models.CharField(max_length=20, blank=True, default='')
    organization = models.CharField(max_length=150, blank=True, default='')
    bio = models.TextField(blank=True, default='')
    email_verified = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.role})'

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_organizer(self):
        return self.role == UserRole.ORGANIZER

    @property
    def is_attendee(self):
        return self.role == UserRole.ATTENDEE


class EmailVerificationOTP(models.Model):
    class Purpose(models.TextChoices):
        EMAIL_VERIFICATION = 'EMAIL_VERIFICATION', 'Email verification'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='verification_otps',
        null=True,
        blank=True,
    )
    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified = models.BooleanField(default=False)
    purpose = models.CharField(
        max_length=30,
        choices=Purpose.choices,
        default=Purpose.EMAIL_VERIFICATION,
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} ({self.purpose})'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance, email_verified=False)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
