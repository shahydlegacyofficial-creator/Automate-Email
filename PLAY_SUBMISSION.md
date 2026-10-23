# Publishing Legacy AI Email Studio on Google Play

Everything Google Play asks for is prepared in this repository. This page goes through Play Console in order and says
what to enter at each step.

| Item | Where |
|---|---|
| App bundle (AAB), signed with your upload key | `LegacyAIEmailStudio-play.aab` (sent to you), or the **LegacyAIEmailStudio-play** artifact of the *Build Android app* workflow once the upload-key secrets are set (step 1) |
| R8 mapping file (deobfuscation) | `LegacyAIEmailStudio-play-mapping.txt` (same places) |
| Store text | [`fastlane/metadata/android/en-US/`](fastlane/metadata/android/en-US) - `title.txt`, `short_description.txt`, `full_description.txt`, `changelogs/4.txt` |
| App icon 512 × 512 | `fastlane/metadata/android/en-US/images/icon.png` |
| Feature graphic 1024 × 500 | `fastlane/metadata/android/en-US/images/featureGraphic.png` |
| Phone screenshots (1080 × 2160) | `fastlane/metadata/android/en-US/images/phoneScreenshots/` |
| Privacy policy URL | <https://github.com/shahydlegacyofficial-creator/Automate-Email/blob/HEAD/PRIVACY.md> |

**App facts:** package name `com.legacyai.emailstudio` (permanent once uploaded), version 1.5.0 (version code 4),
targets Android 16 (API 36), minimum Android 8.0 (API 26). It has no ads, in-app purchases, accounts or analytics. The only
native code is Jetpack Compose's small graphics library, which is built for 16 KB memory pages as Play requires.

---

## 0. Before you start

1. **A Google Play developer account** (one-time USD 25) at <https://play.google.com/console>. Google verifies your
   identity first, which can take a few days.
2. **Personal accounts created after November 2023 must run a closed test first:** at least **12 testers** opted in for
   **14 days in a row** before you can apply for production. Plan for this: invite friends or customers by email in the
   *Closed testing* track (step 6). Organisation accounts are exempt.
3. **Keep the upload key safe.** You received `upload-keystore.jks` and its password. Store both in a password manager
   and keep a backup copy. If the key is ever lost or leaked, Play Console can reset it (*Setup → App signing → Request
   upload key reset*), but that takes a few days.

## 1. Let GitHub sign future bundles (recommended, once)

GitHub → the repository → **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
|---|---|
| `ANDROID_UPLOAD_KEYSTORE_BASE64` | the whole content of `upload-keystore.base64.txt` |
| `ANDROID_UPLOAD_KEYSTORE_PASSWORD` | the keystore password |
| `ANDROID_UPLOAD_KEY_PASSWORD` | the same password |
| `ANDROID_UPLOAD_KEY_ALIAS` | `upload` |

From then on, every *Build Android app* run produces a **signed** `LegacyAIEmailStudio-play.aab` in the artifact
**LegacyAIEmailStudio-play**. Without the secrets it produces `LegacyAIEmailStudio-play-unsigned.aab`, which Play will not
accept.

To sign an unsigned bundle by hand (needs Java):
`jarsigner -keystore upload-keystore.jks -sigalg SHA256withRSA -digestalg SHA-256 LegacyAIEmailStudio-play-unsigned.aab upload`

**Optional: Microsoft 365 sign-in for everyone.** Without this, people can still send through SMTP (Gmail, Zoho, web
hosts) or use Simulation mode. Microsoft 365 users would then have to paste a client ID of their own. To build one in:

1. Register an app at <https://entra.microsoft.com> → **App registrations → New registration**. Choose *Accounts in any
   organizational directory and personal Microsoft accounts*.
2. Under **Authentication**, turn on *Allow public client flows*.
3. Add the delegated permissions `Mail.Send`, `Mail.ReadWrite`, `Contacts.Read`, `User.Read` and `offline_access`.
4. Add a **repository variable** (not a secret) named `MS_CLIENT_ID` with its Application (client) ID.

Completing Microsoft's *publisher verification* removes the "unverified" warning and lets more organisations allow it.

## 2. Create the app

Play Console → **Create app**:

- **App name:** `Legacy AI Email Studio`
- **Default language:** English (United States)
- **App or game:** App
- **Free or paid:** Free
- Accept the declarations and click *Create app*.

## 3. Set up your app (Dashboard → "Set up your app")

| Section | What to enter |
|---|---|
| **Privacy policy** | `https://github.com/shahydlegacyofficial-creator/Automate-Email/blob/HEAD/PRIVACY.md` |
| **App access** | *All functionality is available without special access.* Notes for the reviewer: "No account is needed. The app opens in Simulation mode, so campaigns, history and every screen work without sending real email. The AI agents screen (More → AI agents) can be switched on without a login." |
| **Ads** | No, my app does not contain ads |
| **Content rating** | Start the questionnaire. Email: yours. Category: **All other app types**. Answer **No** to violence, sexuality, language, controlled substances and gambling. It does let users share content with others (email), but there is no social feature with strangers. Expected rating: Everyone / PEGI 3. |
| **Target audience** | **18 and over**. It is a business tool, which also keeps it out of the Families programme. |
| **News app** | No |
| **COVID-19 apps** | Not a COVID-19 app |
| **Data safety** | See below |
| **Government apps** | No |
| **Financial features** | None |
| **Health** | None |

### Data safety answers

The app has no servers. Data goes from the phone straight to the email service the user connects (Microsoft or their
SMTP/IMAP server), only when they send or import.

- **Does your app collect or share any of the required user data types?** **Yes**. Emails and addresses leave the device
  to be delivered.
- **Is all of the user data collected by your app encrypted in transit?** **Yes** (HTTPS / TLS).
- **Do you provide a way for users to request that their data is deleted?** **Yes**. Everything is on the device, so
  uninstalling or *Clear storage* deletes it, and history entries can be deleted in the app.

Data types to tick. For each: **Collected: Yes · Shared: No** (a user-initiated transfer to the user's own email
provider is not "sharing") · **Processed ephemerally: No** · **Required: Yes** · **Purpose: App functionality**:

| Category | Data type | Why |
|---|---|---|
| Personal info | **Email address** | Recipient addresses and the sender address are sent to the email provider |
| Personal info | **Name** | Recipient names are used to personalise emails |
| Messages | **Emails** | The emails the user sends |
| Contacts | **Contacts** (optional, *not* required) | Only if the user imports phone contacts. They are read on the device, and their addresses go out only as recipients of emails the user sends. |
| Files and docs | **Files and docs** (optional) | Attachments the user adds to emails |

Leave everything else unticked: no location, financial, health, photos, audio, calendar, app activity, web browsing, app
info, device IDs or analytics.

## 4. Store listing (Grow → Store presence → Main store listing)

Copy from `fastlane/metadata/android/en-US/`:

- **App name:** `title.txt`
- **Short description:** `short_description.txt` (80 characters max)
- **Full description:** `full_description.txt`
- **App icon:** `images/icon.png`
- **Feature graphic:** `images/featureGraphic.png`
- **Phone screenshots:** everything in `images/phoneScreenshots/`, in order
- **Category:** Business (or Productivity). **Tags:** Email, Business, Productivity.
- **Contact details:** an email address users can reach you at (required; shown publicly), and the website
  `https://github.com/shahydlegacyofficial-creator/Automate-Email` if you like.

## 5. Upload the bundle and answer the permission questions

**Test and release → Testing → Closed testing → Create track** (or *Internal testing* first, if you want to try it
yourself in minutes):

1. **Create new release.** When asked about app signing, choose **Use Google-generated key** (Play App Signing). Your
   upload key only proves the uploads are yours.
2. Upload `LegacyAIEmailStudio-play.aab`.
3. Under **App bundle explorer → Downloads**, or in the release, upload `LegacyAIEmailStudio-play-mapping.txt` as the
   deobfuscation file. This makes crash reports readable.
4. **Release notes:** paste `changelogs/4.txt`.

Play Console will then ask about these permissions (*Policy and programmes → App content*):

- **Foreground service: special use** (`FOREGROUND_SERVICE_SPECIAL_USE`). Description to paste:

  > The app sends a user-started email campaign: one email to one recipient at a time, waiting a fixed interval the user
  > chooses (usually 60 seconds) between emails, for as long as the campaign lasts, which can be several hours. The
  > foreground service keeps that schedule running while the screen is off. It shows a notification with progress and
  > Pause/Stop buttons, starts only when the user taps Start (or approves a campaign an AI agent asked to start), and ends
  > when the last email is sent. No other foreground service type fits: dataSync is limited to 6 hours a day and is for
  > transferring data, and the work cannot be deferred because the interval between emails is part of what the user asked for.

  If Google asks for a video, record about 30 seconds: Compose → Recipients → Automation → Start, then show the
  notification. Upload it to YouTube as *unlisted* and paste the link.
- **Contacts** (`READ_CONTACTS`): used only when the user picks *Phone contacts* under **More → Outlook data → Read from**, to add them as recipients. Nothing is
  uploaded.
- **Notifications** (`POST_NOTIFICATIONS`): campaign progress, campaign finished, and AI-agent approval requests.

## 6. Testers, then production

1. In the closed test track, add testers by email (a Google Group works well) and share the opt-in link. Keep **at least
   12 testers opted in for 14 days**.
2. Then **Dashboard → Apply for production**, answer the short questions about your test, and roll the release out to
   production. Google's review usually takes from a day to a week.

## 7. Updates

Each new version needs a higher `versionCode` in `android/app/build.gradle.kts`. Push it, download the
**LegacyAIEmailStudio-play** artifact from the *Build Android app* run, and upload it as a new release. Every new version
must keep targeting the API level Google requires: API 36 from 31 August 2026, and the next one about a year later.

## Policy notes worth knowing

- **Bulk email:** Google Play allows email tools, but the listing and the app ask people to email only those who agreed.
  The app has a do-not-email list and never sends in bulk, only one recipient at a time.
- **Third-party names:** the description mentions Claude and Microsoft 365 only to say the app works with them. Don't
  use their logos in screenshots or the icon.
- **AI agents:** the app doesn't run an AI model itself. It is a tool the user's own agent can use, and every send waits
  for the user's approval by default.
