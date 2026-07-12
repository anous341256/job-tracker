from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import AITask
from .providers import ProviderAuthError, ProviderError, ProviderSchemaError
from .services import run_task, save_match_analysis


@shared_task(bind=True, max_retries=2)
def execute_ai_task(self, task_id):
    task = AITask.objects.select_related('user', 'job__company', 'resume').get(pk=task_id)
    task.status = AITask.Status.RUNNING; task.started_at = task.started_at or timezone.now(); task.retry_count = self.request.retries; task.error_type = ''; task.error_message = ''
    task.save(update_fields=('status', 'started_at', 'retry_count', 'error_type', 'error_message'))
    try:
        response = run_task(task)
        task.result = response.data; task.input_tokens = response.input_tokens; task.output_tokens = response.output_tokens; task.status = AITask.Status.SUCCEEDED; task.finished_at = timezone.now()
        task.save(update_fields=('result', 'input_tokens', 'output_tokens', 'status', 'finished_at'))
        if task.task_type == AITask.Type.JOB_MATCH: save_match_analysis(task)
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


@shared_task
def cleanup_ai_tasks():
    stale_before = timezone.now() - timezone.timedelta(minutes=settings.AI_TASK_STALE_MINUTES)
    AITask.objects.filter(status=AITask.Status.RUNNING, started_at__lt=stale_before).update(status=AITask.Status.FAILED, error_type='StaleTask', error_message='任务执行超时，请重新运行。', finished_at=timezone.now())
    AITask.objects.filter(status=AITask.Status.FAILED, finished_at__lt=timezone.now() - timezone.timedelta(days=30)).delete()
