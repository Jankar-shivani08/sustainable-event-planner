from datetime import datetime

from django import forms

from .models import Attendance, Event, ResourcePlan, Vendor, VendorChecklist, SustainabilityChecklist, ChecklistItem, WasteRecord


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            'event_name',
            'event_type',
            'venue',
            'event_date',
            'start_time',
            'end_time',
            'duration',
            'expected_attendees',
            'catering_type',
            'food_service_type',
            'number_of_meals',
            'number_of_vendors',
            'status',
        ]
        widgets = {
            'event_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter event name'}),
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'venue': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter venue'}),
            'event_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'placeholder': 'Duration in hours'}),
            'expected_attendees': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'catering_type': forms.Select(attrs={'class': 'form-select'}),
            'food_service_type': forms.Select(attrs={'class': 'form-select'}),
            'number_of_meals': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'number_of_vendors': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        duration = cleaned_data.get('duration')

        if start_time and end_time and end_time <= start_time:
            raise forms.ValidationError('End time must be after start time.')

        if duration is not None and duration <= 0:
            raise forms.ValidationError('Duration must be greater than zero.')

        if start_time and end_time and duration is None:
            start_dt = datetime.combine(datetime.today().date(), start_time)
            end_dt = datetime.combine(datetime.today().date(), end_time)
            duration_hours = (end_dt - start_dt).total_seconds() / 3600
            if duration_hours > 0:
                cleaned_data['duration'] = int(duration_hours)

        return cleaned_data

    def clean_expected_attendees(self):
        attendees = self.cleaned_data.get('expected_attendees')
        if attendees is not None and attendees <= 0:
            raise forms.ValidationError('Expected attendees must be greater than zero.')
        return attendees

    def clean_number_of_meals(self):
        meals = self.cleaned_data.get('number_of_meals')
        if meals is not None and meals < 0:
            raise forms.ValidationError('Number of meals cannot be negative.')
        return meals

    def clean_number_of_vendors(self):
        vendors = self.cleaned_data.get('number_of_vendors')
        if vendors is not None and vendors < 0:
            raise forms.ValidationError('Number of vendors cannot be negative.')
        return vendors


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['attendee_name', 'email', 'phone']
        widgets = {
            'attendee_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Attendee name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
        }


class HistoricalDatasetUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Historical event CSV',
        help_text='Upload a CSV with the required historical event columns.',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv,text/csv'}),
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        if not csv_file.name.lower().endswith('.csv'):
            raise forms.ValidationError('Please upload a CSV file.')
        return csv_file


class MLPredictionForm(forms.Form):
    event_type = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    duration = forms.FloatField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))
    expected_attendees = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    catering_type = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    food_quantity = forms.FloatField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))
    plastic_quantity = forms.FloatField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))
    paper_quantity = forms.FloatField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))
    material_quantity = forms.FloatField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))


class WastePredictionForm(forms.Form):
    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        empty_label='Select an event',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class ResourcePlanForm(forms.ModelForm):
    class Meta:
        model = ResourcePlan
        fields = [
            'rice',
            'vegetables',
            'meat',
            'snacks',
            'bread',
            'drinks',
            'desserts',
            'total_food_quantity',
            'plastic',
            'paper',
            'glass',
            'metal',
            'decoration_material',
            'disposable_items',
            'other_materials',
        ]
        widgets = {
            'rice': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'vegetables': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'meat': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'snacks': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'bread': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'drinks': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'desserts': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'total_food_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'plastic': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'paper': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'glass': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'metal': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'decoration_material': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'disposable_items': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
            'other_materials': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.fields:
            value = cleaned_data.get(field_name)
            if value is not None and value < 0:
                self.add_error(field_name, 'Quantity cannot be negative.')
        return cleaned_data


class WasteRecordForm(forms.ModelForm):
    class Meta:
        model = WasteRecord
        fields = [
            'actual_attendance',
            'food_waste',
            'plastic_waste',
            'paper_waste',
            'glass_waste',
            'metal_waste',
            'decoration_waste',
            'other_waste',
            'leftover_food',
            'recycled_waste',
            'disposed_waste',
        ]
        widgets = {
            field: forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.01'})
            for field in fields
        }


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'vendor_name',
            'vendor_type',
            'contact_person',
            'phone',
            'email',
            'address',
            'sustainability_rating',
            'is_eco_friendly',
        ]
        widgets = {
            'vendor_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter vendor name'}),
            'vendor_type': forms.Select(attrs={'class': 'form-select'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Vendor address'}),
            'sustainability_rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'is_eco_friendly': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_sustainability_rating(self):
        value = self.cleaned_data.get('sustainability_rating')
        if value is not None and (value < 0 or value > 100):
            raise forms.ValidationError('Sustainability rating must be between 0 and 100.')
        return value


class VendorChecklistForm(forms.ModelForm):
    class Meta:
        model = VendorChecklist
        fields = [
            'avoids_single_use_plastic',
            'uses_reusable_containers',
            'provides_waste_segmentation',
            'uses_eco_friendly_materials',
            'minimizes_packaging',
            'uses_recyclable_materials',
            'has_waste_management_practices',
        ]
        widgets = {
            field: forms.Select(attrs={'class': 'form-select'})
            for field in fields
        }


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['question', 'category', 'response', 'score']
        widgets = {
            'question': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Checklist question'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'response': forms.Select(attrs={'class': 'form-select'}),
            'score': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
        }

    def clean_score(self):
        score = self.cleaned_data.get('score')
        if score is not None and (score < 0 or score > 100):
            raise forms.ValidationError('Score must be between 0 and 100.')
        return score


class SustainabilityChecklistForm(forms.ModelForm):
    class Meta:
        model = SustainabilityChecklist
        fields = []
