from django.urls import path

from . import views

app_name = 'events'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('create/', views.event_create, name='event_create'),
    path('historical-dataset/', views.historical_dataset, name='historical_dataset'),
    path('historical-dataset/upload/', views.historical_dataset_upload, name='historical_dataset_upload'),
    path('historical-dataset/<str:pk>/delete/', views.historical_record_delete, name='historical_record_delete'),
    path('ml-predictions/', views.ml_predictions, name='ml_predictions'),
    path('waste-prediction/', views.waste_prediction, name='waste_prediction'),
    path('waste-analysis/', views.waste_analysis, name='waste_analysis'),
    path('recommendations/report/', views.recommendation_report, name='recommendation_report'),
    path('<str:pk>/', views.event_detail, name='event_detail'),
    path('<str:pk>/attendance/', views.attendance_list, name='attendance_list'),
    path('<str:pk>/attendance/add/', views.attendance_create, name='attendance_create'),
    path('<str:pk>/waste-record/', views.waste_record, name='waste_record'),
    path('<str:pk>/update/', views.event_update, name='event_update'),
    path('<str:pk>/delete/', views.event_delete, name='event_delete'),
    path('<str:pk>/resources/', views.resource_plan_detail, name='resource_plan_detail'),
    path('<str:pk>/resources/create/', views.resource_plan_create, name='resource_plan_create'),
    path('<str:pk>/resources/update/', views.resource_plan_update, name='resource_plan_update'),
    path('<str:pk>/resources/delete/', views.resource_plan_delete, name='resource_plan_delete'),
    path('<str:pk>/vendors/', views.vendor_list, name='vendor_list'),
    path('<str:pk>/vendors/create/', views.vendor_create, name='vendor_create'),
    path('vendors/<str:pk>/', views.vendor_detail, name='vendor_detail'),
    path('vendors/<str:pk>/update/', views.vendor_update, name='vendor_update'),
    path('vendors/<str:pk>/delete/', views.vendor_delete, name='vendor_delete'),
    path('vendors/<str:pk>/checklist/create/', views.vendor_checklist_create, name='vendor_checklist_create'),
    path('vendors/<str:pk>/checklist/update/', views.vendor_checklist_update, name='vendor_checklist_update'),
    path('attendance/<str:pk>/', views.attendance_detail, name='attendance_detail'),
    path('attendance/<str:pk>/check-in/', views.attendance_check_in, name='attendance_check_in'),
    path('<str:pk>/sustainability/', views.sustainability_dashboard, name='sustainability_dashboard'),
    path('<str:pk>/sustainability/create/', views.sustainability_checklist_create, name='sustainability_checklist_create'),
    path('<str:pk>/sustainability/<str:checklist_id>/', views.sustainability_checklist_form, name='sustainability_checklist_form'),
]
