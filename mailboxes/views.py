import secrets
from urllib.parse import urlencode

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from .forms import ComposeEmailForm, EmailLinkForm, OutlookFolderForm, QuickCompanyLinkForm
from .models import EmailAccount, SyncedEmail
from .services import (
    PROVIDERS,
    encrypt_token,
    local_outlook_identity,
    provider_credentials,
    send_message,
    mark_and_delete_email,
    import_local_attachment,
    list_local_attachments,
    sync_account,
)


@login_required
def accounts(request):
    return render(request, 'mailboxes/accounts.html', {'accounts': EmailAccount.objects.filter(user=request.user)})


@login_required
def connect_local_outlook(request):
    if request.method != 'POST':
        return redirect('mailboxes:accounts')
    try:
        email = local_outlook_identity()
        EmailAccount.objects.update_or_create(
            user=request.user,
            provider=EmailAccount.Provider.OUTLOOK_LOCAL,
            email_address=email,
            defaults={'scopes': ['local:Mail.Read'], 'status': EmailAccount.Status.ACTIVE, 'error_message': ''},
        )
        messages.success(request, f'已连接本机 Outlook：{email}（只读）。')
    except Exception as exc:
        messages.error(request, f'无法连接本机 Outlook：{exc}')
    return redirect('mailboxes:accounts')


@login_required
def connect(request, provider):
    try:
        client_id, _ = provider_credentials(provider)
    except ImproperlyConfigured as exc:
        messages.error(request, str(exc))
        return redirect('mailboxes:accounts')
    if not client_id:
        messages.error(request, '尚未配置该服务商的 OAuth Client ID。')
        return redirect('mailboxes:accounts')
    state = secrets.token_urlsafe(32)
    request.session[f'oauth_state_{provider}'] = state
    callback_url = request.build_absolute_uri(reverse('mailboxes:callback', args=[provider]))
    params = {
        'client_id': client_id,
        'redirect_uri': callback_url,
        'response_type': 'code',
        'scope': PROVIDERS[provider]['scope'],
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent',
    }
    return redirect(f"{PROVIDERS[provider]['authorize']}?{urlencode(params)}")


@login_required
def callback(request, provider):
    if request.GET.get('state') != request.session.pop(f'oauth_state_{provider}', None):
        messages.error(request, 'OAuth state 校验失败。')
        return redirect('mailboxes:accounts')
    client_id, client_secret = provider_credentials(provider)
    callback_url = request.build_absolute_uri(reverse('mailboxes:callback', args=[provider]))
    response = requests.post(PROVIDERS[provider]['token'], data={'client_id': client_id, 'client_secret': client_secret, 'code': request.GET.get('code'), 'redirect_uri': callback_url, 'grant_type': 'authorization_code'}, timeout=30)
    response.raise_for_status()
    token = response.json()
    profile = requests.get(PROVIDERS[provider]['profile'], headers={'Authorization': f"Bearer {token['access_token']}"}, timeout=30)
    profile.raise_for_status()
    data = profile.json()
    email = data.get('emailAddress') or data.get('mail') or data.get('userPrincipalName') or request.user.email
    EmailAccount.objects.update_or_create(user=request.user, provider=provider, email_address=email, defaults={'encrypted_access_token': encrypt_token(token['access_token']), 'encrypted_refresh_token': encrypt_token(token.get('refresh_token', '')), 'token_expires_at': timezone.now() + timezone.timedelta(seconds=token.get('expires_in', 3600)), 'scopes': token.get('scope', '').split(), 'status': EmailAccount.Status.ACTIVE})
    messages.success(request, f'{email} 已连接。')
    return redirect('mailboxes:accounts')


@login_required
def disconnect(request, pk):
    account = get_object_or_404(EmailAccount, pk=pk, user=request.user)
    if request.method == 'POST':
        account.encrypted_access_token = ''
        account.encrypted_refresh_token = ''
        account.status = EmailAccount.Status.DISCONNECTED
        account.save()
    return redirect('mailboxes:accounts')


@login_required
def messages_list(request):
    emails = SyncedEmail.objects.filter(account__user=request.user).select_related('account', 'company', 'application')
    q = request.GET.get('q', '').strip()
    company = request.GET.get('company', '').strip()
    linked = request.GET.get('linked', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if q:
        emails = emails.filter(Q(subject__icontains=q) | Q(sender__icontains=q) | Q(body_text__icontains=q))
    if company.isdigit():
        emails = emails.filter(company_id=company, company__user=request.user)
    if linked == 'yes':
        emails = emails.filter(Q(company__isnull=False) | Q(application__isnull=False) | Q(contact__isnull=False)).distinct()
    elif linked == 'no':
        emails = emails.filter(company__isnull=True, application__isnull=True, contact__isnull=True)
    if date_from:
        emails = emails.filter(received_at__date__gte=date_from)
    if date_to:
        emails = emails.filter(received_at__date__lte=date_to)
    page_obj = Paginator(emails, 20).get_page(request.GET.get('page'))
    return render(request, 'mailboxes/messages.html', {
        'emails': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.paginator.num_pages > 1,
        'companies': request.user.companies.filter(archived_at__isnull=True).order_by('name'),
    })


@login_required
def message_detail(request, pk):
    email = get_object_or_404(
        SyncedEmail.objects.select_related('account', 'company', 'application', 'contact'),
        pk=pk,
        account__user=request.user,
    )
    attachments = []
    attachment_error = ''
    if email.has_attachments and email.account.provider == EmailAccount.Provider.OUTLOOK_LOCAL:
        try: attachments = list_local_attachments(email)
        except Exception as exc: attachment_error = str(exc)
    return render(request, 'mailboxes/message_detail.html', {'email': email, 'attachments': attachments, 'attachment_error': attachment_error})


@login_required
def import_attachment(request, pk, index):
    email = get_object_or_404(SyncedEmail, pk=pk, account__user=request.user)
    if request.method == 'POST':
        try:
            document = import_local_attachment(email, index)
            messages.success(request, f'附件“{document.original_name}”已导入资料库。')
        except Exception as exc:
            messages.error(request, f'附件导入失败：{exc}')
    return redirect('mailboxes:message-detail', pk=pk)


@login_required
def link_message(request, pk):
    email = get_object_or_404(SyncedEmail, pk=pk, account__user=request.user)
    form = EmailLinkForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        email.company = form.cleaned_data['company']
        email.application = form.cleaned_data['application']
        email.contact = form.cleaned_data['contact']
        email.save(update_fields=('company', 'application', 'contact'))
        messages.success(request, '邮件关联已更新。')
        return redirect('mailboxes:message-detail', pk=email.pk)
    return render(request, 'generic/form.html', {'form': form, 'title': '关联邮件'})


@login_required
def quick_link_company(request, pk):
    email = get_object_or_404(SyncedEmail, pk=pk, account__user=request.user)
    if request.method == 'POST':
        form = QuickCompanyLinkForm(request.POST, user=request.user)
        if form.is_valid():
            email.company = form.cleaned_data['company']
            email.save(update_fields=('company',))
            messages.success(request, '邮件公司关联已更新。')
    return redirect(request.POST.get('next') or 'mailboxes:messages')


@login_required
def delete_message(request, pk):
    email = get_object_or_404(SyncedEmail, pk=pk, account__user=request.user)
    if request.method == 'POST' and request.POST.get('confirm') == 'yes':
        mark_and_delete_email(email)
        messages.success(request, '已删除数据库中的邮件副本；Outlook 原邮件未受影响。')
        return redirect('mailboxes:messages')
    return render(request, 'mailboxes/message_confirm_delete.html', {'email': email})


@login_required
def bulk_delete_messages(request):
    if request.method == 'POST' and request.POST.get('confirm') == 'yes':
        selected = list(SyncedEmail.objects.filter(account__user=request.user, pk__in=request.POST.getlist('selected')).select_related('account'))
        for email in selected:
            mark_and_delete_email(email)
        messages.success(request, f'已删除 {len(selected)} 封数据库邮件副本；Outlook 原邮件未受影响。')
    return redirect('mailboxes:messages')


@login_required
def update_folder(request, pk):
    account = get_object_or_404(EmailAccount, pk=pk, user=request.user, provider=EmailAccount.Provider.OUTLOOK_LOCAL)
    if request.method == 'POST':
        form = OutlookFolderForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, '同步文件夹已更新。')
    return redirect('mailboxes:accounts')


@login_required
def sync(request, pk):
    account = get_object_or_404(EmailAccount, pk=pk, user=request.user)
    if request.method == 'POST':
        try:
            imported = sync_account(account)
            if account.provider == EmailAccount.Provider.OUTLOOK_LOCAL:
                messages.success(request, f'本机 Outlook 同步完成，本次新增 {imported} 封邮件。')
            else:
                messages.success(request, '邮箱同步完成。')
        except Exception as exc:
            account.status = EmailAccount.Status.ERROR
            account.error_message = str(exc)[:1000]
            account.save()
            messages.error(request, '邮箱同步失败，请查看账户错误信息。')
    return redirect('mailboxes:accounts')


@login_required
def compose(request):
    form = ComposeEmailForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        application = Application.objects.filter(pk=form.cleaned_data.get('application_id'), user=request.user).first()
        try:
            send_message(form.cleaned_data['account'], to=form.cleaned_data['to'], subject=form.cleaned_data['subject'], body=form.cleaned_data['body'], application=application)
            messages.success(request, '邮件已发送。')
            return redirect('applications:detail', pk=application.pk) if application else redirect('mailboxes:messages')
        except Exception:
            form.add_error(None, '发送失败，请检查邮箱授权后重试。')
    return render(request, 'generic/form.html', {'form': form})
