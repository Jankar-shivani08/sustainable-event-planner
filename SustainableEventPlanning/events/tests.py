from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
import tempfile
from unittest.mock import patch

import pandas as pd

from django.contrib.auth import get_user_model
from accounts.models import UserRole

from .dataset import REQUIRED_COLUMNS, process_historical_csv
from .models import Attendance, Event, HistoricalEventRecord, Prediction, Recommendation, ResourcePlan, RiskThresholdConfig, Vendor, VendorChecklist, SustainabilityChecklist, ChecklistItem, WasteRecord
from .recommendations import build_recommendations, generate_recommendations
from .services import check_in_attendee, create_attendance_qr
from .ml.pipeline import FEATURE_COLUMNS, TARGET_COLUMNS, train_all_targets


class AttendanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='attendanceorganizer', password='StrongPass123!')
        self.event = Event.objects.create(
            event_name='Attendance Expo', event_type=Event.EventType.EXHIBITION,
            venue='Main Hall', event_date='2026-10-01', start_time='09:00:00',
            end_time='12:00:00', duration=3, expected_attendees=100, organizer=self.user,
        )

    def test_registration_generates_unique_qr_and_check_in_updates_metrics(self):
        first = Attendance.objects.create(event=self.event, attendee_name='Asha', email='asha@example.com')
        second = Attendance.objects.create(event=self.event, attendee_name='Bala', email='bala@example.com')
        create_attendance_qr(first)
        first.save(update_fields=['qr_code'])
        create_attendance_qr(second)
        second.save(update_fields=['qr_code'])
        check_in_attendee(first)

        self.event.refresh_from_db()
        self.assertNotEqual(first.registration_id, second.registration_id)
        self.assertTrue(first.qr_code.name)
        self.assertTrue(second.qr_code.name)
        self.assertEqual(self.event.registered_attendees, 2)
        self.assertEqual(self.event.actual_attendance, 1)
        self.assertEqual(self.event.attendance_percentage, 50)


class HistoricalDatasetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='datasetadmin', password='StrongPass123!')
        self.user.profile.role = 'ADMIN'
        self.user.profile.save()

    def test_parser_reports_missing_columns_and_invalid_rows(self):
        csv = b'event_type,duration,expected_attendees,actual_attendees,catering_type,food_quantity,plastic_quantity,paper_quantity,material_quantity,actual_food_waste,actual_plastic_waste,actual_paper_waste,actual_material_waste,total_actual_waste,sustainability_score\nConference,2,100,80,Buffet,50,10,5,20,4,1,1,2,8,75\nWedding,invalid,,60,Plated,50,10,5,20,4,1,1,2,8,80\n'
        result = process_historical_csv(SimpleUploadedFile('history.csv', csv))
        self.assertEqual(result.missing_columns, [])
        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(len(result.invalid_rows), 1)
        self.assertTrue(any('duration' in error for error in result.invalid_rows[0]['errors']))

    def test_parser_detects_missing_required_columns(self):
        result = process_historical_csv(SimpleUploadedFile('history.csv', b'event_type,duration\nConference,2\n'))
        self.assertEqual(result.valid_rows, [])
        self.assertEqual(set(result.missing_columns), set(REQUIRED_COLUMNS) - {'event_type', 'duration'})

    def test_admin_uploads_valid_rows_and_can_delete_records(self):
        csv = b'event_type,duration,expected_attendees,actual_attendees,catering_type,food_quantity,plastic_quantity,paper_quantity,material_quantity,actual_food_waste,actual_plastic_waste,actual_paper_waste,actual_material_waste,total_actual_waste,sustainability_score\nConference,2,100,80,Buffet,50,10,5,20,4,1,1,2,8,75\n'
        self.client.force_login(self.user)
        response = self.client.post('/events/historical-dataset/upload/', {'csv_file': SimpleUploadedFile('history.csv', csv, content_type='text/csv')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(HistoricalEventRecord.objects.count(), 1)
        record = HistoricalEventRecord.objects.first()
        self.client.post(f'/events/historical-dataset/{record.pk}/delete/')
        self.assertEqual(HistoricalEventRecord.objects.count(), 0)


class MLPipelineTests(TestCase):
    def test_all_targets_train_compare_models_and_save_artifacts(self):
        frame = pd.read_csv('training_data/sample_historical_events.csv')
        with tempfile.TemporaryDirectory() as output_dir:
            results = train_all_targets(frame, output_dir)

            self.assertEqual({result.target_name for result in results}, set(TARGET_COLUMNS))
            for result in results:
                self.assertIn(result.selected_model, {'linear_regression', 'decision_tree', 'random_forest'})
                self.assertEqual(set(result.metrics), {'linear_regression', 'decision_tree', 'random_forest'})
                for metric_values in result.metrics.values():
                    self.assertEqual(set(metric_values), {'mae', 'rmse', 'r2'})
                self.assertTrue(result.artifact_path.endswith(f'{result.target_name}.joblib'))

    def test_prediction_features_exclude_outcomes_to_prevent_leakage(self):
        outcome_columns = set(TARGET_COLUMNS.values()) | {
            'actual_plastic_waste', 'actual_paper_waste', 'actual_material_waste',
            'total_actual_waste', 'sustainability_score',
        }
        self.assertTrue(set(FEATURE_COLUMNS).isdisjoint(outcome_columns))


class WastePredictionViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='predictionorganizer', password='StrongPass123!')
        self.event = Event.objects.create(
            event_name='Prediction Expo', event_type=Event.EventType.CONFERENCE,
            venue='Main Hall', event_date='2026-10-01', start_time='09:00:00',
            end_time='13:00:00', duration=4, expected_attendees=300,
            catering_type=Event.CateringType.MIXED, organizer=self.user,
        )
        ResourcePlan.objects.create(
            event=self.event, rice=20, vegetables=30, meat=25, snacks=10,
            bread=8, drinks=40, desserts=12, total_food_quantity=145,
            plastic=20, paper=15, glass=5, metal=4, decoration_material=10,
            disposable_items=8, other_materials=3,
        )

    @patch('events.views.model_version_summary', return_value='attendance:linear_regression; food_waste:random_forest')
    @patch('events.views.predict_all')
    def test_organizer_generates_and_stores_prediction(self, predict_all_mock, version_mock):
        predict_all_mock.return_value = {
            'attendance': 275.0,
            'food_waste': 12.5,
            'plastic_waste': 4.0,
            'paper_waste': 3.0,
            'material_waste': 6.5,
        }
        self.client.force_login(self.user)
        response = self.client.get('/events/waste-prediction/', {'event': self.event.pk})
        self.assertContains(response, 'Prediction Expo')
        response = self.client.post('/events/waste-prediction/', {'event': self.event.pk})

        self.assertEqual(response.status_code, 200)
        prediction = Prediction.objects.get(event=self.event)
        self.assertEqual(prediction.predicted_attendance, 275.0)
        self.assertEqual(prediction.total_predicted_waste, 26.0)
        self.assertEqual(prediction.risk_level, 'Medium')
        self.assertEqual(prediction.model_version, 'attendance:linear_regression; food_waste:random_forest')
        predict_all_mock.assert_called_once_with({
            'event_type': 'Conference',
            'duration': 4,
            'expected_attendees': 300,
            'catering_type': 'Mixed',
            'food_quantity': 145,
            'plastic_quantity': 20,
            'paper_quantity': 15,
            'material_quantity': 65,
        })

    def test_risk_uses_total_waste_and_waste_per_attendee(self):
        from .ml.prediction import waste_risk_level

        thresholds = RiskThresholdConfig(
            low_max_total_waste=25,
            medium_max_total_waste=75,
            low_max_waste_per_attendee=0.10,
            medium_max_waste_per_attendee=0.20,
        )
        self.assertEqual(waste_risk_level(20, 250, thresholds), 'Low')
        self.assertEqual(waste_risk_level(26, 275, thresholds), 'Medium')
        self.assertEqual(waste_risk_level(80, 100, thresholds), 'High')


class RecommendationEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='recommendationorganizer', password='StrongPass123!')
        self.event = Event.objects.create(
            event_name='Recommendation Expo', event_type=Event.EventType.FESTIVAL,
            venue='Open Grounds', event_date='2026-10-02', start_time='09:00:00',
            end_time='18:00:00', duration=9, expected_attendees=100, organizer=self.user,
        )
        self.plan = ResourcePlan.objects.create(
            event=self.event, rice=50, vegetables=50, meat=50, snacks=30,
            bread=20, drinks=30, desserts=20, plastic=40, paper=30, glass=5,
            metal=5, decoration_material=20, disposable_items=15, other_materials=5,
        )
        self.prediction = Prediction.objects.create(
            event=self.event, predicted_attendance=100, predicted_food_waste=30,
            predicted_plastic_waste=30, predicted_paper_waste=30,
            predicted_material_waste=30, total_predicted_waste=120,
            risk_level='High', model_version='test',
        )

    def test_engine_generates_actionable_category_and_sustainability_recommendations(self):
        checklist = SustainabilityChecklist.objects.create(event=self.event)
        ChecklistItem.objects.create(
            checklist=checklist, question='Waste is segregated', category='Waste Segregation',
            response='No', score=0,
        )
        Vendor.objects.create(
            event=self.event, vendor_name='Basic Vendor', vendor_type='Other',
            contact_person='Contact', phone='123', email='vendor@example.com',
            address='Address', sustainability_rating=40,
        )

        drafts = build_recommendations(self.event, self.prediction)
        categories = {draft.category for draft in drafts}
        self.assertTrue({'Food', 'Plastic', 'Paper', 'Material', 'Waste Segregation', 'Vendors'} <= categories)
        stored = generate_recommendations(self.event, self.prediction)
        self.assertEqual(len(stored), len(drafts))
        self.assertEqual(Recommendation.objects.filter(prediction=self.prediction).count(), len(drafts))


class ResourcePlanTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='planner',
            email='planner@example.com',
            password='StrongPass123!',
        )
        self.event = Event.objects.create(
            event_name='Green Expo',
            event_type=Event.EventType.EXHIBITION,
            venue='City Hall',
            event_date='2026-10-01',
            start_time='09:00:00',
            end_time='12:00:00',
            duration=3,
            expected_attendees=200,
            organizer=self.user,
        )

    def test_resource_plan_rejects_negative_quantities(self):
        plan = ResourcePlan(
            event=self.event,
            rice=-1,
            vegetables=20,
            meat=0,
            snacks=10,
            bread=5,
            drinks=15,
            desserts=5,
            total_food_quantity=56,
            plastic=10,
            paper=5,
            glass=2,
            metal=3,
            decoration_material=4,
            disposable_items=6,
            other_materials=2,
        )
        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_resource_plan_computes_totals(self):
        plan = ResourcePlan(
            event=self.event,
            rice=10,
            vegetables=20,
            meat=15,
            snacks=10,
            bread=8,
            drinks=30,
            desserts=12,
            total_food_quantity=105,
            plastic=25,
            paper=10,
            glass=5,
            metal=2,
            decoration_material=8,
            disposable_items=12,
            other_materials=3,
        )
        self.assertEqual(plan.food_total, 105)
        self.assertEqual(plan.material_total, 65)
        self.assertEqual(plan.overall_total, 170)


class WasteRecordTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='wasteorganizer', password='StrongPass123!')
        self.event = Event.objects.create(
            event_name='Completed Expo', event_type=Event.EventType.EXHIBITION,
            venue='City Hall', event_date='2026-10-01', start_time='09:00:00',
            end_time='12:00:00', duration=3, expected_attendees=100,
            organizer=self.user, status=Event.Status.COMPLETED,
        )
        self.client.force_login(self.user)

    def test_organizer_records_waste_and_total_excludes_disposition(self):
        response = self.client.post(f'/events/{self.event.pk}/waste-record/', {
            'actual_attendance': 80,
            'food_waste': '1.25',
            'plastic_waste': '2.50',
            'paper_waste': '0.50',
            'glass_waste': '1.00',
            'metal_waste': '0.25',
            'decoration_waste': '0.75',
            'other_waste': '0.50',
            'leftover_food': '1.25',
            'recycled_waste': '3.00',
            'disposed_waste': '4.00',
        })

        self.assertRedirects(response, f'/events/{self.event.pk}/')
        record = WasteRecord.objects.get(event=self.event)
        self.assertEqual(record.total_actual_waste, 8)
        self.assertEqual(record.actual_attendance, 80)

    def test_incomplete_event_cannot_record_waste(self):
        self.event.status = Event.Status.ONGOING
        self.event.save(update_fields=['status'])

        response = self.client.get(f'/events/{self.event.pk}/waste-record/')

        self.assertRedirects(response, f'/events/{self.event.pk}/')
        self.assertFalse(WasteRecord.objects.filter(event=self.event).exists())

    def test_negative_quantities_are_rejected(self):
        response = self.client.post(f'/events/{self.event.pk}/waste-record/', {
            'actual_attendance': 80,
            'food_waste': '-1',
            'plastic_waste': 0,
            'paper_waste': 0,
            'glass_waste': 0,
            'metal_waste': 0,
            'decoration_waste': 0,
            'other_waste': 0,
            'leftover_food': 0,
            'recycled_waste': 0,
            'disposed_waste': 0,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ensure this value is greater than or equal to 0.')
        self.assertFalse(WasteRecord.objects.filter(event=self.event).exists())

    def test_model_validation_rejects_negative_quantities(self):
        record = WasteRecord(event=self.event, food_waste=-1)
        with self.assertRaises(ValidationError):
            record.full_clean()


class WasteAnalysisTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='analysisorganizer', password='StrongPass123!')
        self.event = Event.objects.create(
            event_name='Analysis Expo', event_type=Event.EventType.CONFERENCE,
            venue='Main Hall', event_date='2026-10-01', start_time='09:00:00',
            end_time='13:00:00', duration=4, expected_attendees=100,
            organizer=self.user, status=Event.Status.COMPLETED,
        )
        Prediction.objects.create(
            event=self.event, predicted_attendance=90, predicted_food_waste=4,
            predicted_plastic_waste=0.5, predicted_paper_waste=0.25,
            predicted_material_waste=1, total_predicted_waste=5.75,
            risk_level='Low', model_version='test-model',
        )
        WasteRecord.objects.create(
            event=self.event, actual_attendance=80, food_waste=2,
            leftover_food=1, plastic_waste=1, paper_waste=0,
            glass_waste=0.5, metal_waste=0.25,
            decoration_waste=0.25, other_waste=0.5,
            recycled_waste=2, disposed_waste=3,
        )
        self.client.force_login(self.user)

    def test_analysis_compares_all_categories_and_calculates_errors(self):
        response = self.client.get('/events/waste-analysis/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['matched_event_count'], 1)
        self.assertEqual(len(response.context['comparison_rows']), 5)
        food = next(row for row in response.context['comparison_rows'] if row['metric'] == 'Food Waste')
        total = next(row for row in response.context['comparison_rows'] if row['metric'] == 'Total Waste')
        self.assertEqual(food['actual'], 3)
        self.assertEqual(food['absolute_error'], 1)
        self.assertAlmostEqual(float(food['percentage_error']), 100 / 3)
        self.assertEqual(total['actual'], 5.5)
        self.assertEqual(total['absolute_error'], 0.25)
        self.assertContains(response, 'Over by')
        self.assertContains(response, 'N/A')

    def test_completed_events_without_both_records_are_listed_as_pending(self):
        missing_event = Event.objects.create(
            event_name='Missing Analysis Data', event_type=Event.EventType.SEMINAR,
            venue='Room 2', event_date='2026-10-02', start_time='09:00:00',
            end_time='10:00:00', duration=1, expected_attendees=20,
            organizer=self.user, status=Event.Status.COMPLETED,
        )

        response = self.client.get('/events/waste-analysis/')

        self.assertEqual(response.context['completed_event_count'], 2)
        self.assertEqual(len(response.context['pending_events']), 1)
        self.assertEqual(response.context['pending_events'][0]['event'], missing_event)
        self.assertContains(response, 'No prediction and no actual waste record')


class RoleDashboardTests(TestCase):
    def setUp(self):
        self.organizer = get_user_model().objects.create_user(username='dashboardorganizer', password='StrongPass123!')
        self.organizer.profile.role = UserRole.ORGANIZER
        self.organizer.profile.save()
        self.other_organizer = get_user_model().objects.create_user(username='otherdashboardorganizer', password='StrongPass123!')
        self.other_organizer.profile.role = UserRole.ORGANIZER
        self.other_organizer.profile.save()
        self.admin = get_user_model().objects.create_user(username='dashboardadmin', password='StrongPass123!')
        self.admin.profile.role = UserRole.ADMIN
        self.admin.profile.save()

        self.organizer_event = Event.objects.create(
            event_name='Organizer Dashboard Event', event_type=Event.EventType.CONFERENCE,
            venue='Hall A', event_date='2026-10-01', start_time='09:00:00',
            end_time='12:00:00', duration=3, expected_attendees=100,
            organizer=self.organizer, status=Event.Status.COMPLETED,
        )
        self.other_event = Event.objects.create(
            event_name='Other Organizer Event', event_type=Event.EventType.FESTIVAL,
            venue='Hall B', event_date='2026-10-02', start_time='09:00:00',
            end_time='12:00:00', duration=3, expected_attendees=200,
            organizer=self.other_organizer, status=Event.Status.SCHEDULED,
        )
        Attendance.objects.create(event=self.organizer_event, attendee_name='A', email='a@example.com')
        Prediction.objects.create(
            event=self.organizer_event, predicted_attendance=90, predicted_food_waste=4,
            predicted_plastic_waste=2, predicted_paper_waste=1, predicted_material_waste=3,
            total_predicted_waste=10, risk_level='High', model_version='test-model',
        )
        WasteRecord.objects.create(
            event=self.organizer_event, actual_attendance=85, food_waste=2,
            leftover_food=1, plastic_waste=1, paper_waste=1,
            glass_waste=1, metal_waste=1, decoration_waste=1, other_waste=1,
        )
        checklist = SustainabilityChecklist.objects.create(event=self.organizer_event)
        ChecklistItem.objects.create(checklist=checklist, question='Waste sorted', category='Waste Segregation', response='Yes', score=100)

    def test_organizer_dashboard_only_aggregates_own_events(self):
        self.client.force_login(self.organizer)

        response = self.client.get('/accounts/dashboard/organizer/')

        self.assertEqual(response.status_code, 200)
        dashboard = response.context['dashboard']
        self.assertEqual(dashboard['total_events'], 1)
        self.assertEqual(dashboard['completed_events'], 1)
        self.assertEqual(dashboard['total_attendees'], 1)
        self.assertEqual(dashboard['predicted_waste'], 10)
        self.assertEqual(dashboard['actual_waste'], 9)
        self.assertEqual(dashboard['average_sustainability_score'], 100)
        self.assertEqual(dashboard['high_risk_events'], 1)
        self.assertEqual(dashboard['charts']['event_type_waste']['labels'], ['Conference'])

    def test_admin_dashboard_aggregates_all_organizers(self):
        self.client.force_login(self.admin)

        response = self.client.get('/accounts/dashboard/admin/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dashboard']['total_events'], 2)
        self.assertEqual(response.context['dashboard']['charts']['event_type_waste']['labels'], ['Conference', 'Festival'])


class VendorManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='vendororganizer',
            email='vendororganizer@example.com',
            password='StrongPass123!',
        )
        self.event = Event.objects.create(
            event_name='Eco Summit',
            event_type=Event.EventType.CONFERENCE,
            venue='Conference Center',
            event_date='2026-11-12',
            start_time='09:00:00',
            end_time='17:00:00',
            duration=8,
            expected_attendees=500,
            organizer=self.user,
        )

    def test_vendor_score_calculation(self):
        vendor = Vendor.objects.create(
            event=self.event,
            vendor_name='Green Supply Co.',
            vendor_type=Vendor.VendorType.FOOD,
            contact_person='Alice',
            phone='123456789',
            email='alice@example.com',
            address='Somewhere',
            sustainability_rating=88,
            is_eco_friendly=True,
        )
        checklist = VendorChecklist.objects.create(
            vendor=vendor,
            avoids_single_use_plastic='Yes',
            uses_reusable_containers='Yes',
            provides_waste_segmentation='Partially',
            uses_eco_friendly_materials='Yes',
            minimizes_packaging='No',
            uses_recyclable_materials='Partially',
            has_waste_management_practices='Yes',
        )

        self.assertEqual(checklist.sustainability_score, 71.43)
        self.assertTrue(vendor.is_eco_friendly)


class SustainabilityChecklistTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='sustainorganizer',
            email='sustainorganizer@example.com',
            password='StrongPass123!',
        )
        self.event = Event.objects.create(
            event_name='Sustainable Fair',
            event_type=Event.EventType.EXHIBITION,
            venue='Green Hall',
            event_date='2026-12-15',
            start_time='10:00:00',
            end_time='18:00:00',
            duration=8,
            expected_attendees=250,
            organizer=self.user,
        )

    def test_checklist_score_and_category_summary(self):
        checklist = SustainabilityChecklist.objects.create(event=self.event)
        items = [
            ChecklistItem.objects.create(checklist=checklist, question='Food waste is minimized', category='Food Management', response='Yes', score=100),
            ChecklistItem.objects.create(checklist=checklist, question='Single-use plastic is avoided', category='Plastic Reduction', response='Partially', score=50),
            ChecklistItem.objects.create(checklist=checklist, question='Paper usage is reduced', category='Paper Reduction', response='Yes', score=100),
            ChecklistItem.objects.create(checklist=checklist, question='Waste is segregated properly', category='Waste Segregation', response='No', score=0),
            ChecklistItem.objects.create(checklist=checklist, question='Recycling is practiced', category='Recycling', response='Yes', score=100),
            ChecklistItem.objects.create(checklist=checklist, question='Energy use is monitored', category='Energy Usage', response='Partially', score=50),
            ChecklistItem.objects.create(checklist=checklist, question='Transportation is optimized', category='Transportation', response='Yes', score=100),
            ChecklistItem.objects.create(checklist=checklist, question='Eco-friendly materials are preferred', category='Eco-friendly Materials', response='Yes', score=100),
            ChecklistItem.objects.create(checklist=checklist, question='Leftovers are managed sustainably', category='Leftover Food Management', response='No', score=0),
        ]

        self.assertEqual(checklist.overall_score, 66.67)
        self.assertEqual(checklist.category_summary['Food Management'], 100)
        self.assertEqual(checklist.category_summary['Plastic Reduction'], 50)
        self.assertEqual(checklist.category_summary['Waste Segregation'], 0)
        self.assertEqual(checklist.percent_complete, 100)
        self.assertEqual(len(items), 9)
