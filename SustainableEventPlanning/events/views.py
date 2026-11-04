from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from decimal import Decimal
import pandas as pd

from .dataset import REQUIRED_COLUMNS, process_historical_csv
from .forms import AttendanceForm, EventForm, HistoricalDatasetUploadForm, MLPredictionForm, ResourcePlanForm, VendorChecklistForm, VendorForm, SustainabilityChecklistForm, ChecklistItemForm, WastePredictionForm, WasteRecordForm
from .models import Attendance, Event, HistoricalEventRecord, Prediction, Recommendation, ResourcePlan, RiskThresholdConfig, Vendor, VendorChecklist, SustainabilityChecklist, ChecklistItem, WasteRecord
from .recommendations import generate_recommendations
from .services import check_in_attendee, create_attendance_qr
from .ml.prediction import model_version_summary, predict_all, waste_risk_level


def can_manage_event(user, event):
    profile = getattr(user, 'profile', None)
    if user.is_superuser:
        return True
    if profile and profile.is_admin:
        return True
    return user == event.organizer


@login_required
def event_list(request):
    profile = getattr(request.user, 'profile', None)

    if profile and profile.is_admin:
        events = Event.objects.all()
    else:
        events = Event.objects.filter(organizer=request.user)

    query = request.GET.get('q', '').strip()
    event_type = request.GET.get('event_type', '')
    status = request.GET.get('status', '')

    if query:
        events = events.filter(
            Q(event_name__icontains=query)
            | Q(venue__icontains=query)
            | Q(organizer__username__icontains=query)
        )

    if event_type:
        events = events.filter(event_type=event_type)

    if status:
        events = events.filter(status=status)

    events = events.order_by('-event_date', '-created_at')

    paginator = Paginator(events, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'events/event_list.html', {
        'page_obj': page_obj,
        'query': query,
        'event_type': event_type,
        'status': status,
        'event_type_choices': Event.EventType.choices,
        'status_choices': Event.Status.choices,
    })


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to view this event.')
        return redirect('events:event_list')
    plan = getattr(event, 'resource_plan', None)
    attendees = event.attendees.all()
    recommendations = event.recommendations.select_related('prediction')[:6]
    waste_record = getattr(event, 'waste_record', None)
    return render(request, 'events/event_detail.html', {'event': event, 'plan': plan, 'attendees': attendees, 'recommendations': recommendations, 'waste_record': waste_record})


@login_required
def waste_record(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to record waste for this event.')
        return redirect('events:event_list')
    if event.status != Event.Status.COMPLETED:
        messages.error(request, 'Post-event waste can only be recorded for completed events.')
        return redirect('events:event_detail', pk=event.pk)

    record = getattr(event, 'waste_record', None)
    if request.method == 'POST':
        form = WasteRecordForm(request.POST, instance=record)
        if form.is_valid():
            saved_record = form.save(commit=False)
            saved_record.event = event
            saved_record.save()
            messages.success(request, 'Post-event waste record saved.')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = WasteRecordForm(instance=record)

    return render(request, 'events/waste_record_form.html', {
        'event': event,
        'form': form,
        'title': 'Record Post-Event Waste' if record is None else 'Update Post-Event Waste',
    })


@login_required
def attendance_list(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to view attendance for this event.')
        return redirect('events:event_list')
    return render(request, 'events/attendance_list.html', {'event': event, 'attendees': event.attendees.all()})


@login_required
def attendance_create(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to register attendees for this event.')
        return redirect('events:event_list')
    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            attendee = form.save(commit=False)
            attendee.event = event
            attendee.save()
            create_attendance_qr(attendee)
            attendee.save(update_fields=['qr_code'])
            messages.success(request, 'Attendee registered and QR code generated.')
            return redirect('events:attendance_detail', pk=attendee.pk)
    else:
        form = AttendanceForm()
    return render(request, 'events/attendance_form.html', {'event': event, 'form': form, 'title': 'Add Attendee'})


@login_required
def attendance_detail(request, pk):
    attendee = get_object_or_404(Attendance, pk=pk)
    if not can_manage_event(request.user, attendee.event):
        messages.error(request, 'You do not have permission to view this attendance record.')
        return redirect('events:event_list')
    return render(request, 'events/attendance_detail.html', {'event': attendee.event, 'attendee': attendee})


@login_required
def attendance_check_in(request, pk):
    attendee = get_object_or_404(Attendance, pk=pk)
    if not can_manage_event(request.user, attendee.event):
        messages.error(request, 'You do not have permission to record attendance.')
        return redirect('events:event_list')
    if request.method == 'POST':
        check_in_attendee(attendee)
        messages.success(request, f'{attendee.attendee_name} checked in successfully.')
    return redirect('events:attendance_detail', pk=attendee.pk)


@login_required
def event_create(request):
    profile = getattr(request.user, 'profile', None)
    if profile and not (profile.is_admin or profile.is_organizer):
        messages.error(request, 'Only organizers and admins can create events.')
        return redirect('events:event_list')

    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            messages.success(request, 'Event created successfully.')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = EventForm()

    return render(request, 'events/event_form.html', {'form': form, 'title': 'Create Event'})


@login_required
def event_update(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to update this event.')
        return redirect('events:event_list')

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully.')
            return redirect('events:event_detail', pk=event.pk)
    else:
        form = EventForm(instance=event)

    return render(request, 'events/event_form.html', {'form': form, 'event': event, 'title': 'Update Event'})


@login_required
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to delete this event.')
        return redirect('events:event_list')

    if request.method == 'POST':
        event.delete()
        messages.success(request, 'Event deleted successfully.')
        return redirect('events:event_list')

    return render(request, 'events/event_confirm_delete.html', {'event': event})


@login_required
def resource_plan_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to view this resource plan.')
        return redirect('events:event_list')

    plan = getattr(event, 'resource_plan', None)
    if not plan:
        return redirect('events:resource_plan_create', pk=event.pk)

    return render(request, 'events/resource_plan_detail.html', {'event': event, 'plan': plan})


@login_required
def vendor_list(request, pk=None):
    if pk is not None:
        event = get_object_or_404(Event, pk=pk)
        if not can_manage_event(request.user, event):
            messages.error(request, 'You do not have permission to view vendors for this event.')
            return redirect('events:event_list')
        vendors = Vendor.objects.filter(event=event)
        return render(request, 'events/vendor_list.html', {'event': event, 'vendors': vendors})

    events = Event.objects.filter(organizer=request.user) if not getattr(request.user.profile, 'is_admin', False) else Event.objects.all()
    vendors = Vendor.objects.filter(event__in=events)
    return render(request, 'events/vendor_list.html', {'vendors': vendors, 'event': None})


@login_required
def vendor_detail(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if not can_manage_event(request.user, vendor.event):
        messages.error(request, 'You do not have permission to view this vendor.')
        return redirect('events:event_list')
    checklist = getattr(vendor, 'sustainability_checklist', None)
    return render(request, 'events/vendor_detail.html', {'vendor': vendor, 'checklist': checklist})


@login_required
def vendor_create(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to add a vendor to this event.')
        return redirect('events:event_list')

    if request.method == 'POST':
        form = VendorForm(request.POST)
        if form.is_valid():
            vendor = form.save(commit=False)
            vendor.event = event
            vendor.save()
            messages.success(request, 'Vendor added successfully.')
            return redirect('events:vendor_detail', pk=vendor.pk)
    else:
        form = VendorForm()

    return render(request, 'events/vendor_form.html', {'form': form, 'event': event, 'title': 'Add Vendor'})


@login_required
def vendor_update(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if not can_manage_event(request.user, vendor.event):
        messages.error(request, 'You do not have permission to update this vendor.')
        return redirect('events:event_list')

    if request.method == 'POST':
        form = VendorForm(request.POST, instance=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendor updated successfully.')
            return redirect('events:vendor_detail', pk=vendor.pk)
    else:
        form = VendorForm(instance=vendor)

    return render(request, 'events/vendor_form.html', {'form': form, 'event': vendor.event, 'title': 'Update Vendor'})


@login_required
def vendor_delete(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if not can_manage_event(request.user, vendor.event):
        messages.error(request, 'You do not have permission to delete this vendor.')
        return redirect('events:event_list')

    if request.method == 'POST':
        vendor.delete()
        messages.success(request, 'Vendor deleted successfully.')
        return redirect('events:event_detail', pk=vendor.event.pk)

    return render(request, 'events/vendor_confirm_delete.html', {'vendor': vendor})


@login_required
def vendor_checklist_create(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if not can_manage_event(request.user, vendor.event):
        messages.error(request, 'You do not have permission to manage this vendor checklist.')
        return redirect('events:event_list')

    checklist = getattr(vendor, 'sustainability_checklist', None)
    if checklist:
        return redirect('events:vendor_checklist_update', pk=vendor.pk)

    if request.method == 'POST':
        form = VendorChecklistForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.vendor = vendor
            instance.save()
            vendor.is_eco_friendly = instance.sustainability_score >= 70
            vendor.sustainability_rating = int(instance.sustainability_score)
            vendor.save()
            messages.success(request, 'Vendor sustainability checklist saved.')
            return redirect('events:vendor_detail', pk=vendor.pk)
    else:
        form = VendorChecklistForm()

    return render(request, 'events/vendor_checklist_form.html', {'form': form, 'vendor': vendor, 'title': 'Vendor Sustainability Checklist'})


@login_required
def vendor_checklist_update(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if not can_manage_event(request.user, vendor.event):
        messages.error(request, 'You do not have permission to manage this vendor checklist.')
        return redirect('events:event_list')

    checklist = getattr(vendor, 'sustainability_checklist', None)
    if not checklist:
        return redirect('events:vendor_checklist_create', pk=vendor.pk)

    if request.method == 'POST':
        form = VendorChecklistForm(request.POST, instance=checklist)
        if form.is_valid():
            instance = form.save()
            vendor.is_eco_friendly = instance.sustainability_score >= 70
            vendor.sustainability_rating = int(instance.sustainability_score)
            vendor.save()
            messages.success(request, 'Vendor sustainability checklist updated.')
            return redirect('events:vendor_detail', pk=vendor.pk)
    else:
        form = VendorChecklistForm(instance=checklist)

    return render(request, 'events/vendor_checklist_form.html', {'form': form, 'vendor': vendor, 'title': 'Update Vendor Sustainability Checklist'})


@login_required
def sustainability_dashboard(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to view sustainability details for this event.')
        return redirect('events:event_list')

    checklist = SustainabilityChecklist.objects.filter(event=event).first()
    if not checklist:
        return redirect('events:sustainability_checklist_create', pk=event.pk)

    category_scores = checklist.category_summary
    total_categories = len(category_scores)
    overall_score = checklist.overall_score
    context = {
        'event': event,
        'checklist': checklist,
        'category_scores': category_scores,
        'total_categories': total_categories,
        'overall_score': overall_score,
    }
    return render(request, 'events/sustainability_dashboard.html', context)


@login_required
def sustainability_checklist_create(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to create a sustainability checklist for this event.')
        return redirect('events:event_list')

    checklist = SustainabilityChecklist.objects.filter(event=event).first()
    if checklist:
        return redirect('events:sustainability_dashboard', pk=event.pk)

    if request.method == 'POST':
        form = SustainabilityChecklistForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.event = event
            instance.save()
            messages.success(request, 'Sustainability checklist created successfully.')
            return redirect('events:sustainability_checklist_form', pk=event.pk, checklist_id=instance.pk)
    else:
        form = SustainabilityChecklistForm()

    return render(request, 'events/sustainability_checklist_form.html', {'form': form, 'event': event, 'title': 'Create Sustainability Checklist'})


@login_required
def sustainability_checklist_form(request, pk, checklist_id):
    event = get_object_or_404(Event, pk=pk)
    checklist = get_object_or_404(SustainabilityChecklist, pk=checklist_id, event=event)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to edit this checklist.')
        return redirect('events:event_list')

    items = checklist.items.all()
    if request.method == 'POST':
        for item in items:
            response = request.POST.get(f'item_{item.pk}_response')
            if response in SustainabilityChecklist.Response.values:
                item.response = response
                item.score = SustainabilityChecklist.SCORE_MAP[response]
            item.save()
        messages.success(request, 'Checklist updated successfully.')
        return redirect('events:sustainability_dashboard', pk=event.pk)

    item_forms = []
    for item in items:
        item_forms.append({'item': item, 'form': ChecklistItemForm(instance=item)})

    if not item_forms:
        default_items = [
            {'question': 'Food waste is minimized during the event.', 'category': 'Food Management', 'response': 'Yes', 'score': 100},
            {'question': 'Single-use plastic is reduced or avoided.', 'category': 'Plastic Reduction', 'response': 'Partially', 'score': 50},
            {'question': 'Paper usage is reduced.', 'category': 'Paper Reduction', 'response': 'Yes', 'score': 100},
            {'question': 'Waste is segregated properly.', 'category': 'Waste Segregation', 'response': 'No', 'score': 0},
            {'question': 'Recycling practices are followed.', 'category': 'Recycling', 'response': 'Yes', 'score': 100},
            {'question': 'Energy usage is monitored and optimized.', 'category': 'Energy Usage', 'response': 'Partially', 'score': 50},
            {'question': 'Transportation is planned to reduce emissions.', 'category': 'Transportation', 'response': 'Yes', 'score': 100},
            {'question': 'Eco-friendly materials are used wherever possible.', 'category': 'Eco-friendly Materials', 'response': 'Yes', 'score': 100},
            {'question': 'Leftover food is managed responsibly.', 'category': 'Leftover Food Management', 'response': 'No', 'score': 0},
        ]
        for data in default_items:
            ChecklistItem.objects.create(checklist=checklist, **data)
        item_forms = [{'item': item, 'form': ChecklistItemForm(instance=item)} for item in checklist.items.all()]

    return render(request, 'events/sustainability_checklist_form.html', {'event': event, 'checklist': checklist, 'items': item_forms, 'title': 'Sustainability Checklist'})


@login_required
def resource_plan_create(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to create a resource plan for this event.')
        return redirect('events:event_list')
    if hasattr(event, 'resource_plan'):
        return redirect('events:resource_plan_update', pk=event.pk)

    if request.method == 'POST':
        form = ResourcePlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.event = event
            plan.save()
            messages.success(request, 'Resource plan created successfully.')
            return redirect('events:resource_plan_detail', pk=event.pk)
    else:
        form = ResourcePlanForm()

    return render(request, 'events/resource_plan_form.html', {'form': form, 'event': event, 'title': 'Create Resource Plan'})


@login_required
def resource_plan_update(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to update this resource plan.')
        return redirect('events:event_list')

    plan = getattr(event, 'resource_plan', None)
    if not plan:
        return redirect('events:resource_plan_create', pk=event.pk)

    if request.method == 'POST':
        form = ResourcePlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resource plan updated successfully.')
            return redirect('events:resource_plan_detail', pk=event.pk)
    else:
        form = ResourcePlanForm(instance=plan)

    return render(request, 'events/resource_plan_form.html', {'form': form, 'event': event, 'title': 'Update Resource Plan'})


@login_required
def resource_plan_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_manage_event(request.user, event):
        messages.error(request, 'You do not have permission to delete this resource plan.')
        return redirect('events:event_list')

    plan = getattr(event, 'resource_plan', None)
    if not plan:
        return redirect('events:event_detail', pk=event.pk)

    if request.method == 'POST':
        plan.delete()
        messages.success(request, 'Resource plan deleted successfully.')
        return redirect('events:event_detail', pk=event.pk)

    return render(request, 'events/resource_plan_confirm_delete.html', {'event': event, 'plan': plan})


@login_required
def historical_dataset(request):
    profile = getattr(request.user, 'profile', None)
    if not request.user.is_superuser and not (profile and profile.is_admin):
        messages.error(request, 'Only admins can manage historical event datasets.')
        return redirect('accounts:profile')

    query = request.GET.get('q', '').strip()
    event_type = request.GET.get('event_type', '').strip()
    catering_type = request.GET.get('catering_type', '').strip()
    records = HistoricalEventRecord.objects.all()
    if query:
        records = records.filter(event_type__icontains=query)
    if event_type:
        records = records.filter(event_type=event_type)
    if catering_type:
        records = records.filter(catering_type=catering_type)
    stats = HistoricalEventRecord.objects.aggregate(
        total=Count('id'),
        average_expected=Avg('expected_attendees'),
        average_actual=Avg('actual_attendees'),
        average_sustainability=Avg('sustainability_score'),
        total_waste=Sum('total_actual_waste'),
    )
    return render(request, 'events/historical_dataset.html', {
        'records': records,
        'stats': stats,
        'event_types': HistoricalEventRecord.objects.values_list('event_type', flat=True).distinct().order_by('event_type'),
        'catering_types': HistoricalEventRecord.objects.values_list('catering_type', flat=True).distinct().order_by('catering_type'),
        'query': query,
        'selected_event_type': event_type,
        'selected_catering_type': catering_type,
    })


@login_required
def historical_dataset_upload(request):
    profile = getattr(request.user, 'profile', None)
    if not request.user.is_superuser and not (profile and profile.is_admin):
        messages.error(request, 'Only admins can upload historical event datasets.')
        return redirect('accounts:profile')
    form = HistoricalDatasetUploadForm(request.POST or None, request.FILES or None)
    import_result = None
    if request.method == 'POST' and form.is_valid():
        try:
            import_result = process_historical_csv(form.cleaned_data['csv_file'])
        except (pd.errors.ParserError, UnicodeDecodeError) as error:
            form.add_error('csv_file', f'Could not read CSV: {error}')
        else:
            if import_result.missing_columns:
                form.add_error('csv_file', 'Missing required columns: ' + ', '.join(import_result.missing_columns))
            else:
                HistoricalEventRecord.objects.bulk_create([
                    HistoricalEventRecord(source_file=form.cleaned_data['csv_file'].name, **row)
                    for row in import_result.valid_rows
                ])
                messages.success(request, f'Imported {len(import_result.valid_rows)} valid record(s).')
                if import_result.invalid_rows:
                    messages.warning(request, f'{len(import_result.invalid_rows)} invalid row(s) were skipped.')
                return render(request, 'events/historical_dataset_upload.html', {'form': HistoricalDatasetUploadForm(), 'result': import_result})
    return render(request, 'events/historical_dataset_upload.html', {'form': form, 'result': import_result})


@login_required
def historical_record_delete(request, pk):
    profile = getattr(request.user, 'profile', None)
    if not request.user.is_superuser and not (profile and profile.is_admin):
        messages.error(request, 'Only admins can delete historical records.')
        return redirect('accounts:profile')
    record = get_object_or_404(HistoricalEventRecord, pk=pk)
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Historical record deleted.')
    return redirect('events:historical_dataset')


@login_required
def ml_predictions(request):
    profile = getattr(request.user, 'profile', None)
    if not request.user.is_superuser and not (profile and profile.is_admin):
        messages.error(request, 'Only admins can run ML predictions.')
        return redirect('accounts:profile')
    form = MLPredictionForm(request.POST or None)
    predictions = None
    model_error = None
    if request.method == 'POST' and form.is_valid():
        try:
            predictions = predict_all(form.cleaned_data)
        except (FileNotFoundError, ValueError) as error:
            model_error = str(error)
    return render(request, 'events/ml_predictions.html', {
        'form': form,
        'predictions': predictions,
        'model_error': model_error,
    })


@login_required
def waste_prediction(request):
    profile = getattr(request.user, 'profile', None)
    events = Event.objects.all() if request.user.is_superuser or (profile and profile.is_admin) else Event.objects.filter(organizer=request.user)
    form = WastePredictionForm(request.POST or None)
    form.fields['event'].queryset = events
    if request.method == 'GET' and request.GET.get('event'):
        form.initial['event'] = request.GET['event']
    prediction = None
    prediction_data = None
    error = None
    if request.method == 'POST' and form.is_valid():
        event = form.cleaned_data['event']
        plan = getattr(event, 'resource_plan', None)
        if plan is None:
            error = 'Create a resource plan for this event before generating a waste prediction.'
        else:
            features = {
                'event_type': event.event_type,
                'duration': event.duration,
                'expected_attendees': event.expected_attendees,
                'catering_type': event.catering_type,
                'food_quantity': plan.food_total,
                'plastic_quantity': plan.plastic,
                'paper_quantity': plan.paper,
                'material_quantity': plan.material_total,
            }
            try:
                predictions = predict_all(features)
                total_waste = sum(predictions[target] for target in ('food_waste', 'plastic_waste', 'paper_waste', 'material_waste'))
                risk_level = waste_risk_level(total_waste, predictions['attendance'])
                prediction = Prediction.objects.create(
                    event=event,
                    predicted_attendance=predictions['attendance'],
                    predicted_food_waste=predictions['food_waste'],
                    predicted_plastic_waste=predictions['plastic_waste'],
                    predicted_paper_waste=predictions['paper_waste'],
                    predicted_material_waste=predictions['material_waste'],
                    total_predicted_waste=total_waste,
                    risk_level=risk_level,
                    model_version=model_version_summary(),
                )
                recommendations = generate_recommendations(event, prediction)
                prediction_data = {
                    'labels': ['Food Waste', 'Plastic Waste', 'Paper Waste', 'Material Waste'],
                    'values': [prediction.predicted_food_waste, prediction.predicted_plastic_waste, prediction.predicted_paper_waste, prediction.predicted_material_waste],
                }
            except (FileNotFoundError, ValueError) as prediction_error:
                error = str(prediction_error)
    return render(request, 'events/waste_prediction.html', {
        'form': form,
        'prediction': prediction,
        'prediction_data': prediction_data,
        'error': error,
        'thresholds': RiskThresholdConfig.active(),
        'recommendations': prediction.recommendations.all() if prediction else [],
    })


@login_required
def recommendation_report(request):
    profile = getattr(request.user, 'profile', None)
    events = Event.objects.all() if request.user.is_superuser or (profile and profile.is_admin) else Event.objects.filter(organizer=request.user)
    event_id = request.GET.get('event', '')
    recommendations = Recommendation.objects.filter(event__in=events).select_related('event', 'prediction')
    if event_id:
        recommendations = recommendations.filter(event_id=event_id)
    return render(request, 'events/recommendation_report.html', {
        'recommendations': recommendations,
        'events': events,
        'selected_event': event_id,
    })


@login_required
def waste_analysis(request):
    profile = getattr(request.user, 'profile', None)
    events = Event.objects.filter(status=Event.Status.COMPLETED)
    if not request.user.is_superuser and not (profile and profile.is_admin):
        events = events.filter(organizer=request.user)

    metric_definitions = (
        ('Food Waste', 'predicted_food_waste', ('food_waste', 'leftover_food')),
        ('Plastic Waste', 'predicted_plastic_waste', ('plastic_waste',)),
        ('Paper Waste', 'predicted_paper_waste', ('paper_waste',)),
        ('Material Waste', 'predicted_material_waste', ('glass_waste', 'metal_waste', 'decoration_waste', 'other_waste')),
        ('Total Waste', 'total_predicted_waste', None),
    )
    comparison_rows = []
    pending_events = []
    chart_totals = {
        label: {'predicted': Decimal('0'), 'actual': Decimal('0')}
        for label, _, _ in metric_definitions
    }
    matched_event_count = 0

    for event in events.order_by('-event_date', 'event_name'):
        prediction = event.predictions.order_by('-created_at').first()
        try:
            actual_record = event.waste_record
        except WasteRecord.DoesNotExist:
            actual_record = None

        missing = []
        if prediction is None:
            missing.append('prediction')
        if actual_record is None:
            missing.append('actual waste record')
        if missing:
            pending_events.append({'event': event, 'missing': f"No {' and no '.join(missing)}"})
            continue

        matched_event_count += 1
        for label, prediction_field, actual_fields in metric_definitions:
            predicted = Decimal(str(getattr(prediction, prediction_field)))
            if actual_fields is None:
                actual = actual_record.total_actual_waste
            else:
                actual = sum((getattr(actual_record, field) for field in actual_fields), Decimal('0'))
            difference = predicted - actual
            percentage_error = abs(difference) / actual * 100 if actual else None
            if difference > 0:
                direction = 'over'
                difference_label = 'Over by'
            elif difference < 0:
                direction = 'under'
                difference_label = 'Under by'
            else:
                direction = 'exact'
                difference_label = 'Exact'

            comparison_rows.append({
                'event': event,
                'metric': label,
                'predicted': predicted,
                'actual': actual,
                'absolute_error': abs(difference),
                'percentage_error': percentage_error,
                'has_percentage_error': percentage_error is not None,
                'difference_amount': abs(difference),
                'difference_label': difference_label,
                'direction': direction,
            })
            chart_totals[label]['predicted'] += predicted
            chart_totals[label]['actual'] += actual

    total_rows = [row for row in comparison_rows if row['metric'] == 'Total Waste']

    def mean(values):
        return sum(values, Decimal('0')) / len(values) if values else None

    average_predicted_total = mean([row['predicted'] for row in total_rows])
    average_actual_total = mean([row['actual'] for row in total_rows])
    mean_absolute_total_error = mean([row['absolute_error'] for row in total_rows])
    total_percentage_errors = [row['percentage_error'] for row in total_rows if row['has_percentage_error']]
    mean_total_percentage_error = mean(total_percentage_errors)

    chart_metrics = []
    for label, _, _ in metric_definitions:
        predicted_average = chart_totals[label]['predicted'] / matched_event_count if matched_event_count else Decimal('0')
        actual_average = chart_totals[label]['actual'] / matched_event_count if matched_event_count else Decimal('0')
        chart_metrics.append({
            'label': label,
            'predicted_average': predicted_average,
            'actual_average': actual_average,
        })
    chart_max = max(
        (max(metric['predicted_average'], metric['actual_average']) for metric in chart_metrics),
        default=Decimal('0'),
    )
    for metric in chart_metrics:
        metric['predicted_width'] = metric['predicted_average'] / chart_max * 100 if chart_max else 0
        metric['actual_width'] = metric['actual_average'] / chart_max * 100 if chart_max else 0

    return render(request, 'events/waste_analysis.html', {
        'completed_event_count': events.count(),
        'matched_event_count': matched_event_count,
        'comparison_rows': comparison_rows,
        'pending_events': pending_events,
        'chart_metrics': chart_metrics,
        'average_predicted_total': average_predicted_total,
        'average_actual_total': average_actual_total,
        'mean_absolute_total_error': mean_absolute_total_error,
        'mean_total_percentage_error': mean_total_percentage_error,
        'has_mean_total_percentage_error': mean_total_percentage_error is not None,
    })
