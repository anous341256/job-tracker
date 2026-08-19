"""Windows companion that relays classic Outlook and local Ollama to Django.

All mutable state is kept under ``D:\\New project\\.local\\host-agent``.  The
agent only makes outbound HTTPS requests when a remote server is configured.
"""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.local' / 'host-agent'
CONFIG_FILE = STATE / 'agent.env'
OUTBOX = STATE / 'outbox'
LOG_DIR = STATE / 'logs'


def load_local_config():
    """Load the agent-only config without adding another dependency."""
    if not CONFIG_FILE.exists():
        return
    for raw_line in CONFIG_FILE.read_text(encoding='utf-8-sig').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


STATE.mkdir(parents=True, exist_ok=True)
OUTBOX.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
load_local_config()

TOKEN_FILE = Path(os.getenv('HOST_AGENT_TOKEN_FILE', str(STATE / 'token')))
BASE_URL = os.getenv('JOB_TRACKER_URL', 'http://127.0.0.1:8000').rstrip('/')
CA_BUNDLE = os.getenv('JOB_TRACKER_CA_BUNDLE', '').strip()
POLL_SECONDS = max(2, int(os.getenv('HOST_AGENT_POLL_SECONDS', '3')))
VERSION = '1.1.0'


def stable_agent_id():
    configured = os.getenv('HOST_AGENT_ID', '').strip()
    if configured:
        return configured[:100]
    path = STATE / 'agent-id'
    if not path.exists():
        path.write_text(f'windows-{uuid.uuid4().hex[:16]}', encoding='ascii')
    return path.read_text(encoding='ascii').strip()[:100]


AGENT_ID = stable_agent_id()
SESSION = requests.Session()
LOGGER = logging.getLogger('jobtracker-host-agent')
LOGGER.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_DIR / 'agent.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
LOGGER.addHandler(handler)


def validate_server_url():
    parsed = urlparse(BASE_URL)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise SystemExit('JOB_TRACKER_URL must be a valid http(s) URL.')
    if parsed.scheme != 'https' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise SystemExit('A remote JOB_TRACKER_URL must use HTTPS. Plain HTTP is allowed only for localhost.')


def request_headers():
    token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-JobTracker-Agent': AGENT_ID,
        'User-Agent': f'JobTrackerHostAgent/{VERSION}',
    }


def post(path, payload, timeout):
    response = SESSION.post(
        f'{BASE_URL}{path}', headers=request_headers(),
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        timeout=timeout, verify=CA_BUNDLE or True,
    )
    response.raise_for_status()
    return response


def outlook_namespace():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return pythoncom, win32com.client.Dispatch('Outlook.Application').GetNamespace('MAPI')


def outlook_identity():
    pythoncom, namespace = outlook_namespace()
    try:
        for account in namespace.Accounts:
            address = str(getattr(account, 'SmtpAddress', '') or '').strip()
            if '@' in address:
                return address
        raise RuntimeError('No SMTP address found in classic Outlook.')
    finally:
        pythoncom.CoUninitialize()


def sender_address(item, fallback):
    address = str(getattr(item, 'SenderEmailAddress', '') or '')
    if getattr(item, 'SenderEmailType', '') == 'EX':
        try:
            address = str(item.Sender.GetExchangeUser().PrimarySmtpAddress or address)
        except Exception:
            pass
    return address if '@' in address else fallback


def _timestamp(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.timestamp()


def sync_outlook(payload):
    """Read one bounded page. The server queues older pages when truncated."""
    pythoncom, namespace = outlook_namespace()
    try:
        folder = namespace.GetDefaultFolder(6)
        if payload.get('folder') and payload['folder'].lower() != 'inbox':
            folder = folder.Folders.Item(payload['folder'])
        items = folder.Items
        items.Sort('[ReceivedTime]', True)
        limit = min(max(int(payload.get('limit', 100)), 1), 100)
        since_ts = _timestamp(payload.get('since'))
        if since_ts is None:
            since_ts = (datetime.now() - timedelta(days=int(payload.get('days', 30)))).timestamp()
        before_ts = _timestamp(payload.get('before_received_at'))
        messages = []
        truncated = False
        fallback = outlook_identity()
        for item in items:
            if getattr(item, 'Class', None) != 43:
                continue
            received = getattr(item, 'ReceivedTime', None)
            if not received:
                continue
            received_ts = received.timestamp()
            if before_ts is not None and received_ts >= before_ts:
                continue
            if received_ts < since_ts:
                break
            if len(messages) >= limit:
                truncated = True
                break
            recipients = []
            try:
                recipients = [str(r.Address) for r in item.Recipients if getattr(r, 'Address', None)]
            except Exception:
                pass
            messages.append({
                'id': str(item.EntryID),
                'thread_id': str(getattr(item, 'ConversationID', '') or ''),
                'sender': sender_address(item, fallback),
                'recipients': recipients,
                'subject': str(getattr(item, 'Subject', '') or '')[:500],
                'body_text': str(getattr(item, 'Body', '') or '')[:50000],
                'folder_name': payload.get('folder', 'Inbox'),
                'is_read': not bool(getattr(item, 'UnRead', False)),
                'has_attachments': bool(getattr(getattr(item, 'Attachments', None), 'Count', 0)),
                'received_at': received.isoformat(),
            })
        return {
            'messages': messages,
            'truncated': truncated,
            'next_before_received_at': messages[-1]['received_at'] if truncated and messages else None,
        }
    finally:
        pythoncom.CoUninitialize()


def ollama(payload):
    response = requests.post('http://127.0.0.1:11434/api/chat', json={
        'model': payload['model'], 'stream': False, 'think': False,
        'messages': [
            {'role': 'system', 'content': payload['system_prompt']},
            {'role': 'user', 'content': payload['prompt']},
        ],
        'format': payload['schema'], 'options': {'temperature': 0},
    }, timeout=180)
    if not response.ok:
        try:
            detail = response.json().get('error', '')
        except (ValueError, AttributeError):
            detail = ''
        detail = str(detail)[:500]
        raise RuntimeError(f'Ollama HTTP {response.status_code}: {detail or "request rejected"}')
    data = response.json()
    return {
        'result': json.loads(data['message']['content']),
        'input_tokens': int(data.get('prompt_eval_count', 0)),
        'output_tokens': int(data.get('eval_count', 0)),
    }


def health():
    errors = []
    try:
        outlook_identity()
        outlook_ok = True
    except Exception as exc:
        outlook_ok = False
        errors.append(f'Outlook: {exc}')
    try:
        ollama_ok = requests.get('http://127.0.0.1:11434/api/tags', timeout=2).ok
    except Exception:
        ollama_ok = False
    return outlook_ok, ollama_ok, '; '.join(errors)[:1000]


def _protect(data):
    import win32crypt
    return win32crypt.CryptProtectData(data, 'Job Tracker Host Agent', None, None, None, 0)


def _unprotect(data):
    import win32crypt
    return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]


def save_completion(command_id, data):
    """Persist encrypted results before upload so a network failure loses nothing."""
    destination = OUTBOX / f'{int(command_id)}.bin'
    temporary = OUTBOX / f'{int(command_id)}.tmp'
    record = json.dumps({'command_id': int(command_id), 'data': data}, ensure_ascii=False).encode('utf-8')
    temporary.write_bytes(_protect(record))
    os.replace(temporary, destination)


def flush_outbox():
    pending = sorted(OUTBOX.glob('*.bin'), key=lambda item: item.stat().st_mtime)
    for item in pending:
        record = json.loads(_unprotect(item.read_bytes()).decode('utf-8'))
        response = post(
            f"/internal/host-agent/commands/{record['command_id']}/complete/",
            record['data'], timeout=90,
        )
        if response.json().get('acknowledged') or response.json().get('duplicate'):
            item.unlink(missing_ok=True)
            LOGGER.info('Uploaded result for command %s.', record['command_id'])
        else:
            raise RuntimeError(f"Server rejected command {record['command_id']} result.")
    return len(pending)


def execute(command):
    if command['type'] == 'outlook_connect':
        return {'email_address': outlook_identity()}
    if command['type'] == 'outlook_sync':
        return sync_outlook(command['payload'])
    if command['type'] == 'ollama':
        return ollama(command['payload'])
    raise RuntimeError('Unsupported host agent command.')


def main():
    if sys.platform != 'win32':
        raise SystemExit('Host agent must run on Windows.')
    if not TOKEN_FILE.exists() or not TOKEN_FILE.read_text(encoding='utf-8').strip():
        raise SystemExit(f'Missing host-agent token file: {TOKEN_FILE}')
    validate_server_url()
    LOGGER.info('Host Agent %s started; server=%s agent_id=%s', VERSION, BASE_URL, AGENT_ID)
    while True:
        try:
            flush_outbox()
            outlook_ok, ollama_ok, health_error = health()
            post('/internal/host-agent/heartbeat/', {
                'agent_id': AGENT_ID,
                'version': VERSION,
                'outlook_available': outlook_ok,
                'ollama_available': ollama_ok,
                'error_message': health_error,
            }, timeout=15)
            response = post('/internal/host-agent/claim/', {'agent_id': AGENT_ID}, timeout=25)
            command = response.json().get('command')
            if command:
                try:
                    output = execute(command)
                except Exception as exc:
                    LOGGER.exception('Command %s failed locally.', command['id'])
                    output = {'error': str(exc)[:1000]}
                save_completion(command['id'], output)
                flush_outbox()
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            LOGGER.info('Host Agent stopped by user.')
            return
        except Exception as exc:
            LOGGER.warning('Connection cycle failed: %s', exc)
            time.sleep(min(max(POLL_SECONDS * 2, 8), 30))


if __name__ == '__main__':
    main()
