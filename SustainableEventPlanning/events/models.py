import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Event(models.Model):
    class EventType(models.TextChoices):
        WEDDING = 'Wedding', 'Wedding'
        CONFERENCE = 'Conference', 'Conference'
        SEMINAR = 'Seminar', 'Seminar'
        COLLEGE_EVENT = 'College Event', 'College Event'
        CORPORATE_EVENT = 'Corporate Event', 'Corporate Event'
        BIRTHDAY = 'Birthday', 'Birthday'
        FESTIVAL = 'Festival', 'Festival'
        SPORTS_EVENT = 'Sports Event', 'Sports Event'
        EXHIBITION = 'Exhibition', 'Exhibition'
        COMMUNITY_EVENT = 'Community Event', 'Community Event'
        OTHER = 'Other', 'Other'

    class CateringType(models.TextChoices):
        VEGETARIAN = 'Vegetarian', 'Vegetarian'
        NON_VEGETARIAN = 'Non-Vegetarian', 'Non-Vegetarian'
        VEGAN = 'Vegan', 'Vegan'
        MIXED = 'Mixed', 'Mixed'
        CUSTOM = 'Custom', 'Custom'

    class FoodServiceType(models.TextChoices):
        BUFFET = 'Buffet', 'Buffet'
        PLATED = 'Plated', 'Plated'
        FOOD_TRUCK = 'Food Truck', 'Food Truck'
        COCKTAIL = 'Cocktail', 'Cocktail'
        BOXED = 'Boxed Meals', 'Boxed Meals'
        OTHER = 'Other', 'Other'

    class Status(models.TextChoices):
        DRAFT = 'Draft', 'Draft'
        SCHEDULED = 'Scheduled', 'Scheduled'
        ONGOING = 'Ongoing', 'Ongoing'
        COMPLETED = 'Completed', 'Completed'
        CANCELLED = 'Cancelled', 'Cancelled'
        POSTPONED = 'Postponed', 'Postponed'

    event_name = models.CharField(max_length=200)
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        default=EventType.OTHER,
    )
    venue = models.CharField(max_length=255)
    event_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration = models.PositiveIntegerField(help_text='Duration in hours')
    expected_attendees = models.PositiveIntegerField()
    catering_type = models.CharField(
        max_length=30,
        choices=CateringType.choices,
        default=CateringType.MIXED,
    )
    food_service_type = models.CharField(
        max_length=30,
        choices=FoodServiceType.choices,
        default=FoodServiceType.BUFFET,
    )
    number_of_meals = models.PositiveIntegerField(default=0)
    number_of_vendors = models.PositiveIntegerField(default=0)
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organized_events',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    class Meta:
        ordering = ['-event_date', '-created_at']
        verbose_name = 'Event'
        verbose_name_plural = 'Events'

    def __str__(self):
        return self.event_name

    @property
    def organizer_name(self):
        return self.organizer.get_full_name() or self.organizer.username

    @property
    def registered_attendees(self):
        return self.attendees.count()

    @property
    def actual_attendance(self):
        return self.attendees.filter(is_present=True).count()

    @property
    def attendance_percentage(self):
        if not self.registered_attendees:
            return 0
        return round(self.actual_attendance / self.registered_attendees * 100, 2)


class Attendance(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='attendees',
    )
    attendee_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    registration_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_code = models.ImageField(upload_to='attendance_qr_codes/', blank=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    is_present = models.BooleanField(default=False)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-registered_at']
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'

    def __str__(self):
        return f'{self.attendee_name} - {self.event.event_name}'


class HistoricalEventRecord(models.Model):
    event_type = models.CharField(max_length=100)
    duration = models.FloatField()
    expected_attendees = models.PositiveIntegerField()
    actual_attendees = models.PositiveIntegerField()
    catering_type = models.CharField(max_length=100)
    food_quantity = models.FloatField()
    plastic_quantity = models.FloatField()
    paper_quantity = models.FloatField()
    material_quantity = models.FloatField()
    actual_food_waste = models.FloatField()
    actual_plastic_waste = models.FloatField()
    actual_paper_waste = models.FloatField()
    actual_material_waste = models.FloatField()
    total_actual_waste = models.FloatField()
    sustainability_score = models.FloatField()
    source_file = models.CharField(max_length=255, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-imported_at', '-id']
        verbose_name = 'Historical Event Record'
        verbose_name_plural = 'Historical Event Records'

    def __str__(self):
        return f'{self.event_type} - {self.imported_at:%Y-%m-%d}'


class Prediction(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = 'Low', 'Low'
        MEDIUM = 'Medium', 'Medium'
        HIGH = 'High', 'High'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='predictions')
    predicted_attendance = models.FloatField()
    predicted_food_waste = models.FloatField()
    predicted_plastic_waste = models.FloatField()
    predicted_paper_waste = models.FloatField()
    predicted_material_waste = models.FloatField()
    total_predicted_waste = models.FloatField()
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    model_version = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Waste Prediction'
        verbose_name_plural = 'Waste Predictions'

    def __str__(self):
        return f'{self.event.event_name} - {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def waste_per_attendee(self):
        if self.predicted_attendance <= 0:
            return 0
        return self.total_predicted_waste / self.predicted_attendance


class Recommendation(models.Model):
    class Priority(models.TextChoices):
        HIGH = 'High', 'High'
        MEDIUM = 'Medium', 'Medium'
        LOW = 'Low', 'Low'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='recommendations')
    prediction = models.ForeignKey(Prediction, on_delete=models.CASCADE, related_name='recommendations')
    category = models.CharField(max_length=40)
    title = models.CharField(max_length=255)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    metric_value = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', 'priority', 'id']
        verbose_name = 'Sustainability Recommendation'
        verbose_name_plural = 'Sustainability Recommendations'

    def __str__(self):
        return f'{self.event.event_name}: {self.title}'


class RiskThresholdConfig(models.Model):
    key = models.CharField(max_length=20, primary_key=True, default='active')
    low_max_total_waste = models.FloatField(
        default=25,
        validators=[MinValueValidator(0)],
        help_text='LOW requires total predicted waste at or below this guardrail.',
    )
    medium_max_total_waste = models.FloatField(
        default=75,
        validators=[MinValueValidator(0)],
        help_text='HIGH starts when total predicted waste exceeds this limit.',
    )
    low_max_waste_per_attendee = models.FloatField(
        default=0.10,
        validators=[MinValueValidator(0)],
        help_text='LOW requires waste per attendee at or below this normalized limit.',
    )
    medium_max_waste_per_attendee = models.FloatField(
        default=0.20,
        validators=[MinValueValidator(0)],
        help_text='HIGH starts when waste per attendee exceeds this normalized limit.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Waste Risk Threshold Configuration'
        verbose_name_plural = 'Waste Risk Threshold Configuration'

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.low_max_total_waste >= self.medium_max_total_waste:
            errors['medium_max_total_waste'] = 'Medium total-waste limit must be greater than the low limit.'
        if self.low_max_waste_per_attendee >= self.medium_max_waste_per_attendee:
            errors['medium_max_waste_per_attendee'] = 'Medium per-attendee limit must be greater than the low limit.'
        if errors:
            raise ValidationError(errors)

    @classmethod
    def active(cls):
        config, _ = cls.objects.get_or_create(key='active')
        return config

    def __str__(self):
        return 'Active waste risk thresholds'


class ResourcePlan(models.Model):
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name='resource_plan',
    )

    rice = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    vegetables = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    meat = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    snacks = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    bread = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    drinks = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    desserts = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    total_food_quantity = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    plastic = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    paper = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    glass = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    metal = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    decoration_material = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    disposable_items = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    other_materials = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ['-event__event_date']
        verbose_name = 'Resource Plan'
        verbose_name_plural = 'Resource Plans'

    def __str__(self):
        return f"Resource plan for {self.event.event_name}"

    @property
    def food_total(self):
        return (
            self.rice
            + self.vegetables
            + self.meat
            + self.snacks
            + self.bread
            + self.drinks
            + self.desserts
        )

    @property
    def material_total(self):
        return (
            self.plastic
            + self.paper
            + self.glass
            + self.metal
            + self.decoration_material
            + self.disposable_items
            + self.other_materials
        )

    @property
    def overall_total(self):
        return self.food_total + self.material_total


class WasteRecord(models.Model):
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name='waste_record',
    )
    actual_attendance = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    food_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    plastic_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    paper_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    glass_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    metal_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    decoration_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    other_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    leftover_food = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    recycled_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    disposed_waste = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Post-event Waste Record'
        verbose_name_plural = 'Post-event Waste Records'

    def __str__(self):
        return f'Waste record for {self.event.event_name}'

    @property
    def total_actual_waste(self):
        return sum((
            self.food_waste,
            self.plastic_waste,
            self.paper_waste,
            self.glass_waste,
            self.metal_waste,
            self.decoration_waste,
            self.other_waste,
            self.leftover_food,
        ))


class Vendor(models.Model):
    class VendorType(models.TextChoices):
        FOOD = 'Food', 'Food'
        DECORATION = 'Decoration', 'Decoration'
        MATERIAL = 'Material', 'Material'
        TRANSPORT = 'Transport', 'Transport'
        WASTE_MANAGEMENT = 'Waste Management', 'Waste Management'
        OTHER = 'Other', 'Other'

    vendor_name = models.CharField(max_length=200)
    vendor_type = models.CharField(
        max_length=50,
        choices=VendorType.choices,
        default=VendorType.OTHER,
    )
    contact_person = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.TextField()
    sustainability_rating = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_eco_friendly = models.BooleanField(default=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='vendors',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['vendor_name']
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'

    def __str__(self):
        return self.vendor_name


class VendorChecklist(models.Model):
    class AnswerChoice(models.TextChoices):
        YES = 'Yes', 'Yes'
        NO = 'No', 'No'
        PARTIALLY = 'Partially', 'Partially'
        NOT_APPLICABLE = 'Not Applicable', 'Not Applicable'

    SCORE_MAP = {
        'Yes': 100,
        'No': 0,
        'Partially': 50,
        'Not Applicable': 0,
    }

    vendor = models.OneToOneField(
        Vendor,
        on_delete=models.CASCADE,
        related_name='sustainability_checklist',
    )
    avoids_single_use_plastic = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    uses_reusable_containers = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    provides_waste_segmentation = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    uses_eco_friendly_materials = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    minimizes_packaging = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    uses_recyclable_materials = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)
    has_waste_management_practices = models.CharField(max_length=20, choices=AnswerChoice.choices, default=AnswerChoice.NOT_APPLICABLE)

    class Meta:
        verbose_name = 'Vendor Sustainability Checklist'
        verbose_name_plural = 'Vendor Sustainability Checklists'

    def __str__(self):
        return f"Checklist for {self.vendor.vendor_name}"

    @property
    def sustainability_score(self):
        answers = [
            self.avoids_single_use_plastic,
            self.uses_reusable_containers,
            self.provides_waste_segmentation,
            self.uses_eco_friendly_materials,
            self.minimizes_packaging,
            self.uses_recyclable_materials,
            self.has_waste_management_practices,
        ]
        total = sum(self.SCORE_MAP.get(answer, 0) for answer in answers)
        return round(total / len(answers), 2)


class SustainabilityChecklist(models.Model):
    class Category(models.TextChoices):
        FOOD_MANAGEMENT = 'Food Management', 'Food Management'
        PLASTIC_REDUCTION = 'Plastic Reduction', 'Plastic Reduction'
        PAPER_REDUCTION = 'Paper Reduction', 'Paper Reduction'
        WASTE_SEGREGATION = 'Waste Segregation', 'Waste Segregation'
        RECYCLING = 'Recycling', 'Recycling'
        ENERGY_USAGE = 'Energy Usage', 'Energy Usage'
        TRANSPORTATION = 'Transportation', 'Transportation'
        ECO_FRIENDLY_MATERIALS = 'Eco-friendly Materials', 'Eco-friendly Materials'
        LEFTOVER_FOOD_MANAGEMENT = 'Leftover Food Management', 'Leftover Food Management'

    class Response(models.TextChoices):
        YES = 'Yes', 'Yes'
        NO = 'No', 'No'
        PARTIALLY = 'Partially', 'Partially'
        NOT_APPLICABLE = 'Not Applicable', 'Not Applicable'

    SCORE_MAP = {
        'Yes': 100,
        'No': 0,
        'Partially': 50,
        'Not Applicable': 0,
    }

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='sustainability_checklists',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sustainability Checklist'
        verbose_name_plural = 'Sustainability Checklists'

    @property
    def overall_score(self):
        items = self.items.all()
        if not items:
            return 0
        total = sum(item.score for item in items)
        return round(total / len(items), 2)

    @property
    def category_summary(self):
        totals = {}
        counts = {}
        for item in self.items.all():
            totals[item.category] = totals.get(item.category, 0) + item.score
            counts[item.category] = counts.get(item.category, 0) + 1
        return {
            category: round(totals[category] / counts[category], 2)
            for category in totals
        }

    @property
    def percent_complete(self):
        items = self.items.count()
        if not items:
            return 0
        return 100

    def __str__(self):
        return f"Sustainability checklist for {self.event.event_name}"


class ChecklistItem(models.Model):
    checklist = models.ForeignKey(
        SustainabilityChecklist,
        on_delete=models.CASCADE,
        related_name='items',
    )
    question = models.CharField(max_length=255)
    category = models.CharField(max_length=80, choices=SustainabilityChecklist.Category.choices)
    response = models.CharField(max_length=20, choices=SustainabilityChecklist.Response.choices, default=SustainabilityChecklist.Response.NOT_APPLICABLE)
    score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ['category', 'id']
        verbose_name = 'Checklist Item'
        verbose_name_plural = 'Checklist Items'

    def __str__(self):
        return f"{self.category}: {self.question}"
