# Privacy Policy - Legacy AI Email Studio

*Last updated: 23 October 2026*

This policy covers the **Legacy AI Email Studio** app for Android (Google Play package `com.legacyai.emailstudio`) and the
Legacy AI Email Studio desktop app for Windows. Both are published by Shahyd Legacy ("we").

**In short:** the app has no servers, accounts, analytics, advertising or tracking. Your data stays on your device. It only
goes to the email service **you** connect, so that your emails can be sent and your mailbox read. We never receive it.

## What the app stores, and where

Everything below is stored **only on your device**, in the app's private storage:

- **Your email work:** drafts, templates, recipient lists (email addresses and names), the do-not-email list and the
  history of what was sent to whom.
- **Your email signature:** the contact details, social links and logo you enter.
- **Settings:** for example the sending method and the time between emails.
- **Sign-in secrets:** your SMTP/IMAP password, Microsoft sign-in tokens and the AI-agent access token. On Android all of
  them are encrypted with the Android Keystore. On Windows, passwords are kept in Windows Credential Manager and Microsoft
  tokens are protected with DPAPI. The AI-agent token is kept in the app's settings folder so that AI apps on the same PC
  can find it.

Android backups are switched off for this app, so this data is not copied to cloud backups. Uninstalling the app (or
**Settings → Apps → Legacy AI Email Studio → Clear storage**) deletes all of it. Individual history entries can also be
deleted in the app.

## What leaves your device, and why

Data leaves your device only when the app does something you asked for, and only to the service you chose:

| You choose | What is sent | Where |
|---|---|---|
| **Microsoft 365 / Outlook.com** | The emails you send (recipients, subject, content, attachments). When you use *Outlook data*, the app reads message headers, addresses and contacts from your mailbox. | Microsoft (Microsoft Graph), over HTTPS, with the permissions you approve at sign-in |
| **SMTP / IMAP email account** | The emails you send; when you use *Outlook data* with IMAP, the app reads messages from that mailbox. | The mail server you enter, over TLS where the server supports it |
| **Simulation mode** | Nothing. Emails are not sent anywhere. | - |

These services handle your data under their own privacy policies, for example the
[Microsoft Privacy Statement](https://privacy.microsoft.com/privacystatement).

## Phone contacts (Android)

If you choose to import recipients from your phone's contacts, the app asks for the **Contacts** permission. It reads names
and email addresses on the device to add them to your recipient list. Contacts are not uploaded anywhere. You can refuse or
withdraw the permission at any time in Android settings; the rest of the app keeps working.

## Notifications (Android)

The app shows notifications for campaign progress, finished campaigns and AI-agent approval requests. They are created on
the device. Nothing is sent to us or to a push service.

## AI agents (optional)

If you switch on **AI agents**, AI assistants you connect yourself can use the app through the Model Context Protocol
(MCP). Examples are Claude Code, Claude Desktop, Legacy AI or another MCP client. They need the access token shown in the
app, and by default only apps on the same device can connect. If you also allow **devices on my Wi-Fi**, devices on your
local network that have the token can connect. A connected agent can read what the app holds (drafts, recipient lists,
templates, history) and ask to send email. With the default setting, every send waits for your approval on the phone.
What an AI agent does with the data it reads is governed by that agent's own privacy terms. You can switch AI agents off or
create a new token at any time.

## What we do not do

- We do not collect, sell or share personal data, and we have no servers that receive it.
- We do not use analytics, crash-reporting, advertising or tracking SDKs.
- We do not use your data to train AI models.

## Your responsibilities when emailing others

You decide who receives your emails. Only email people who have agreed to hear from you, and honour unsubscribe requests.
The do-not-email list helps you do this. You are responsible for complying with the laws that apply to your messages, such
as GDPR, CAN-SPAM or your local equivalents.

## Children

The app is a business tool and is not directed at children under 13 (or the age required in your country).

## Changes and contact

If this policy changes, the new version will be published at this address with a new "Last updated" date. For questions
about privacy, please use the contact email on the app's Google Play listing, or open an issue at
<https://github.com/shahydlegacyofficial-creator/Automate-Email/issues>.
