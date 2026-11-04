from django.urls import path

from . import views

app_name = 'attendee'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('events/<str:pk>/', views.event_info, name='event_info'),
    path('events/<str:pk>/register/', views.register_for_event, name='register_event'),
]
