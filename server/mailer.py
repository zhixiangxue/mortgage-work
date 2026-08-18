"""Email delivery for login codes.

Three providers, picked by ``EMAIL_PROVIDER``:

* ``console`` (default) — prints the code to stdout/log. Zero-config so the
  whole loop runs on a dev box with no mail account; the "email" is the
  terminal.
* ``smtp`` — plain SMTP, the pilot pick: your own mailbox, no third party.
  Defaults to Gmail (needs an *app password*, not the account password —
  Google Account → Security → 2-Step Verification → App passwords), and
  works the same with QQ/163 auth codes by pointing ``SMTP_HOST`` at them.
* ``resend`` — real delivery via Resend's HTTP API. Needs ``RESEND_API_KEY``
  and ``RESEND_FROM`` (a verified sender on the Resend account) — the
  post-pilot choice once volume or deliverability starts to matter.

The app never sees which provider is active — it only asks "send a code to
this address".
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx

log = logging.getLogger(__name__)


def _code_mail(code: str) -> tuple[str, str, str]:
    """Subject + plain text + HTML shared by every provider. The plain part
    is the spam-filter fallback; the HTML part is what people actually see."""
    subject = f"Your Mortgage Work login code: {code}"
    text = (
        f"Your Mortgage Work login code is:\n\n    {code}\n\n"
        "It expires in 10 minutes. If you didn't ask for this code, "
        "ignore this email.\n"
    )
    # Email-client-safe on purpose: table layout, inline styles, system
    # fonts, no images or web fonts — renders identically in Gmail,
    # Outlook and QQ mail alike.
    html = f"""\
<div style="background:#f4f5f7;padding:32px 16px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table role="presentation" width="420" cellpadding="0" cellspacing="0"
             style="max-width:420px;width:100%;">
        <tr><td style="padding:8px 0 24px;font-family:Helvetica,Arial,sans-serif;
                       font-size:18px;font-weight:bold;color:#111827;">
          Mortgage<span style="color:#3cd742;"> Work</span>
        </td></tr>
        <tr><td style="background:#ffffff;border-radius:12px;padding:36px 32px;
                       font-family:Helvetica,Arial,sans-serif;">
          <div style="font-size:16px;color:#111827;font-weight:bold;">
            Your login code
          </div>
          <div style="font-size:14px;color:#6b7280;padding:10px 0 24px;">
            Enter this code to sign in. It expires in 10 minutes.
          </div>
          <div align="center"
               style="background:#f4f5f7;border-radius:10px;padding:24px 0;
                      font-size:40px;font-weight:bold;letter-spacing:12px;
                      color:#111827;font-family:Helvetica,Arial,sans-serif;">
            {code}
          </div>
          <div style="font-size:13px;color:#6b7280;padding:24px 0 0;
                      line-height:1.6;">
            If you didn't ask for this code, you can safely ignore this
            email.
          </div>
        </td></tr>
        <tr><td style="padding:20px 4px;font-family:Helvetica,Arial,sans-serif;
                       font-size:12px;color:#9ca3af;">
          Mortgage Work — the AI workspace for loan officers
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>
"""
    return subject, text, html


def send_code(email: str, code: str) -> None:
    """Deliver the login code. Raises RuntimeError when delivery is impossible
    (missing provider config) so the API can surface it instead of pretending
    the mail went out."""
    provider = os.environ.get("EMAIL_PROVIDER", "console").lower()
    if provider == "smtp" or provider == "gmail":
        _send_smtp(email, code)
    elif provider == "resend":
        _send_resend(email, code)
    else:
        # Dev/demo path: the code is the log line. Kept loud on purpose —
        # forgetting the console provider is active and hunting a "lost email"
        # is the failure mode this noise prevents.
        log.info("[console-mailer] login code for %s → %s", email, code)
        print(f"[console-mailer] login code for {email} → {code}", flush=True)


def _send_smtp(email: str, code: str) -> None:
    """Send through a personal mailbox. Gmail defaults: smtp.gmail.com:587
    STARTTLS with an app password. Free Gmail allows ~500 recipients/day —
    headroom the pilot will never touch."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", "") or username
    if not username or not password:
        raise RuntimeError(
            "EMAIL_PROVIDER=smtp but SMTP_USER / SMTP_PASSWORD are not set "
            "(for Gmail, SMTP_PASSWORD is an app password, not your login)")
    subject, text, html = _code_mail(code)
    msg = EmailMessage()
    msg["From"] = f"Mortgage Work <{sender}>"
    msg["To"] = email
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(username, password)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        # The single most likely misconfiguration deserves its own wording.
        raise RuntimeError(
            f"SMTP login to {host} rejected — for Gmail use an app password "
            "(16 chars, from Google Account → Security → App passwords)")
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"SMTP delivery to {host} failed: {exc}")
    log.info("login code mailed to %s via smtp (%s)", email, host)


def _send_resend(email: str, code: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("RESEND_FROM", "")
    if not api_key or not sender:
        raise RuntimeError(
            "EMAIL_PROVIDER=resend but RESEND_API_KEY / RESEND_FROM are not set")
    subject, text, html = _code_mail(code)
    res = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": sender,
            "to": [email],
            "subject": subject,
            "text": text,
            "html": html,
        },
        timeout=20,
    )
    if res.status_code >= 300:
        raise RuntimeError(f"resend rejected the mail ({res.status_code}): {res.text[:200]}")
    log.info("login code mailed to %s via resend", email)
