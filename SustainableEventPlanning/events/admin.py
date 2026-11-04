from django.contrib import admin

from .models import Attendance, Event, HistoricalEventRecord, Prediction, Recommendation, ResourcePlan, RiskThresholdConfig, Vendor, VendorChecklist, SustainabilityChecklist, ChecklistItem, WasteRecord


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('event', 'category', 'title', 'priority', 'metric_value', 'created_at')
    list_filter = ('category', 'priority', 'event__event_type', 'event__status', 'created_at')
    search_fields = ('event__event_name', 'title', 'description')
    ordering = ('-created_at', 'priority')
    list_select_related = ('event', 'prediction')
    list_per_page = 50


@admin.register(RiskThresholdConfig)
class RiskThresholdConfigAdmin(admin.ModelAdmin):
    list_display = ('key', 'low_max_total_waste', 'medium_max_total_waste', 'low_max_waste_per_attendee', 'medium_max_waste_per_attendee', 'updated_at')
    list_filter = ('updated_at',)
    search_fields = ('key',)
    ordering = ('key',)
    readonly_fields = ('updated_at',)
    fieldsets = (
        ('Total predicted waste', {'fields': ('low_max_total_waste', 'medium_max_total_waste')}),
        ('Waste per attendee', {'fields': ('low_max_waste_per_attendee', 'medium_max_waste_per_attendee')}),
    )

    def has_add_permission(self, request):
        return not RiskThresholdConfig.objects.filter(key='active').exists()

    def save_model(self, request, obj, form, change):
        obj.key = 'active'
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        'event',
        'predicted_attendance',
        'predicted_food_waste',
        'predicted_plastic_waste',
        'predicted_paper_waste',
        'predicted_material_waste',
        'total_predicted_waste',
        'risk_level',
        'created_at',
    )
    list_filter = ('risk_level', 'event__event_type', 'event__status', 'created_at')
    search_fields = ('event__event_name', 'event__organizer__username', 'model_version')
    ordering = ('-created_at',)
    list_select_related = ('event', 'event__organizer')
    list_per_page = 50


@admin.register(HistoricalEventRecord)
class HistoricalEventRecordAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'duration', 'expected_attendees', 'actual_attendees', 'total_actual_waste', 'sustainability_score', 'imported_at')
    list_filter = ('event_type', 'catering_type', 'imported_at')
    search_fields = ('event_type', 'catering_type', 'source_file')
    ordering = ('-imported_at', '-id')
    list_per_page = 50


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('attendee_name', 'event', 'email', 'phone', 'is_present', 'check_in_time', 'registered_at')
    list_filter = ('is_present', 'event__event_type', 'event__status', 'event', 'registered_at')
    search_fields = ('attendee_name', 'email', 'phone', 'registration_id', 'event__event_name')
    ordering = ('-registered_at',)
    list_select_related = ('event',)
    list_per_page = 50


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'event_name',
        'event_type',
        'event_date',
        'venue',
        'organizer',
        'expected_attendees',
        'status',
    )
    list_filter = ('event_type', 'status', 'event_date')
    search_fields = ('event_name', 'venue', 'organizer__username', 'organizer__email')
    ordering = ('-event_date',)
    list_select_related = ('organizer',)
    list_per_page = 50


@admin.register(ResourcePlan)
class ResourcePlanAdmin(admin.ModelAdmin):
    list_display = ('event', 'food_total', 'material_total', 'overall_total')
    list_filter = ('event__event_type', 'event__status', 'event__event_date')
    search_fields = ('event__event_name', 'event__organizer__username')
    ordering = ('-event__event_date',)
    list_select_related = ('event', 'event__organizer')
    list_per_page = 50


@admin.register(WasteRecord)
class WasteRecordAdmin(admin.ModelAdmin):
    list_display = ('event', 'actual_attendance', 'total_actual_waste', 'recycled_waste', 'disposed_waste', 'recorded_at')
    list_filter = ('event__event_type', 'event__status', 'recorded_at')
    search_fields = ('event__event_name', 'event__organizer__username')
    ordering = ('-recorded_at',)
    readonly_fields = ('recorded_at',)
    list_select_related = ('event', 'event__organizer')
    list_per_page = 50


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('vendor_name', 'vendor_type', 'event', 'sustainability_rating', 'is_eco_friendly')
    list_filter = ('vendor_type', 'is_eco_friendly', 'event__event_type', 'event__status', 'event')
    search_fields = ('vendor_name', 'contact_person', 'email', 'phone', 'event__event_name')
    ordering = ('vendor_name', 'event__event_date')
    list_select_related = ('event',)
    list_per_page = 50


@admin.register(VendorChecklist)
class VendorChecklistAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'sustainability_score', 'vendor_type', 'event_name', 'event_status')
    list_filter = ('vendor__vendor_type', 'vendor__is_eco_friendly', 'vendor__event__status')
    search_fields = ('vendor__vendor_name', 'vendor__contact_person', 'vendor__event__event_name')
    ordering = ('vendor__vendor_name',)
    list_select_related = ('vendor', 'vendor__event')
    list_per_page = 50

    @admin.display(description='Vendor type', ordering='vendor__vendor_type')
    def vendor_type(self, obj):
        return obj.vendor.vendor_type

    @admin.display(description='Event', ordering='vendor__event__event_name')
    def event_name(self, obj):
        return obj.vendor.event.event_name

    @admin.display(description='Event status', ordering='vendor__event__status')
    def event_status(self, obj):
        return obj.vendor.event.status


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ('question', 'category', 'response', 'score')
    show_change_link = True
    ordering = ('category', 'id')


@admin.register(SustainabilityChecklist)
class SustainabilityChecklistAdmin(admin.ModelAdmin):
    list_display = ('event', 'overall_score', 'item_count', 'created_at', 'updated_at')
    list_filter = ('event__event_type', 'event__status', 'created_at', 'updated_at')
    search_fields = ('event__event_name', 'event__organizer__username')
    ordering = ('-created_at',)
    list_select_related = ('event', 'event__organizer')
    list_per_page = 50
    inlines = (ChecklistItemInline,)

    @admin.display(description='Scored items')
    def item_count(self, obj):
        return obj.items.count()


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'response', 'score', 'event_name', 'checklist')
    list_filter = ('category', 'response', 'checklist__event__event_type', 'checklist__event__status')
    search_fields = ('question', 'checklist__event__event_name', 'checklist__event__organizer__username')
    ordering = ('checklist__event__event_date', 'category', 'id')
    list_select_related = ('checklist', 'checklist__event')
    list_per_page = 50

    @admin.display(description='Event', ordering='checklist__event__event_name')
    def event_name(self, obj):
        return obj.checklist.event.event_name
