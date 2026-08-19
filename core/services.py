from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from applications.models import Application, Interview
from applications.services import (
    PIPELINE_STAGE_LABELS,
    PIPELINE_STAGE_RANK,
    change_job_pipeline,
    change_status,
    pipeline_stage,
)
from companies.models import Company, JobPosition

from .models import CalendarEvent, TodoItem


@dataclass
class ActionEvent:
    kind: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    color: str
    url: str
    job_title: str = ''
    all_day: bool = False
    overdue: bool = False

    @property
    def duration_minutes(self):
        if self.all_day or not self.ends_at:
            return None
        return max(1, int((self.ends_at - self.starts_at).total_seconds() / 60))


@dataclass(frozen=True)
class TimedBusyInterval:
    kind: str
    title: str
    starts_at: datetime
    ends_at: datetime
    url: str
    color: str

    @property
    def duration_minutes(self):
        return max(1, int((self.ends_at - self.starts_at).total_seconds() / 60))


def user_calendar_timezone(user):
    """Return a safe ZoneInfo for calendar calculations."""
    profile = getattr(user, 'profile', None)
    name = getattr(profile, 'timezone', '') or settings.TIME_ZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        try:
            return ZoneInfo(settings.TIME_ZONE)
        except ZoneInfoNotFoundError:
            return ZoneInfo('UTC')


def timed_busy_intervals(user, start, end):
    """Return the timed records that genuinely occupy calendar time."""
    intervals = []
    interviews = Interview.objects.filter(
        application__user=user,
        scheduled_at__lt=end,
    ).exclude(status=Interview.Status.CANCELLED)
    for interview in interviews:
        interval_end = interview.scheduled_at + timedelta(minutes=interview.duration_minutes or 60)
        if interval_end <= start:
            continue
        intervals.append(TimedBusyInterval(
            kind='interview',
            title=f'面试：{interview.title}',
            starts_at=interview.scheduled_at,
            ends_at=interval_end,
            url=f'/applications/{interview.application_id}/',
            color='#2f67d8',
        ))

    calendar_events = CalendarEvent.objects.filter(
        user=user,
        starts_at__lt=end,
    ).filter(
        Q(ends_at__gt=start)
        | Q(ends_at__isnull=True, starts_at__gte=start - timedelta(hours=1))
    )
    for event in calendar_events:
        interval_end = event.ends_at or event.starts_at + timedelta(minutes=60)
        if interval_end <= start:
            continue
        intervals.append(TimedBusyInterval(
            kind=event.event_type,
            title=f'{event.get_event_type_display()}：{event.title}',
            starts_at=event.starts_at,
            ends_at=interval_end,
            url=f'/calendar/events/{event.pk}/edit/',
            color=event_color(event.event_type),
        ))
    return sorted(intervals, key=lambda item: (item.starts_at, item.ends_at))


def workday_free_slots(user, start, end, *, minimum_minutes=30):
    """Calculate weekday gaps inside 10:00–19:00 in the user's timezone."""
    local_tz = user_calendar_timezone(user)
    local_start = start.astimezone(local_tz)
    local_end = end.astimezone(local_tz)
    busy = timed_busy_intervals(user, start, end)
    free_slots = []
    day = local_start.date()
    while True:
        work_start = datetime.combine(day, time(10), tzinfo=local_tz)
        if work_start >= local_end:
            break
        work_end = datetime.combine(day, time(19), tzinfo=local_tz)
        if day.weekday() < 5:
            window_start = max(work_start, local_start)
            window_end = min(work_end, local_end)
            if window_start < window_end:
                occupied = []
                for interval in busy:
                    interval_start = interval.starts_at.astimezone(local_tz)
                    interval_end = interval.ends_at.astimezone(local_tz)
                    clipped_start = max(interval_start, window_start)
                    clipped_end = min(interval_end, window_end)
                    if clipped_start < clipped_end:
                        occupied.append((clipped_start, clipped_end))
                occupied.sort()
                merged = []
                for occupied_start, occupied_end in occupied:
                    if merged and occupied_start <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], occupied_end))
                    else:
                        merged.append((occupied_start, occupied_end))
                cursor = window_start
                for occupied_start, occupied_end in merged:
                    if (occupied_start - cursor).total_seconds() >= minimum_minutes * 60:
                        free_slots.append((cursor, occupied_start))
                    cursor = max(cursor, occupied_end)
                if (window_end - cursor).total_seconds() >= minimum_minutes * 60:
                    free_slots.append((cursor, window_end))
        day += timedelta(days=1)
    return free_slots


def _aware_date(value, *, end_of_day=False):
    point = time(23, 59) if end_of_day else time.min
    return timezone.make_aware(datetime.combine(value, point), timezone.get_current_timezone())


def build_company_cards(user):
    """Return action-center cards with a fixed number of database queries."""
    active_apps = Application.objects.filter(user=user).prefetch_related(
        Prefetch(
            'interviews',
            queryset=Interview.objects.filter(
                status__in=(Interview.Status.SCHEDULED, Interview.Status.RESCHEDULED),
            ).order_by('scheduled_at'),
            to_attr='dashboard_interviews',
        )
    ).order_by('-created_at', '-pk')
    jobs = JobPosition.objects.prefetch_related(
        Prefetch('applications', queryset=active_apps, to_attr='dashboard_applications'),
    ).order_by('application_deadline', '-updated_at')
    companies = list(
        Company.objects.filter(user=user, archived_at__isnull=True)
        .prefetch_related(
            Prefetch('job_positions', queryset=jobs, to_attr='dashboard_jobs'),
            Prefetch('calendar_events', queryset=CalendarEvent.objects.order_by('starts_at'), to_attr='dashboard_events'),
            Prefetch(
                'todo_items',
                queryset=TodoItem.objects.select_related('job_position', 'application').order_by('status', 'due_at', '-updated_at'),
                to_attr='dashboard_todos',
            ),
        )
    )
    now = timezone.now()
    cards = []
    for company in companies:
        events = []
        for job in company.dashboard_jobs:
            latest_app = job.dashboard_applications[0] if job.dashboard_applications else None
            job.pipeline_application = latest_app
            job.pipeline_stage = pipeline_stage(latest_app)
            job.pipeline_stage_label = PIPELINE_STAGE_LABELS[job.pipeline_stage]
            job.pipeline_outcome_label = latest_app.get_status_display() if latest_app and job.pipeline_stage == 'ended' else ''
            if job.application_deadline and job.status in {
                JobPosition.Status.DRAFT, JobPosition.Status.OPEN, JobPosition.Status.UNKNOWN,
            } and job.pipeline_stage != 'ended':
                start = _aware_date(job.application_deadline, end_of_day=True)
                events.append(ActionEvent(
                    'deadline', f'{job.title} · 职位截止', start, None, '#d75b4e',
                    f'/jobs/{job.pk}/', job.title, True, start < now,
                ))
            if latest_app:
                if latest_app.next_action_date and job.pipeline_stage != 'ended':
                    start = _aware_date(latest_app.next_action_date)
                    events.append(ActionEvent(
                        'followup', latest_app.next_action or f'{job.title} · 跟进', start, None,
                        '#c89435', f'/applications/{latest_app.pk}/', job.title, True, start < now,
                    ))
                for interview in getattr(latest_app, 'dashboard_interviews', []):
                    end = interview.scheduled_at + timedelta(minutes=interview.duration_minutes or 60)
                    events.append(ActionEvent(
                        'interview', interview.title, interview.scheduled_at, end, '#3e68c7',
                        f'/applications/{latest_app.pk}/', job.title, False, end < now,
                    ))
        for event in company.dashboard_events:
            events.append(ActionEvent(
                event.event_type, event.title, event.starts_at, event.ends_at, event_color(event.event_type),
                f'/calendar/events/{event.pk}/edit/?next=/dashboard/%23company-{company.pk}',
                event.job_position.title if event.job_position_id else '', False,
                (event.ends_at or event.starts_at) < now,
            ))
        events.sort(key=lambda event: (
            0 if event.overdue else 1,
            -event.starts_at.timestamp() if event.overdue else event.starts_at.timestamp(),
        ))
        open_todos = [todo for todo in company.dashboard_todos if todo.status != TodoItem.Status.DONE]
        next_dates = [event.starts_at for event in events if event.starts_at >= now]
        next_dates.extend(todo.due_at for todo in open_todos if todo.due_at)
        next_action_at = min(next_dates) if next_dates else None
        has_overdue = any(event.overdue for event in events) or any(todo.due_at and todo.due_at < now for todo in open_todos)
        active_stages = [job.pipeline_stage for job in company.dashboard_jobs if job.pipeline_stage != 'ended']
        if active_stages:
            company_stage = max(active_stages, key=lambda value: PIPELINE_STAGE_RANK[value])
        elif company.dashboard_jobs:
            company_stage = 'ended'
        else:
            company_stage = 'unapplied'
        cards.append({
            'company': company,
            'jobs': company.dashboard_jobs,
            'stage': company_stage,
            'stage_label': PIPELINE_STAGE_LABELS[company_stage],
            'events': events,
            'visible_events': events[:3],
            'todos': open_todos,
            'visible_todos': open_todos[:5],
            'next_action_at': next_action_at,
            'has_overdue': has_overdue,
            'collapsed': bool(company.dashboard_jobs) and all(job.pipeline_stage == 'ended' for job in company.dashboard_jobs) and not open_todos and not next_dates,
        })
    priority_rank = {
        Company.Priority.DREAM: 0,
        Company.Priority.HIGH: 1,
        Company.Priority.MEDIUM: 2,
        Company.Priority.LOW: 3,
    }
    distant = timezone.now() + timedelta(days=36500)
    cards.sort(key=lambda card: (
        0 if card['company'].pinned_order is not None else 1,
        card['company'].pinned_order if card['company'].pinned_order is not None else 0,
        0 if card['has_overdue'] else 1,
        card['next_action_at'] or distant,
        priority_rank.get(card['company'].priority, 9),
        -card['company'].updated_at.timestamp(),
    ))
    return cards


def event_color(event_type):
    return {
        CalendarEvent.Type.INTERVIEW: '#3e68c7',
        CalendarEvent.Type.ES_DEADLINE: '#d75b4e',
        CalendarEvent.Type.ASSESSMENT: '#8a63b8',
        CalendarEvent.Type.BRIEFING: '#3f8a76',
        CalendarEvent.Type.CALL: '#337f9d',
    }.get(event_type, '#6d7787')


@transaction.atomic
def create_scheduled_action(*, user, company, title, event_type, starts_at, ends_at=None,
                            job_position=None, location='', meeting_url='', notes='', participants=None,
                            source_email=None, contact=None, application=None):
    if company.user_id != user.id:
        raise ValidationError('不能为其他用户的公司创建日程。')
    if job_position and job_position.company_id != company.id:
        raise ValidationError('关联职位必须属于所选公司。')
    if application and (application.user_id != user.id or application.job_position.company_id != company.id):
        raise ValidationError('关联投递必须属于所选公司。')
    if ends_at and ends_at <= starts_at:
        raise ValidationError('结束时间必须晚于开始时间。')
    if event_type == CalendarEvent.Type.INTERVIEW and job_position:
        if application:
            application = change_status(
                application=application,
                status=Application.Status.INTERVIEWING,
                user=user,
                note='创建面试日程时自动推进。',
            )
        else:
            application = change_job_pipeline(
                job=job_position,
                user=user,
                stage='interviewing',
                note='创建面试日程时自动推进。',
            )
        next_round = (application.interviews.order_by('-round_number').values_list('round_number', flat=True).first() or 0) + 1
        duration = int((ends_at - starts_at).total_seconds() / 60) if ends_at else None
        return Interview.objects.create(
            application=application,
            round_number=next_round,
            title=title,
            interview_type=Interview.Type.VIDEO if meeting_url else Interview.Type.ONSITE,
            scheduled_at=starts_at,
            duration_minutes=duration,
            meeting_url=meeting_url,
            location=location,
            interviewer_names='、'.join(participants or []),
            preparation_notes=notes,
        )
    return CalendarEvent.objects.create(
        user=user,
        company=company,
        job_position=job_position,
        title=title,
        event_type=event_type,
        starts_at=starts_at,
        ends_at=ends_at,
        location=location,
        meeting_url=meeting_url,
        notes=notes,
        participants=participants or [],
        source_email=source_email,
        contact=contact,
        application=application,
    )
