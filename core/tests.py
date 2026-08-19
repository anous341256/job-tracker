import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, ApplicationStatusLog, Interview
from companies.models import Company, JobPosition
from accounts.models import Profile

from mailboxes.models import EmailAccount, SyncedEmail

from .models import CalendarEvent, HostAgentCommand, TodoItem
from .tasks import queue_periodic_outlook_syncs


class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('alice', password='pass')
        self.other = get_user_model().objects.create_user('bob', password='pass')

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 302)

    def test_dashboard_is_company_scoped_and_action_first(self):
        Company.objects.create(user=self.other, name='Private company')
        company = Company.objects.create(user=self.user, name='Visible company')
        JobPosition.objects.create(company=company, title='Engineer')
        self.client.force_login(self.user)

        response = self.client.get(reverse('core:dashboard'))

        self.assertContains(response, '求职行动中心')
        self.assertContains(response, 'Visible company')
        self.assertContains(response, 'Engineer')
        self.assertNotContains(response, 'Private company')
        self.assertNotContains(response, 'monthly-data')

    def test_dashboard_query_count_does_not_grow_per_company(self):
        self.client.force_login(self.user)
        company = Company.objects.create(user=self.user, name='One')
        job = JobPosition.objects.create(company=company, title='First role')
        application = Application.objects.create(user=self.user, job_position=job)
        TodoItem.objects.create(user=self.user, company=company, title='First task')
        CalendarEvent.objects.create(user=self.user, company=company, title='First event', starts_at=timezone.now())
        Interview.objects.create(application=application, round_number=1, title='First interview', scheduled_at=timezone.now())
        with CaptureQueriesContext(connection) as first:
            self.client.get(reverse('core:dashboard'))
        for index in range(6):
            company = Company.objects.create(user=self.user, name=f'Company {index}')
            job = JobPosition.objects.create(company=company, title=f'Role {index}')
            application = Application.objects.create(user=self.user, job_position=job)
            TodoItem.objects.create(user=self.user, company=company, title=f'Task {index}')
            CalendarEvent.objects.create(user=self.user, company=company, title=f'Event {index}', starts_at=timezone.now())
            Interview.objects.create(application=application, round_number=1, title='Interview', scheduled_at=timezone.now())
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse('core:dashboard'))
        self.assertLessEqual(len(many), len(first) + 1)

    def test_todo_requires_owned_company_and_can_be_completed(self):
        company = Company.objects.create(user=self.user, name='Example')
        other_company = Company.objects.create(user=self.other, name='Other')
        self.client.force_login(self.user)
        invalid = self.client.post(reverse('core:todo-create'), {
            'company': other_company.pk, 'title': 'Private', 'status': 'todo', 'priority': 'medium',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(TodoItem.objects.filter(title='Private').exists())
        response = self.client.post(reverse('core:todo-create'), {
            'company': company.pk, 'title': 'Prepare ES', 'status': 'todo', 'priority': 'high',
        })
        self.assertRedirects(response, reverse('core:dashboard'))
        item = TodoItem.objects.get(title='Prepare ES')
        self.client.post(reverse('core:todo-toggle', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, TodoItem.Status.DONE)

    def test_dashboard_todo_can_complete_and_reopen_with_htmx(self):
        company = Company.objects.create(user=self.user, name='Example')
        item = TodoItem.objects.create(user=self.user, company=company, title='Prepare ES')
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('core:todo-toggle', args=[item.pk]),
            {'card_company_id': company.pk}, HTTP_HX_REQUEST='true',
        )
        self.assertContains(response, 'is-done')
        item.refresh_from_db()
        self.assertEqual(item.status, TodoItem.Status.DONE)
        response = self.client.post(
            reverse('core:todo-toggle', args=[item.pk]),
            {'card_company_id': company.pk}, HTTP_HX_REQUEST='true',
        )
        self.assertNotContains(response, 'is-done')
        item.refresh_from_db()
        self.assertEqual(item.status, TodoItem.Status.TODO)

    def test_interview_schedule_creates_application_and_history(self):
        company = Company.objects.create(user=self.user, name='Example')
        job = JobPosition.objects.create(company=company, title='Engineer')
        self.client.force_login(self.user)
        response = self.client.post(reverse('core:calendar-event-create'), {
            'company': company.pk,
            'job_position': job.pk,
            'title': '一次面试',
            'event_type': CalendarEvent.Type.INTERVIEW,
            'starts_at': '2026-08-18T10:00',
            'ends_at': '2026-08-18T11:00',
            'location': '', 'meeting_url': '', 'notes': '',
        })
        self.assertRedirects(response, reverse('core:dashboard'))
        application = Application.objects.get(job_position=job)
        self.assertEqual(application.status, Application.Status.INTERVIEWING)
        self.assertTrue(ApplicationStatusLog.objects.filter(application=application).exists())
        self.assertTrue(Interview.objects.filter(application=application, title='一次面试').exists())

    def test_job_query_preselects_company_and_job_for_quick_forms(self):
        company = Company.objects.create(user=self.user, name='Example')
        job = JobPosition.objects.create(company=company, title='Engineer')
        self.client.force_login(self.user)
        for route in ('core:todo-create', 'core:calendar-event-create'):
            response = self.client.get(reverse(route), {'job': job.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['form'].fields['company'].initial, company)
            self.assertEqual(response.context['form'].fields['job_position'].initial, job)

    def test_calendar_event_edit_is_user_scoped(self):
        company = Company.objects.create(user=self.user, name='Example')
        event = CalendarEvent.objects.create(user=self.user, company=company, title='Briefing', starts_at=timezone.now())
        other_company = Company.objects.create(user=self.other, name='Other')
        other_event = CalendarEvent.objects.create(user=self.other, company=other_company, title='Private', starts_at=timezone.now())
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('core:calendar-event-edit', args=[other_event.pk])).status_code, 404)
        response = self.client.post(reverse('core:calendar-event-edit', args=[event.pk]), {
            'company': company.pk, 'job_position': '', 'title': 'Updated briefing',
            'event_type': CalendarEvent.Type.BRIEFING,
            'starts_at': '2026-08-18T10:00', 'ends_at': '2026-08-18T11:00',
            'location': '', 'meeting_url': '', 'notes': '',
        })
        self.assertRedirects(response, reverse('calendar'))
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated briefing')


class CalendarFreeSlotTests(TestCase):
    def setUp(self):
        self.tz = ZoneInfo('Asia/Tokyo')
        self.user = get_user_model().objects.create_user('calendar-user', password='pass')
        self.other = get_user_model().objects.create_user('calendar-other', password='pass')
        Profile.objects.create(user=self.user, timezone='Asia/Tokyo')
        Profile.objects.create(user=self.other, timezone='Asia/Tokyo')
        self.company = Company.objects.create(user=self.user, name='Example')
        self.other_company = Company.objects.create(user=self.other, name='Private')
        self.client.force_login(self.user)

    def dt(self, day, hour=0, minute=0):
        return datetime(2026, 8, day, hour, minute, tzinfo=self.tz)

    def get_slots(self, start, end):
        return self.client.get(reverse('core:calendar-free-slots'), {
            'start': start.isoformat(),
            'end': end.isoformat(),
        })

    def test_empty_workday_returns_full_slot_with_japanese_weekday_copy_text(self):
        response = self.get_slots(self.dt(17), self.dt(18))

        self.assertEqual(response.status_code, 200)
        slots = response.json()
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0]['start'], self.dt(17, 10).isoformat())
        self.assertEqual(slots[0]['end'], self.dt(17, 19).isoformat())
        self.assertEqual(slots[0]['display'], 'background')
        self.assertEqual(slots[0]['extendedProps']['dateLabel'], '2026年8月17日（月）')
        self.assertEqual(slots[0]['extendedProps']['copyText'], '2026年8月17日（月） 10:00–19:00')

    def test_overlapping_and_adjacent_events_are_merged(self):
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='A',
            starts_at=self.dt(17, 11), ends_at=self.dt(17, 12),
        )
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='B',
            starts_at=self.dt(17, 11, 30), ends_at=self.dt(17, 13),
        )
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='C',
            starts_at=self.dt(17, 13), ends_at=self.dt(17, 14),
        )

        slots = self.get_slots(self.dt(17), self.dt(18)).json()

        self.assertEqual(
            [slot['extendedProps']['timeLabel'] for slot in slots],
            ['10:00–11:00', '14:00–19:00'],
        )

    def test_boundary_clipping_and_minimum_thirty_minutes(self):
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='Early',
            starts_at=self.dt(17, 9), ends_at=self.dt(17, 10, 30),
        )
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='Short split',
            starts_at=self.dt(17, 11), ends_at=self.dt(17, 11, 40),
        )
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='Late',
            starts_at=self.dt(17, 12), ends_at=self.dt(17, 20),
        )

        slots = self.get_slots(self.dt(17), self.dt(18)).json()

        self.assertEqual(
            [slot['extendedProps']['timeLabel'] for slot in slots],
            ['10:30–11:00'],
        )

    def test_interview_duration_and_default_event_duration_occupy_time(self):
        job = JobPosition.objects.create(company=self.company, title='Engineer')
        application = Application.objects.create(user=self.user, job_position=job)
        Interview.objects.create(
            application=application, round_number=1, title='Interview',
            scheduled_at=self.dt(17, 10), duration_minutes=90,
        )
        Interview.objects.create(
            application=application, round_number=2, title='Cancelled',
            scheduled_at=self.dt(17, 12), duration_minutes=60,
            status=Interview.Status.CANCELLED,
        )
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='No end',
            starts_at=self.dt(17, 14), ends_at=None,
        )
        TodoItem.objects.create(
            user=self.user, company=self.company, title='Does not block',
            due_at=self.dt(17, 13),
        )

        slots = self.get_slots(self.dt(17), self.dt(18)).json()

        self.assertEqual(
            [slot['extendedProps']['timeLabel'] for slot in slots],
            ['11:30–14:00', '15:00–19:00'],
        )

    def test_cross_day_event_is_clipped_per_workday(self):
        CalendarEvent.objects.create(
            user=self.user, company=self.company, title='Overnight',
            starts_at=self.dt(17, 18, 30), ends_at=self.dt(18, 10, 30),
        )

        slots = self.get_slots(self.dt(17), self.dt(19)).json()

        self.assertEqual(
            [slot['extendedProps']['copyText'] for slot in slots],
            [
                '2026年8月17日（月） 10:00–18:30',
                '2026年8月18日（火） 10:30–19:00',
            ],
        )

    def test_weekends_and_other_users_records_do_not_affect_slots(self):
        CalendarEvent.objects.create(
            user=self.other, company=self.other_company, title='Private',
            starts_at=self.dt(17, 10), ends_at=self.dt(17, 19),
        )
        weekday_slots = self.get_slots(self.dt(17), self.dt(18)).json()
        weekend_slots = self.get_slots(self.dt(22), self.dt(24)).json()

        self.assertEqual(len(weekday_slots), 1)
        self.assertEqual(weekday_slots[0]['extendedProps']['timeLabel'], '10:00–19:00')
        self.assertEqual(weekend_slots, [])

    def test_invalid_or_excessive_ranges_are_rejected(self):
        missing = self.client.get(reverse('core:calendar-free-slots'))
        reversed_range = self.get_slots(self.dt(18), self.dt(17))
        excessive = self.get_slots(self.dt(17), self.dt(17) + timedelta(days=63))

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(reversed_range.status_code, 400)
        self.assertEqual(excessive.status_code, 400)

    def test_calendar_page_exposes_list_and_copy_controls(self):
        response = self.client.get(reverse('calendar'))

        self.assertContains(response, '显示空闲时间')
        self.assertContains(response, '空闲时间一览')
        self.assertContains(response, '复制全部')
        self.assertContains(response, '日期按日本曜日标注')


@override_settings(
    HOST_AGENT_ENABLED=True,
    HOST_AGENT_TOKEN='test-host-agent-token',
    HOST_AGENT_TOKEN_FILE='missing-token-file',
    HOST_AGENT_AUTO_SYNC_MINUTES=2,
)
class HostAgentRelayTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('relay-user', password='pass')
        self.account = EmailAccount.objects.create(
            user=self.user,
            provider=EmailAccount.Provider.OUTLOOK_LOCAL,
            email_address='relay@example.com',
        )
        self.headers = {
            'HTTP_AUTHORIZATION': 'Bearer test-host-agent-token',
            'HTTP_X_JOBTRACKER_AGENT': 'windows-test',
            'HTTP_HOST': '127.0.0.1',
        }

    def post_json(self, path, payload, **headers):
        request_headers = dict(self.headers)
        request_headers.update(headers)
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type='application/json',
            **request_headers,
        )

    def test_invalid_token_is_rejected(self):
        response = self.post_json(
            '/internal/host-agent/heartbeat/', {},
            HTTP_AUTHORIZATION='Bearer wrong-token',
        )
        self.assertEqual(response.status_code, 403)

    def test_claim_complete_and_duplicate_completion_are_idempotent(self):
        command = HostAgentCommand.objects.create(
            user=self.user,
            email_account=self.account,
            command_type=HostAgentCommand.Type.OUTLOOK_SYNC,
            payload={'limit': 100, 'days': 30, 'folder': 'Inbox'},
        )
        claimed = self.post_json('/internal/host-agent/claim/', {'agent_id': 'windows-test'})
        self.assertEqual(claimed.json()['command']['id'], command.pk)
        payload = {
            'messages': [{
                'id': 'entry-1', 'thread_id': 'thread-1',
                'sender': 'sender@example.com', 'recipients': ['relay@example.com'],
                'subject': 'Interview', 'body_text': 'Tomorrow at 10:00',
                'folder_name': 'Inbox', 'is_read': False,
                'has_attachments': False, 'received_at': timezone.now().isoformat(),
            }],
        }
        completed = self.post_json(
            f'/internal/host-agent/commands/{command.pk}/complete/', payload,
        )
        self.assertTrue(completed.json()['acknowledged'])
        self.assertEqual(SyncedEmail.objects.filter(account=self.account).count(), 1)
        duplicate = self.post_json(
            f'/internal/host-agent/commands/{command.pk}/complete/', payload,
        )
        self.assertTrue(duplicate.json()['duplicate'])
        self.assertEqual(SyncedEmail.objects.filter(account=self.account).count(), 1)

    def test_late_outlook_page_is_accepted_and_next_page_is_queued(self):
        command = HostAgentCommand.objects.create(
            user=self.user,
            email_account=self.account,
            command_type=HostAgentCommand.Type.OUTLOOK_SYNC,
            status=HostAgentCommand.Status.EXPIRED,
            payload={'limit': 100, 'days': 30, 'folder': 'Inbox'},
        )
        response = self.post_json(
            f'/internal/host-agent/commands/{command.pk}/complete/',
            {
                'messages': [], 'truncated': True,
                'next_before_received_at': timezone.now().isoformat(),
            },
        )
        self.assertTrue(response.json()['acknowledged'])
        self.assertTrue(HostAgentCommand.objects.filter(
            email_account=self.account,
            status=HostAgentCommand.Status.QUEUED,
            payload__has_key='before_received_at',
        ).exists())

    def test_periodic_task_queues_due_account_once(self):
        self.assertEqual(queue_periodic_outlook_syncs(), 1)
        self.assertEqual(queue_periodic_outlook_syncs(), 0)
        command = HostAgentCommand.objects.get(email_account=self.account)
        self.assertEqual(command.payload['limit'], 100)
