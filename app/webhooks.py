import hashlib
import hmac
import ipaddress
import json
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from .models import db, Webhook

logger = logging.getLogger(__name__)

TIMEOUT = 10

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_url_safe(url):
    """Reject webhook URLs pointing to private/internal networks (SSRF protection)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        addr = ipaddress.ip_address(hostname)
        for net in BLOCKED_NETWORKS:
            if addr in net:
                return False
        return True
    except ValueError:
        # hostname is not an IP, try resolving
        import socket
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in resolved:
                addr = ipaddress.ip_address(sockaddr[0])
                for net in BLOCKED_NETWORKS:
                    if addr in net:
                        return False
            return True
        except (socket.gaierror, TypeError):
            return False


def _sign_payload(payload_bytes, secret):
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def _send_one(webhook, event, payload):
    body = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    body_bytes = json.dumps(body, default=str).encode()

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Taskit-Webhook/1.0",
        "X-Webhook-Event": event,
    }
    if webhook.secret:
        headers["X-Webhook-Signature"] = _sign_payload(body_bytes, webhook.secret)

    try:
        resp = requests.post(webhook.url, data=body_bytes, headers=headers, timeout=TIMEOUT)
        if resp.status_code >= 400:
            logger.warning("Webhook %s returned %s", webhook.id, resp.status_code)
        else:
            logger.info("Webhook %s delivered %s", webhook.id, event)
    except Exception:
        logger.exception("Webhook %s failed for %s", webhook.id, event)


def fire_webhook(event, payload):
    webhooks = Webhook.query.filter_by(is_active=True).all()
    for wh in webhooks:
        if event in wh.get_events_list():
            if not is_url_safe(wh.url):
                logger.warning("Webhook %s blocked: URL %s points to internal network", wh.id, wh.url)
                continue
            t = threading.Thread(target=_send_one, args=(wh, event, payload), daemon=True)
            t.start()


def build_task_payload(task, action=None):
    labels = []
    try:
        labels = [tl.label.name for tl in task.task_labels]
    except Exception:
        pass
    return {
        "task_id": task.id,
        "display_id": task.display_id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "project_id": task.project_id,
        "project_name": task.project.name if task.project else None,
        "assignee": task.assignee.username if task.assignee else None,
        "created_by": task.creator.username if task.creator else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "labels": labels,
        "action": action,
    }


def build_comment_payload(comment, action=None):
    return {
        "comment_id": comment.id,
        "content": comment.content,
        "task_id": comment.task_id,
        "task_title": comment.task.title if comment.task else None,
        "project_id": comment.task.project_id if comment.task else None,
        "project_name": comment.task.project.name if comment.task and comment.task.project else None,
        "author": comment.author.username if comment.author else None,
        "action": action,
    }


def build_project_payload(project, action=None):
    return {
        "project_id": project.id,
        "name": project.name,
        "status": project.status,
        "created_by": project.creator.username if project.creator else None,
        "action": action,
    }
