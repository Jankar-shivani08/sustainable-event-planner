from dataclasses import dataclass

from .models import Recommendation, RiskThresholdConfig


@dataclass
class RecommendationDraft:
    category: str
    title: str
    description: str
    priority: str
    metric_value: float | None = None


def _latest_checklist(event):
    return event.sustainability_checklists.order_by('-created_at').first()


def _vendor_score(event):
    scores = []
    for vendor in event.vendors.all():
        checklist = getattr(vendor, 'sustainability_checklist', None)
        scores.append(checklist.sustainability_score if checklist else vendor.sustainability_rating)
    return round(sum(scores) / len(scores), 2) if scores else None


def build_recommendations(event, prediction):
    plan = getattr(event, 'resource_plan', None)
    checklist = _latest_checklist(event)
    thresholds = RiskThresholdConfig.active()
    recommendations = []
    attendance = prediction.predicted_attendance
    category_waste = {
        'Food': prediction.predicted_food_waste,
        'Plastic': prediction.predicted_plastic_waste,
        'Paper': prediction.predicted_paper_waste,
        'Material': prediction.predicted_material_waste,
    }

    # A category is high when its normalized waste exceeds the configured medium limit.
    for category, waste in category_waste.items():
        per_attendee = waste / attendance if attendance > 0 else float('inf')
        if per_attendee > thresholds.medium_max_waste_per_attendee:
            messages = {
                'Food': ('Optimize food quantity', 'Use attendance history to size the menu, plan leftover food donation, and reduce excessive menu quantities.'),
                'Plastic': ('Replace disposable plastic items', 'Use reusable serving materials and provide water dispensers instead of single-use bottles.'),
                'Paper': ('Reduce paper materials', 'Use digital invitations and QR-based event information instead of printed materials.'),
                'Material': ('Reduce event materials', 'Choose reusable decorations, rent materials where possible, and track material quantities before ordering.'),
            }
            title, description = messages[category]
            recommendations.append(RecommendationDraft(category, title, description, Recommendation.Priority.HIGH, per_attendee))

    if plan and plan.food_total > event.expected_attendees * 1.25:
        recommendations.append(RecommendationDraft(
            'Food', 'Review food quantity buffer',
            'Food quantity is more than 25% above expected attendance. Reconcile portions with attendance history before finalizing catering.',
            Recommendation.Priority.MEDIUM, plan.food_total,
        ))
    if attendance < event.expected_attendees * 0.80:
        recommendations.append(RecommendationDraft(
            'Attendance', 'Use attendance history for planning',
            'Predicted attendance is below 80% of expected attendance. Use registration and attendance history to reduce over-ordering.',
            Recommendation.Priority.MEDIUM, attendance,
        ))

    if checklist:
        if checklist.overall_score < 60:
            recommendations.append(RecommendationDraft(
                'Sustainability', 'Improve sustainability checklist performance',
                'The event sustainability score is below 60. Assign owners to the lowest-scoring checklist categories before the event.',
                Recommendation.Priority.HIGH, checklist.overall_score,
            ))
        segregation_score = checklist.category_summary.get('Waste Segregation', 0)
        if segregation_score < 60:
            recommendations.append(RecommendationDraft(
                'Waste Segregation', 'Strengthen waste segregation',
                'Provide separate waste bins and label organic, recyclable, and general waste clearly at collection points.',
                Recommendation.Priority.HIGH, segregation_score,
            ))

    vendor_score = _vendor_score(event)
    if vendor_score is not None and vendor_score < 70:
        recommendations.append(RecommendationDraft(
            'Vendors', 'Work with higher-scoring sustainable vendors',
            'The average vendor sustainability score is below 70. Ask vendors for improvement plans or compare eco-friendly alternatives.',
            Recommendation.Priority.MEDIUM, vendor_score,
        ))
    return recommendations


def generate_recommendations(event, prediction):
    drafts = build_recommendations(event, prediction)
    return Recommendation.objects.bulk_create([
        Recommendation(
            event=event,
            prediction=prediction,
            category=draft.category,
            title=draft.title,
            description=draft.description,
            priority=draft.priority,
            metric_value=draft.metric_value,
        )
        for draft in drafts
    ])