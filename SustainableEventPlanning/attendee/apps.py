from django.apps import AppConfig


class AttendeeConfig(AppConfig):
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'
    name = 'attendee'
