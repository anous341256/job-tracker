from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Company, JobPosition
from .forms import JobPositionForm


class CompanyAndJobPositionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='alice', password='test-pass')

    def test_company_name_is_unique_per_user(self):
        Company.objects.create(user=self.user, name='Example')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(user=self.user, name='Example')

    def test_same_company_name_is_allowed_for_different_users(self):
        other_user = get_user_model().objects.create_user(username='bob', password='test-pass')
        Company.objects.create(user=self.user, name='Example')
        Company.objects.create(user=other_user, name='Example')

        self.assertEqual(Company.objects.filter(name='Example').count(), 2)

    def test_salary_minimum_cannot_exceed_maximum(self):
        company = Company.objects.create(user=self.user, name='Example')
        job = JobPosition(
            company=company,
            title='Python Developer',
            salary_min=Decimal('6000000'),
            salary_max=Decimal('5000000'),
        )

        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_company_detail_hides_other_users_data(self):
        other_user = get_user_model().objects.create_user(username='bob', password='test-pass')
        company = Company.objects.create(user=other_user, name='Private')
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(reverse('companies:detail', args=[company.pk])).status_code, 404)

    def test_other_category_requires_custom_value(self):
        company = Company.objects.create(user=self.user, name='Example')
        form = JobPositionForm(data={
            'company': company.pk,
            'title': 'Researcher',
            'category': JobPosition.Category.OTHER,
            'category_other': '',
            'status': JobPosition.Status.OPEN,
            'work_mode': JobPosition.WorkMode.UNKNOWN,
            'employment_type': JobPosition.EmploymentType.FULL_TIME,
            'salary_currency': 'JPY',
            'salary_period': JobPosition.SalaryPeriod.YEARLY,
        }, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('category_other', form.errors)

    def test_all_job_dates_use_date_pickers(self):
        form = JobPositionForm(user=self.user)

        self.assertEqual(form.fields['application_deadline'].widget.input_type, 'date')
        self.assertEqual(form.fields['published_at'].widget.input_type, 'date')

    def test_company_page_preselects_company_when_adding_job(self):
        company = Company.objects.create(user=self.user, name='Example')
        self.client.force_login(self.user)

        response = self.client.get(reverse('companies:job-create'), {'company': company.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.context['form'].initial['company']), str(company.pk))

    def test_empty_company_urls_render_as_missing_not_links(self):
        company = Company.objects.create(user=self.user, name='Test')
        self.client.force_login(self.user)

        response = self.client.get(reverse('companies:detail', args=[company.pk]))

        self.assertContains(response, '尚未填写', count=3)
        self.assertNotContains(response, 'atom.com')

    def test_compound_create_accepts_company_name_only(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('companies:create'), {
            'name': 'Minimal Corp',
            'status': Company.Status.RESEARCHING,
            'priority': Company.Priority.MEDIUM,
            'jobs-TOTAL_FORMS': '0', 'jobs-INITIAL_FORMS': '0', 'jobs-MIN_NUM_FORMS': '0', 'jobs-MAX_NUM_FORMS': '1000',
            'schedules-TOTAL_FORMS': '0', 'schedules-INITIAL_FORMS': '0', 'schedules-MIN_NUM_FORMS': '0', 'schedules-MAX_NUM_FORMS': '1000',
            'todos-TOTAL_FORMS': '0', 'todos-INITIAL_FORMS': '0', 'todos-MIN_NUM_FORMS': '0', 'todos-MAX_NUM_FORMS': '1000',
        })
        company = Company.objects.get(name='Minimal Corp')
        self.assertRedirects(response, f'/dashboard/#company-{company.pk}')

    def test_compound_create_ignores_rendered_blank_child_defaults(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('companies:create'), {
            'name': 'Defaults Only Corp',
            'status': Company.Status.RESEARCHING,
            'priority': Company.Priority.MEDIUM,
            'jobs-TOTAL_FORMS': '1', 'jobs-INITIAL_FORMS': '0', 'jobs-MIN_NUM_FORMS': '0', 'jobs-MAX_NUM_FORMS': '1000',
            'jobs-0-title': '', 'jobs-0-category': JobPosition.Category.TECHNICAL,
            'schedules-TOTAL_FORMS': '1', 'schedules-INITIAL_FORMS': '0', 'schedules-MIN_NUM_FORMS': '0', 'schedules-MAX_NUM_FORMS': '1000',
            'schedules-0-title': '', 'schedules-0-event_type': 'other',
            'todos-TOTAL_FORMS': '1', 'todos-INITIAL_FORMS': '0', 'todos-MIN_NUM_FORMS': '0', 'todos-MAX_NUM_FORMS': '1000',
            'todos-0-title': '', 'todos-0-priority': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        company = Company.objects.get(name='Defaults Only Corp')
        self.assertFalse(company.job_positions.exists())
        self.assertFalse(company.calendar_events.exists())
        self.assertFalse(company.todo_items.exists())

    def test_compound_create_saves_multiple_children_atomically(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('companies:create'), {
            'name': 'Action Corp', 'status': 'researching', 'priority': 'high',
            'jobs-TOTAL_FORMS': '2', 'jobs-INITIAL_FORMS': '0', 'jobs-MIN_NUM_FORMS': '0', 'jobs-MAX_NUM_FORMS': '1000',
            'jobs-0-title': 'Engineer', 'jobs-0-category': 'technical',
            'jobs-1-title': 'Consultant', 'jobs-1-category': 'consulting',
            'schedules-TOTAL_FORMS': '1', 'schedules-INITIAL_FORMS': '0', 'schedules-MIN_NUM_FORMS': '0', 'schedules-MAX_NUM_FORMS': '1000',
            'schedules-0-title': '说明会', 'schedules-0-event_type': 'briefing',
            'schedules-0-starts_at': '2026-08-20T10:00', 'schedules-0-job_index': '0',
            'todos-TOTAL_FORMS': '2', 'todos-INITIAL_FORMS': '0', 'todos-MIN_NUM_FORMS': '0', 'todos-MAX_NUM_FORMS': '1000',
            'todos-0-title': '准备 ES', 'todos-0-priority': 'high', 'todos-0-job_index': '0',
            'todos-1-title': '调查企业', 'todos-1-priority': 'medium', 'todos-1-job_index': '1',
        })
        self.assertEqual(response.status_code, 302)
        company = Company.objects.get(name='Action Corp')
        self.assertEqual(company.job_positions.count(), 2)
        self.assertEqual(company.calendar_events.count(), 1)
        self.assertEqual(company.todo_items.count(), 2)
        self.assertEqual(company.calendar_events.get().job_position.title, 'Engineer')

    def test_compound_create_rolls_back_when_child_is_invalid(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('companies:create'), {
            'name': 'Rollback Corp', 'status': 'researching', 'priority': 'medium',
            'jobs-TOTAL_FORMS': '0', 'jobs-INITIAL_FORMS': '0', 'jobs-MIN_NUM_FORMS': '0', 'jobs-MAX_NUM_FORMS': '1000',
            'schedules-TOTAL_FORMS': '1', 'schedules-INITIAL_FORMS': '0', 'schedules-MIN_NUM_FORMS': '0', 'schedules-MAX_NUM_FORMS': '1000',
            'schedules-0-title': '时间未填', 'schedules-0-event_type': 'other',
            'todos-TOTAL_FORMS': '0', 'todos-INITIAL_FORMS': '0', 'todos-MIN_NUM_FORMS': '0', 'todos-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Company.objects.filter(name='Rollback Corp').exists())

    def test_reorder_pinned_rejects_other_users_company(self):
        own = Company.objects.create(user=self.user, name='Own', pinned_order=1)
        other_user = get_user_model().objects.create_user(username='bob', password='test-pass')
        other = Company.objects.create(user=other_user, name='Other', pinned_order=1)
        self.client.force_login(self.user)
        response = self.client.post(reverse('companies:reorder-pinned'), {'company_ids': [own.pk, other.pk]})
        self.assertEqual(response.status_code, 400)
