# Legacy AI Email Studio for Android

This is the Android version of Legacy AI Email Studio (formerly Travel Essence Mail). It has the same features as the Windows
app, in a native Kotlin / Jetpack Compose app for phones and tablets running Android 8.0 or later.

## Download

Every push that changes `android/` is built by GitHub Actions (`.github/workflows/build-android.yml`):

1. Open the repository on GitHub, then **Actions → Build Android app**, and open the latest successful run.
2. Download the **LegacyAIEmailStudio-android** artifact and unzip it to get `LegacyAIEmailStudio.apk`.
3. Copy the APK to the phone and open it. Android asks once to allow installs from that app
   (for example Files or Chrome). Allow it, then tap **Install**.

Pushing a tag such as `v1.0.0` also attaches the APK to a GitHub **Release**.

## Features

| Windows app | Android app |
|---|---|
| Subject, rich email content, JPG/PNG/PDF attachments | **Compose**: formatting toolbar (font, size, bold/italic/underline/strike, colours, highlight, alignment, lists, links, inline pictures, clear formatting), `{first_name}` fields, attachments, templates, preview, test send |
| Paste or upload email addresses in bulk | **Recipients**: paste, clipboard, CSV / TXT / Excel import, de-duplication and validation, name editing, CSV export |
| One email per minute, one customer at a time | **Automation**: one email per customer, then a wait (default 60 seconds). Runs in a foreground service, so it keeps going with the screen off or the app in the background. A notification shows progress with Pause and Stop. |
| Collect data from the Outlook app | **Outlook data**: customers and sent/received emails from your **Microsoft 365 / Outlook.com** mailbox (or any IMAP mailbox, or the phone's contacts, including contacts synced by the Outlook app). Filter by date and subject, add customers to recipients, export to Excel, reuse an email as a template. |
| Light / dark theme | Moon/sun button in the top bar, or **More → Appearance** (System / Light / Dark) |
| Write and send manually | **More → Write & send** (To / Cc / Bcc, editor, attachments) |
| Progress bar | Sent / failed / remaining, countdown to the next email, estimated finish, success rate, live log, notification progress |
| History, re-queue, do-not-email list, signature, simulation mode | All included |

## Sending methods (Settings)

Android can't control the Outlook app the way Windows can, so the phone talks to the mailbox directly:

### 1. Microsoft 365 / Outlook.com (recommended)
The app sends through Microsoft Graph from the Travel Essence mailbox. Emails are saved in **Sent Items**
exactly as if they were sent from Outlook. The same sign-in powers **Outlook data**.

This needs a **one-time setup** in Microsoft Entra (Azure AD). It's free and takes about 5 minutes for you or
your IT admin:

1. Go to <https://entra.microsoft.com> → **Applications → App registrations → New registration**.
   - Name: `Legacy AI Email Studio`
   - Supported account types: *Accounts in any organizational directory and personal Microsoft accounts*
     (or *this organizational directory only* if you only use your company tenant).
   - Redirect URI: leave empty. Click **Register**.
2. Open **Authentication**. Under *Advanced settings*, set **Allow public client flows** to **Yes**, then **Save**.
3. Open **API permissions → Add a permission → Microsoft Graph → Delegated permissions** and add
   `Mail.Send`, `Mail.ReadWrite`, `Contacts.Read`, `User.Read` (and `offline_access`).
   If your organisation requires it, click **Grant admin consent**.
4. Copy the **Application (client) ID** from the *Overview* page.
5. In the app go to **Settings → Microsoft 365 / Outlook.com**, paste the client ID (keep the tenant as `common`
   or enter your tenant ID / domain), then tap **Sign in**. Tap **Copy code & open sign-in page**, paste the
   code, and sign in with the Travel Essence mailbox. The app finishes the sign-in by itself.

### 2. SMTP / IMAP account
For providers that allow SMTP sign-in with an app password, such as Gmail / Google Workspace, Zoho, Yahoo and most
web-hosting mailboxes. Add the IMAP server too and the app will:
- keep a copy of every email in the mailbox's Sent folder, and
- read that mailbox on the **Outlook data** page.

Microsoft 365 has switched off password-based SMTP sign-in, so use option 1 for Microsoft mailboxes.

### 3. Simulation
Practice mode. Campaigns run exactly as normal, but nothing is sent.

## Tips for long campaigns
- Allow notifications so you can watch progress and pause or stop from the notification shade.
- When the Automation page offers it, set the app's battery usage to **Unrestricted**. Some phones
  (for example Samsung or Xiaomi) otherwise pause background apps.
- If sending fails 3 times in a row (for example no internet), the campaign pauses itself. Fix the problem
  and press **Resume**. Customers who never received the email can be re-queued from **History**.

## Building it yourself
Install Android Studio (or JDK 17 + the Android SDK), then:

```bash
cd android
./gradlew testDebugUnitTest    # unit tests
./gradlew assembleRelease      # app/build/outputs/apk/release/app-release.apk
```

The release build is signed with `app/travel-essence-release.jks`, so every build can be installed over the
last one. For a private key, set the `ANDROID_KEYSTORE_PATH`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` environment variables (for example from GitHub secrets).

## Code layout

```
app/src/main/java/com/travelessence/emailstudio/
  core/       recipients parsing, CSV/XLSX, HTML helpers, models, JSON storage    (pure Kotlin, unit-tested)
  mail/       SMTP + MIME (JavaMail), Microsoft Graph client with device-code sign-in
  data/       mailbox readers: Microsoft Graph, IMAP, phone contacts
  campaign/   CampaignEngine (one-at-a-time sender), controller, foreground service
  ui/         Compose theme, components, WebView rich-text editor, screens
app/src/main/assets/editor.html   contenteditable editor used by the Compose screen
```
