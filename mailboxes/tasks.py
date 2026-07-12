from celery import shared_task
from .models import EmailAccount
from .services import sync_account

@shared_task
def sync_all_accounts():
    for account in EmailAccount.objects.filter(status=EmailAccount.Status.ACTIVE):
        try: sync_account(account)
        except Exception as exc:
            account.status = EmailAccount.Status.ERROR; account.error_message = str(exc)[:1000]; account.save(update_fields=('status', 'error_message', 'updated_at'))
