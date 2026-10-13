package com.travelessence.emailstudio.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.campaign.signatureHtml
import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.SendResult
import com.travelessence.emailstudio.mail.backendLabel
import com.travelessence.emailstudio.ui.AttachmentsPanel
import com.travelessence.emailstudio.ui.EmailEditor
import com.travelessence.emailstudio.ui.components.*
import kotlinx.coroutines.launch
import java.time.LocalDateTime

private fun addresses(text: String): Pair<List<String>, List<String>> {
    val good = mutableListOf<String>()
    val bad = mutableListOf<String>()
    text.replace(';', ',').split(',').map { it.trim() }.filter { it.isNotEmpty() }.forEach { token ->
        val found = Recipients.EMAIL_FIND.find(token)?.value ?: token
        val email = Recipients.normalize(found)
        if (Recipients.isValid(email)) good += email else bad += email
    }
    return good to bad
}

@Composable
fun QuickSendScreen(app: App) {
    val state = app.state
    val settings by state.settings.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()

    var to by rememberSaveableText()
    var cc by rememberSaveableText()
    var bcc by rememberSaveableText()
    var subject by remember { mutableStateOf(TextFieldValue("")) }
    var html by remember { mutableStateOf("") }
    var version by remember { mutableIntStateOf(0) }
    var attachments by remember { mutableStateOf<List<Attachment>>(emptyList()) }
    var sending by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    var confirmNoSubject by remember { mutableStateOf(false) }

    fun clear() {
        to = ""; cc = ""; bcc = ""; subject = TextFieldValue(""); html = ""; attachments = emptyList(); version++
    }

    fun doSend() {
        val toList = addresses(to).first
        val ccList = addresses(cc).first
        val bccList = addresses(bcc).first
        val email = OutgoingEmail(toList, subject.text.trim(), Html.buildEmail(html, signatureHtml(settings.signatureHtml)),
            attachments, ccList, bccList)
        sending = true
        scope.launch {
            val error = sendOne(state, email)
            sending = false
            if (error != null) { problem = error; return@launch }
            val now = LocalDateTime.now().withNano(0).toString()
            val session = state.storage.newSession("manual", email.subject, settings.backend, 0, emptyList(), attachments).copy(
                total = toList.size, sent = toList.size, status = "completed", finished = now,
                results = toList.map { SendResult(it, "", "sent", now, "Sent manually") },
            )
            state.storage.saveSession(session)
            state.historyVersion.value++
            state.notify("Email sent to ${toList.joinToString()}")
            clear()
        }
    }

    fun validateAndSend() {
        val bad = addresses(to).second + addresses(cc).second + addresses(bcc).second
        when {
            bad.isNotEmpty() -> problem = "These addresses look invalid:\n\n" + bad.joinToString("\n")
            addresses(to).first.isEmpty() -> problem = "Add at least one recipient in the To field."
            Html.isBlank(html) && attachments.isEmpty() -> problem = "The email is empty."
            subject.text.isBlank() -> confirmNoSubject = true
            else -> doSend()
        }
    }

    Page {
        item { PageHeader("Write & send", "Compose a one-off email and send it straight away - for replies, quotes and individual follow-ups.") }
        item {
            SectionCard(title = "New message", action = {
                TextButton(onClick = {
                    val d = state.draft.value
                    subject = TextFieldValue(d.subject); html = d.html; attachments = d.attachments; version++
                }) { Text("Copy campaign draft") }
            }) {
                OutlinedTextField(to, { to = it }, Modifier.fillMaxWidth(), label = { Text("To") }, singleLine = true,
                    placeholder = { Text("customer@example.com, another@example.com") })
                OutlinedTextField(cc, { cc = it }, Modifier.fillMaxWidth(), label = { Text("Cc (optional)") }, singleLine = true)
                OutlinedTextField(bcc, { bcc = it }, Modifier.fillMaxWidth(), label = { Text("Bcc (optional)") }, singleLine = true)
                SubjectField(subject, { subject = it })
                EmailEditor(html = html, version = version, onChange = { html = it }, height = 380.dp)
            }
        }
        item {
            SectionCard(title = "Attachments", subtitle = "JPG, PNG or PDF.") {
                AttachmentsPanel(attachments) { attachments = it }
            }
        }
        item {
            SectionCard(title = "Send") {
                Text("Sending via ${backendLabel(settings)}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                PrimaryButton(if (sending) "Sending…" else "Send now", Icons.AutoMirrored.Filled.Send, Modifier.fillMaxWidth(),
                    enabled = !sending) { validateAndSend() }
                TextButton(onClick = { clear() }) { Icon(Icons.Filled.Delete, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Clear") }
                Text("Sent emails appear in History (and in your mailbox's Sent Items with Microsoft 365).",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }

    problem?.let { MessageDialog("Sending", it) { problem = null } }
    if (confirmNoSubject) {
        ConfirmDialog("No subject", "Send this email without a subject?", "Send", { confirmNoSubject = false }) { doSend() }
    }
}

@Composable
private fun rememberSaveableText(): MutableState<String> =
    androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf("") }
