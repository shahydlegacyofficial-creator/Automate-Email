package com.travelessence.emailstudio

import android.content.Context
import com.travelessence.emailstudio.core.Draft
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.Settings
import com.travelessence.emailstudio.core.Storage
import com.travelessence.emailstudio.mail.GraphClient
import com.travelessence.emailstudio.mail.MailSender
import com.travelessence.emailstudio.mail.TokenStore
import com.travelessence.emailstudio.mail.createSender
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.File

enum class Screen(val title: String) {
    Dashboard("Dashboard"),
    Compose("Compose email"),
    Recipients("Recipients"),
    Automation("Automation"),
    More("More"),
    QuickSend("Write & send"),
    Signature("Email signature"),
    Outlook("Outlook data"),
    History("History"),
    Agents("AI agents"),
    Settings("Settings"),
}

/** Application-wide state shared by every screen (the Android twin of the desktop AppState). */
class AppState(context: Context) {
    val storage = Storage(File(context.filesDir, "data"))
    val secrets = SecretStore(context)
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val _settings = MutableStateFlow(storage.loadSettings())
    val settings: StateFlow<Settings> = _settings

    private val _draft = MutableStateFlow(storage.loadDraft())
    val draft: StateFlow<Draft> = _draft
    /** Bumped when the draft is replaced from outside the composer (template, Outlook, new). */
    val draftVersion = MutableStateFlow(0)

    private val _recipients = MutableStateFlow(storage.loadRecipients())
    val recipients: StateFlow<List<Recipient>> = _recipients

    val historyVersion = MutableStateFlow(0)
    val messages = MutableSharedFlow<String>(extraBufferCapacity = 16)
    val navigation = MutableSharedFlow<Screen>(extraBufferCapacity = 4)

    private var draftSaveJob: Job? = null

    fun notify(message: String) {
        messages.tryEmit(message)
    }

    fun navigate(screen: Screen) {
        navigation.tryEmit(screen)
    }

    // ---------------------------------------------------------------- draft
    fun updateDraft(draft: Draft) {
        _draft.value = draft
        draftSaveJob?.cancel()
        draftSaveJob = scope.launch {
            delay(700)
            storage.saveDraft(draft)
        }
    }

    fun replaceDraft(draft: Draft) {
        draftSaveJob?.cancel()
        _draft.value = draft
        draftVersion.value++
        scope.launch { storage.saveDraft(draft) }
    }

    fun flush() {
        draftSaveJob?.cancel()
        storage.saveDraft(_draft.value)
    }

    // ---------------------------------------------------------------- recipients
    private fun persistRecipients(list: List<Recipient>) {
        _recipients.value = list
        scope.launch { storage.saveRecipients(list) }
    }

    fun addRecipients(incoming: List<Recipient>): Pair<Int, Int> {
        val (merged, added, dupes) = Recipients.merge(_recipients.value, incoming)
        persistRecipients(merged)
        return added to dupes
    }

    fun setRecipients(list: List<Recipient>) = persistRecipients(list)

    fun removeEmails(emails: Set<String>): Int {
        val before = _recipients.value.size
        persistRecipients(_recipients.value.filter { it.email !in emails })
        return before - _recipients.value.size
    }

    fun renameRecipient(email: String, name: String) {
        persistRecipients(_recipients.value.map { if (it.email == email) it.copy(name = name.trim()) else it })
    }

    // ---------------------------------------------------------------- settings & secrets
    fun saveSettings(transform: (Settings) -> Settings) {
        val updated = transform(_settings.value)
        _settings.value = updated
        scope.launch { storage.saveSettings(updated) }
    }

    var smtpPassword: String
        get() = secrets.get("smtp_password").orEmpty()
        set(value) = secrets.put("smtp_password", value)

    private val tokenStore = object : TokenStore {
        override fun load(): String? = secrets.get("ms_tokens")
        override fun save(value: String?) = secrets.put("ms_tokens", value)
    }

    /** The Microsoft app registration to sign in with: the user's own, else the one built into this release. */
    fun msClientId(s: Settings = _settings.value): String = s.msClientId.trim().ifEmpty { BuildConfig.MS_CLIENT_ID.trim() }

    fun graphClient(s: Settings = _settings.value): GraphClient? =
        msClientId(s).takeIf { it.isNotEmpty() }?.let { GraphClient(it, s.msTenant.trim().ifEmpty { "common" }, tokenStore) }

    fun makeSender(): MailSender = createSender(_settings.value, smtpPassword, graphClient())

    // ---------------------------------------------------------------- campaign readiness (screen + AI agents)
    /** Recipients that will really be emailed (do-not-email list removed) and how many were skipped. */
    fun eligible(list: List<Recipient> = _recipients.value): Pair<List<Recipient>, Int> {
        val suppression = Recipients.parseSuppression(_settings.value.suppressionList)
        val keep = list.filter { !Recipients.isSuppressed(it.email, suppression) }
        return keep to (list.size - keep.size)
    }

    /** Why a campaign can't start now, or null. */
    fun campaignProblem(draft: Draft = _draft.value, eligibleCount: Int = eligible().first.size): String? {
        val s = _settings.value
        return when {
            draft.subject.isBlank() || com.travelessence.emailstudio.core.Html.isBlank(draft.html) ->
                "Please write a subject and email content first."
            eligibleCount == 0 -> "Add at least one recipient first."
            draft.attachments.any { !File(it.path).isFile } -> "An attachment can no longer be found - remove it and add it again."
            s.backend == "microsoft" && graphClient()?.isSignedIn != true ->
                "Sign in to Microsoft 365 / Outlook in Settings, or choose another sending method."
            s.backend == "smtp" && s.smtpHost.isBlank() -> "Set up your SMTP server in Settings first."
            else -> null
        }
    }
}
