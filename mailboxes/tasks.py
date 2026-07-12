from celery import shared_task

from .services import cleanup_stored_emails


@shared_task
def cleanup_email_storage():
    cleanup_stored_emails()
