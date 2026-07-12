import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from .forms import ComposeEmailForm, EmailLinkForm
from .models import EmailAccount, SyncedEmail
from .services import PROVIDERS, encrypt_token, provider_credentials, send_message, sync_account


@login_required
def accounts(request): return render(request, 'mailboxes/accounts.html', {'accounts': EmailAccount.objects.filter(user=request.user)})


@login_required
def connect(request, provider):
    try: client_id, _ = provider_credentials(provider)
    except ImproperlyConfigured as exc: messages.error(request, str(exc)); return redirect('mailboxes:accounts')
    if not client_id: messages.error(request, '尚未配置该服务商的 OAuth Client ID。'); return redirect('mailboxes:accounts')
    state = secrets.token_urlsafe(32); request.session[f'oauth_state_{provider}'] = state
    callback = request.build_absolute_uri(reverse('mailboxes:callback', args=[provider]))
    params = {'client_id': client_id, 'redirect_uri': callback, 'response_type': 'code', 'scope': PROVIDERS[provider]['scope'], 'state': state, 'access_type': 'offline', 'prompt': 'consent'}
    return redirect(f"{PROVIDERS[provider]['authorize']}?{urlencode(params)}")


@login_required
def callback(request, provider):
    if request.GET.get('state') != request.session.pop(f'oauth_state_{provider}', None): messages.error(request, 'OAuth state 校验失败。'); return redirect('mailboxes:accounts')
    client_id, client_secret = provider_credentials(provider); callback_url = request.build_absolute_uri(reverse('mailboxes:callback', args=[provider]))
    response = requests.post(PROVIDERS[provider]['token'], data={'client_id': client_id, 'client_secret': client_secret, 'code': request.GET.get('code'), 'redirect_uri': callback_url, 'grant_type': 'authorization_code'}, timeout=30); response.raise_for_status(); token = response.json()
    profile = requests.get(PROVIDERS[provider]['profile'], headers={'Authorization': f"Bearer {token['access_token']}"}, timeout=30); profile.raise_for_status(); data = profile.json(); email = data.get('emailAddress') or data.get('mail') or data.get('userPrincipalName') or request.user.email
    EmailAccount.objects.update_or_create(user=request.user, provider=provider, email_address=email, defaults={'encrypted_access_token': encrypt_token(token['access_token']), 'encrypted_refresh_token': encrypt_token(token.get('refresh_token', '')), 'token_expires_at': timezone.now() + timezone.timedelta(seconds=token.get('expires_in', 3600)), 'scopes': token.get('scope', '').split(), 'status': EmailAccount.Status.ACTIVE})
    messages.success(request, f'{email} 已连接。'); return redirect('mailboxes:accounts')


@login_required
def disconnect(request, pk):
    account = get_object_or_404(EmailAccount, pk=pk, user=request.user)
    if request.method == 'POST': account.encrypted_access_token = ''; account.encrypted_refresh_token = ''; account.status = EmailAccount.Status.DISCONNECTED; account.save()
    return redirect('mailboxes:accounts')


@login_required
def messages_list(request): return render(request, 'mailboxes/messages.html', {'emails': SyncedEmail.objects.filter(account__user=request.user).select_related('account', 'company', 'application')[:200]})


@login_required
def link_message(request, pk):
    email = get_object_or_404(SyncedEmail, pk=pk, account__user=request.user)
    form = EmailLinkForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        email.company = form.cleaned_data['company']; email.application = form.cleaned_data['application']; email.contact = form.cleaned_data['contact']; email.save(update_fields=('company', 'application', 'contact')); messages.success(request, '邮件关联已更新。'); return redirect('mailboxes:messages')
    return render(request, 'generic/form.html', {'form': form})


@login_required
def sync(request, pk):
    account = get_object_or_404(EmailAccount, pk=pk, user=request.user)
    if request.method == 'POST':
        try: sync_account(account); messages.success(request, '邮箱同步完成。')
        except Exception as exc: account.status = EmailAccount.Status.ERROR; account.error_message = str(exc)[:1000]; account.save(); messages.error(request, '邮箱同步失败，请检查授权。')
    return redirect('mailboxes:accounts')


@login_required
def compose(request):
    form = ComposeEmailForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        application = Application.objects.filter(pk=form.cleaned_data.get('application_id'), user=request.user).first()
        try: send_message(form.cleaned_data['account'], to=form.cleaned_data['to'], subject=form.cleaned_data['subject'], body=form.cleaned_data['body'], application=application); messages.success(request, '邮件已发送。'); return redirect('applications:detail', pk=application.pk) if application else redirect('mailboxes:messages')
        except Exception: form.add_error(None, '发送失败，请检查邮箱授权后重试。')
    return render(request, 'generic/form.html', {'form': form})

# Create your views here.
