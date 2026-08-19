"""Authenticated bridge endpoints for the outbound-only Windows host agent."""
import hmac
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import HostAgentCommand, HostAgentHeartbeat


def _token_is_valid(request):
    expected = settings.HOST_AGENT_TOKEN.strip()
    if not expected:
        try:
            expected = Path(settings.HOST_AGENT_TOKEN_FILE).read_text(encoding='utf-8').strip()
        except OSError:
            return False
    provided = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    return bool(expected) and hmac.compare_digest(expected, provided)


def _transport_is_allowed(request):
    """Remote agents must arrive through HTTPS; localhost development may use HTTP."""
    if request.is_secure():
        return True
    if not settings.HOST_AGENT_ALLOW_INSECURE_LOCAL:
        return False
    try:
        source = ipaddress.ip_address(request.META.get('REMOTE_ADDR', ''))
        target = urlsplit(f"//{request.get_host()}").hostname
    except (ValueError, TypeError):
        return False
    return target in {'127.0.0.1', 'localhost', '::1'} and (source.is_loopback or source.is_private)


def host_agent_auth(view):
    def wrapped(request, *args, **kwargs):
        try:
            content_length = int(request.META.get('CONTENT_LENGTH') or 0)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid content length.'}, status=400)
        if content_length > settings.HOST_AGENT_MAX_BODY_BYTES:
            return JsonResponse({'error': 'Host agent payload is too large.'}, status=413)
        if not _transport_is_allowed(request):
            return HttpResponseForbidden('Remote host agent requests require HTTPS.')
        if not _token_is_valid(request):
            return HttpResponseForbidden('Invalid host agent token.')
        return view(request, *args, **kwargs)
    return wrapped


def _payload(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return {}


@csrf_exempt
@require_POST
@host_agent_auth
def heartbeat(request):
    data = _payload(request)
    HostAgentHeartbeat.objects.update_or_create(
        agent_id=data.get('agent_id', 'windows-local')[:100],
        defaults={
            'version': str(data.get('version', ''))[:30],
            'outlook_available': bool(data.get('outlook_available')),
            'ollama_available': bool(data.get('ollama_available')),
            'error_message': str(data.get('error_message', ''))[:1000],
        },
    )
    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
@host_agent_auth
def claim(request):
    with transaction.atomic():
        command = (
            HostAgentCommand.objects.select_for_update()
            .filter(status=HostAgentCommand.Status.QUEUED)
            .select_related('user', 'ai_task__user', 'email_account')
            .first()
        )
        if not command:
            return JsonResponse({'command': None})
        command.status = HostAgentCommand.Status.RUNNING
        command.claimed_at = timezone.now()
        command.save(update_fields=('status', 'claimed_at'))
        data = {'id': command.pk, 'type': command.command_type, 'payload': command.payload}
        if command.command_type == HostAgentCommand.Type.OLLAMA:
            from ai_assistant.services import host_agent_ollama_request
            data['payload'] = host_agent_ollama_request(command.ai_task)
    return JsonResponse({'command': data})


@csrf_exempt
@require_POST
@host_agent_auth
@transaction.atomic
def complete(request, pk):
    command = HostAgentCommand.objects.select_for_update().select_related('ai_task', 'email_account').filter(pk=pk).first()
    if not command:
        return JsonResponse({'error': 'Unknown command.'}, status=404)
    if command.status in {HostAgentCommand.Status.SUCCEEDED, HostAgentCommand.Status.FAILED}:
        return JsonResponse({
            'ok': command.status == HostAgentCommand.Status.SUCCEEDED,
            'acknowledged': True,
            'duplicate': True,
        })
    allowed_statuses = {HostAgentCommand.Status.RUNNING}
    if command.command_type in {HostAgentCommand.Type.OUTLOOK_CONNECT, HostAgentCommand.Type.OUTLOOK_SYNC}:
        # Outlook is the durable source and message IDs are unique. Accepting a
        # late page after a temporary outage is safer than silently losing it.
        allowed_statuses.add(HostAgentCommand.Status.EXPIRED)
    if command.status not in allowed_statuses:
        return JsonResponse({'error': 'Command is not accepting results.'}, status=409)
    data = _payload(request)
    if data.get('error'):
        command.status = HostAgentCommand.Status.FAILED
        command.error_message = str(data['error'])[:1000]
        if command.ai_task_id:
            from ai_assistant.tasks import fail_host_agent_task
            fail_host_agent_task(command.ai_task, command.error_message)
    else:
        try:
            if command.command_type == HostAgentCommand.Type.OUTLOOK_CONNECT:
                from mailboxes.host_agent import register_outlook_account
                result = register_outlook_account(command.user, data)
            elif command.command_type == HostAgentCommand.Type.OUTLOOK_SYNC:
                from mailboxes.host_agent import save_outlook_messages
                result = save_outlook_messages(command.email_account, data.get('messages', []))
                if data.get('truncated') and data.get('next_before_received_at'):
                    next_payload = dict(command.payload)
                    next_payload['before_received_at'] = data['next_before_received_at']
                    HostAgentCommand.objects.create(
                        user=command.user,
                        email_account=command.email_account,
                        command_type=HostAgentCommand.Type.OUTLOOK_SYNC,
                        payload=next_payload,
                    )
                    result['next_page_queued'] = True
            elif command.command_type == HostAgentCommand.Type.OLLAMA:
                from ai_assistant.tasks import complete_host_agent_task
                result = complete_host_agent_task(command.ai_task, data)
            else:
                result = {}
            command.status = HostAgentCommand.Status.SUCCEEDED
            command.result = result
        except Exception as exc:
            command.status = HostAgentCommand.Status.FAILED
            command.error_message = str(exc)[:1000]
        
    command.completed_at = timezone.now()
    command.save(update_fields=('status', 'result', 'error_message', 'completed_at'))
    return JsonResponse({
        'ok': command.status == HostAgentCommand.Status.SUCCEEDED,
        'acknowledged': True,
    })
