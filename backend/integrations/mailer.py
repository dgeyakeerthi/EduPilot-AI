import os, smtplib, ssl, time
from email.message import EmailMessage

def send(to, subject, body):
    """Returns sent | failed | not_configured. Retries transient errors after 1s, 2s, 4s (max 3 retries)."""
    host = os.environ.get("SMTP_HOST")
    if not host: return "not_configured"
    m = EmailMessage(); m["From"] = os.environ.get("SMTP_FROM", "noreply@localhost"); m["To"] = to; m["Subject"] = subject; m.set_content(body)
    for wait in (0, 1, 2, 4):
        time.sleep(wait)
        try:
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as s:
                s.starttls(context=ssl.create_default_context())
                if os.environ.get("SMTP_USER"): s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                s.send_message(m); return "sent"
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused): return "failed"  # permanent: no retry
        except Exception: continue
    return "failed"
