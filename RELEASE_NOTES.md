**Legacy AI Email Studio** - email automation for **Travel Essence**: write an email once, then the app sends it to each customer one at a time, one minute apart.

## What's new in 1.4.0
- **Inbox (Windows):** emails arriving at your Travel Essence mailboxes, in one list. Watch the Outlook app (every account in it), Microsoft 365 / new Outlook, and any number of other mailboxes over IMAP. Read them, **Reply** or **Reply all** (same thread, with your signature and the original quoted), mark read/unread, or add the sender to your recipients. Replies appear in History.
- **New-email alerts:** the app checks every 2 minutes (you can change this), shows a Windows notification, and the sidebar shows how many are unread.
- **Legacy AI watches the inbox too** (Legacy v3.24): when a customer writes, she tells you who it is and what they want, out loud, as a notice and on your phone. She drafts a reply and sends it only after you approve the exact words. Newsletters and spam are not announced.
- In **Simulation mode** the Inbox shows a practice mailbox with sample customer emails, so you can try replying safely.

## What's new in 1.3.0
- **New name: Legacy AI Email Studio** (was Travel Essence Email Studio, and Travel Essence Mail on Android). Every feature from 1.2.0 is unchanged: campaigns, saved lists, the signature, Microsoft 365 / new Outlook, and Legacy AI control.
- **Upgrading keeps everything.** The installer updates your existing install in place and removes the old shortcuts. Your settings, lists, templates, history and the Legacy AI connection stay as they are. The Android app installs over the old one.
- The files are now `LegacyAIEmailStudio-Setup.exe`, `LegacyAIEmailStudio.exe` and `LegacyAIEmailStudio.apk`.

## What's new in 1.2.0
- **Legacy AI can run your email campaigns (Windows).** New **AI assistant** page: tick *Allow Legacy AI to control this app* and Legacy (v3.23 or newer) connects by herself. Ask her to write an offer, build or pick a customer list, send a test, start the campaign, and tell you how it's going. She works through the same pages you use, so her campaign shows on **Automation** with its progress bar.
- **You stay in charge:** Legacy asks before anything is sent, and the app can ask once more on its own screen before campaigns (always / campaigns only / never). Everything the AI did is listed on the AI assistant page.
- **Saved lists:** name a recipient list (for example “VIP guests”) on the **Recipients** page and load it again any time. Legacy can send to saved lists by name.
- Works with other AI apps too, through the open **MCP** standard (address and token on the AI assistant page).

## What's new in 1.1.0
- **Email signature builder (Windows and Android):** Travel Essence contact details with icons, social media links (Facebook, Instagram, WhatsApp, TikTok, LinkedIn, YouTube, X), your logo, a dark or light card and your choice of accent colour. It's added automatically under every campaign, test and manual email, and the icons and logo are attached inside each email so they always show.
- **New Outlook support on Windows:** sign in to **Microsoft 365 / new Outlook** in Settings to send from your mailbox and collect sent emails, customer addresses and contacts online. No classic Outlook needed.
- **Outlook data:** a new *Connect to* option chooses between the Outlook app on this PC and Microsoft 365 / new Outlook.

## Downloads

| File | Platform | What it is |
|---|---|---|
| `LegacyAIEmailStudio-Setup.exe` | Windows 10/11 | Installer with Start-menu and desktop shortcuts (recommended) |
| `LegacyAIEmailStudio.exe` | Windows 10/11 | Portable app: no install, just double-click |
| `LegacyAIEmailStudio.apk` | Android 8.0+ | Android app: open the file on your phone and tap **Install** |

> Windows SmartScreen and Android Play Protect may warn about an unknown app, because the files aren't code-signed or from an app store. Choose **More info → Run anyway** (Windows) or **Install anyway** (Android).

## Features (Windows and Android)
- **Compose** emails with full formatting, inline pictures, JPG/PNG/PDF attachments, `{first_name}` personalisation, templates, preview and test send
- **Recipients** from pasted text or CSV / Excel / TXT files, with validation and de-duplication
- **Automation**: one email per customer at a fixed interval (default 60 seconds), with pause / resume / stop, a progress bar, countdown, estimated finish time and a live log
- **Outlook data**: collect customers and past Travel Essence emails from Outlook, export them to Excel, and reuse an email as a template
- **Write & send** manual emails, **History** with re-queue, a **do-not-email list**, and light/dark themes

## Sending methods
- **Windows**: the classic Outlook app on the PC, **Microsoft 365 / new Outlook** sign-in, or SMTP
- **Android**: Microsoft 365 / new Outlook sign-in (one-time setup, see `android/README.md`), SMTP/IMAP, or simulation
- Both apps have a **simulation mode** for practising without sending anything
