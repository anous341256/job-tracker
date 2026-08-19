from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from ai_assistant.models import AISettings
from ai_assistant.services import create_email_schedule_task
from mailboxes.models import SyncedEmail
from mailboxes.services import _looks_like_schedule_email


class Command(BaseCommand):
    help = (
        'Queue bounded AI schedule extraction for already-synced emails. '
        'This only creates review tasks; it never approves or changes Outlook.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--provider', choices=('ollama', 'openai'))
        parser.add_argument('--all', action='store_true', help='Include emails without schedule signals')

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(pk=options['user_id']).first()
        if not user:
            raise CommandError('User not found.')
        limit = max(1, min(options['limit'], 20))
        settings_obj, _ = AISettings.objects.get_or_create(user=user)
        provider = options.get('provider') or settings_obj.default_provider
        emails = SyncedEmail.objects.filter(account__user=user).order_by('-received_at')
        queued = 0
        considered = 0
        for email in emails:
            if considered >= limit:
                break
            if not options['all'] and not _looks_like_schedule_email(email):
                continue
            considered += 1
            task, created = create_email_schedule_task(user=user, email=email, provider=provider)
            queued += int(created)
            self.stdout.write(f'{email.pk}\t{task.pk}\t{task.status}\t{email.subject[:80]}')
        self.stdout.write(self.style.SUCCESS(f'Considered {considered}; queued {queued} schedule analysis task(s).'))
