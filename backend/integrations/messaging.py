"""SMS / WhatsApp (Twilio REST) and Web Push (pywebpush + VAPID). Each returns sent | failed | not_configured | no_subscription | invalid_phone."""
import base64, json, os, re, time, urllib.error, urllib.parse, urllib.request

def _twilio(frm, to, body):
    sid, tok = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    if not (sid and tok and frm): return "not_configured"
    data = urllib.parse.urlencode({"From": frm, "To": to, "Body": body[:1500]}).encode()
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode())
    for wait in (0, 1, 2, 4):  # retry only transient errors
        time.sleep(wait)
        try: urllib.request.urlopen(req, timeout=15); return "sent"
        except urllib.error.HTTPError as e:
            if e.code < 500: return "failed"
        except Exception: pass
    return "failed"

def _phone(p): return bool(p and re.fullmatch(r"\+[1-9]\d{7,14}", p))
def sms(to, body): return _twilio(os.environ.get("TWILIO_SMS_FROM"), to, body) if _phone(to) else "invalid_phone"
def whatsapp(to, body):
    frm = os.environ.get("TWILIO_WHATSAPP_FROM")
    return _twilio("whatsapp:" + frm if frm else None, "whatsapp:" + to, body) if _phone(to) else "invalid_phone"
def push(sub, title):
    key = os.environ.get("VAPID_PRIVATE_KEY")
    try: from pywebpush import webpush
    except ImportError: return "not_configured"
    if not key: return "not_configured"
    if not sub: return "no_subscription"
    try:
        webpush(subscription_info=sub, data=json.dumps({"title": title}), vapid_private_key=key, vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")}); return "sent"
    except Exception: return "failed"
