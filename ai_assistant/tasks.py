from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import AITask
from .providers import ProviderAuthError, ProviderError, ProviderSchemaError
from .services import run_task, save_match_analysis, save_email_schedule_candidates


@shared_task(bind=True, max_retries=2)
def execute_ai_task(self, task_id):
    task = AITask.objects.select_related('user', 'job__company', 'resume', 'email__company', 'email__application', 'email__contact').get(pk=task_id)
    if task.provider == 'ollama' and getattr(settings, 'HOST_AGENT_ENABLED', False):
        from core.models import HostAgentCommand
        HostAgentCommand.objects.get_or_create(user=task.user, ai_task=task, defaults={'command_type': HostAgentCommand.Type.OLLAMA})
        task.status = AITask.Status.WAITING_HOST
        task.save(update_fields=('status',))
        return
    task.status = AITask.Status.RUNNING; task.started_at = task.started_at or timezone.now(); task.retry_count = self.request.retries; task.error_type = ''; task.error_message = ''
    task.save(update_fields=('status', 'started_at', 'retry_count', 'error_type', 'error_message'))
    try:
        response = run_task(task)
        task.result = response.data; task.input_tokens = response.input_tokens; task.output_tokens = response.output_tokens; task.status = AITask.Status.SUCCEEDED; task.finished_at = timezone.now()
        task.save(update_fields=('result', 'input_tokens', 'output_tokens', 'status', 'finished_at'))
        if task.task_type == AITask.Type.JOB_MATCH: save_match_analysis(task)
        if task.task_type in (AITask.Type.EMAIL_SCHEDULE, AITask.Type.EMAIL_CHAT):
            save_email_schedule_candidates(task)
    except ProviderSchemaError as exc:
        if self.request.retries < 1: raise self.retry(exc=exc, countdown=2)
        _fail(task, exc)
    except ProviderAuthError as exc: _fail(task, exc)
    except ProviderError as exc:
        if self.request.retries < self.max_retries: raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1))
        _fail(task, exc)
    except Exception as exc: _fail(task, exc)


def _fail(task, exc):
    task.status = AITask.Status.FAILED; task.error_type = exc.__class__.__name__; task.error_message = str(exc)[:1000]; task.finished_at = timezone.now(); task.save(update_fields=('status', 'error_type', 'error_message', 'finished_at'))


def complete_host_agent_task(task, data):
    if task.status not in (AITask.Status.WAITING_HOST, AITask.Status.RUNNING):
        raise ValueError('AI task is not waiting for the host agent.')
    from .schemas import EmailAssistantResult, EmailScheduleResult, JDParseResult, JobMatchResult
    schema = {
        AITask.Type.JD_PARSE: JDParseResult,
        AITask.Type.JOB_MATCH: JobMatchResult,
        AITask.Type.EMAIL_SCHEDULE: EmailScheduleResult,
        AITask.Type.EMAIL_CHAT: EmailAssistantResult,
    }[task.task_type]
    task.result = schema.model_validate(data.get('result', {})).model_dump(mode='json')
    task.input_tokens = int(data.get('input_tokens', 0) or 0)
    task.output_tokens = int(data.get('output_tokens', 0) or 0)
    task.status = AITask.Status.SUCCEEDED
    task.started_at = task.started_at or timezone.now()
    task.finished_at = timezone.now()
    task.save(update_fields=('result', 'input_tokens', 'output_tokens', 'status', 'started_at', 'finished_at'))
    if task.task_type == AITask.Type.JOB_MATCH:
        save_match_analysis(task)
    if task.task_type in (AITask.Type.EMAIL_SCHEDULE, AITask.Type.EMAIL_CHAT):
        save_email_schedule_candidates(task)
    return {'task_id': str(task.pk)}


def fail_host_agent_task(task, message):
    task.status = AITask.Status.FAILED
    task.error_type = 'HostAgentError'
    task.error_message = str(message)[:1000]
    task.finished_at = timezone.now()
    task.save(update_fields=('status', 'error_type', 'error_message', 'finished_at'))


@shared_task
def cleanup_ai_tasks():
    stale_before = timezone.now() - timezone.timedelta(minutes=settings.AI_TASK_STALE_MINUTES)
    AITask.objects.filter(status=AITask.Status.RUNNING, started_at__lt=stale_before).update(status=AITask.Status.FAILED, error_type='StaleTask', error_message='任务执行超时，请重新运行。', finished_at=timezone.now())
    AITask.objects.filter(status=AITask.Status.FAILED, finished_at__lt=timezone.now() - timezone.timedelta(days=30)).delete()
