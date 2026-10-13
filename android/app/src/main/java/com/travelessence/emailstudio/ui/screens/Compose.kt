package com.travelessence.emailstudio.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.AppState
import com.travelessence.emailstudio.Screen
import com.travelessence.emailstudio.campaign.signatureHtml
import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Draft
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.Template
import com.travelessence.emailstudio.mail.backendLabel
import com.travelessence.emailstudio.ui.AttachmentsPanel
import com.travelessence.emailstudio.ui.EmailEditor
import com.travelessence.emailstudio.ui.HtmlView
import com.travelessence.emailstudio.ui.components.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDateTime

/** Sends a single email on a background thread. Returns an error message, or null on success. */
suspend fun sendOne(state: AppState, email: OutgoingEmail): String? = withContext(Dispatchers.IO) {
    try {
        state.makeSender().use { sender ->
            sender.open()
            sender.send(email)
        }
        null
    } catch (e: Exception) {
        e.message ?: e.javaClass.simpleName
    }
}

/** Subject field with an "insert field" menu that drops {first_name} etc. at the cursor. */
@Composable
fun SubjectField(value: TextFieldValue, onChange: (TextFieldValue) -> Unit, modifier: Modifier = Modifier, label: String = "Subject") {
    var open by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = true, modifier = modifier.fillMaxWidth(),
        trailingIcon = {
            Box {
                IconButton(onClick = { open = true }) { Icon(Icons.Filled.DataObject, "Insert field", tint = MaterialTheme.colorScheme.primary) }
                DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                    Html.PLACEHOLDERS.forEach { (key, name) ->
                        DropdownMenuItem(text = { Text("$name   {$key}") }, onClick = {
                            open = false
                            val token = "{$key}"
                            val t = value.text
                            val start = value.selection.min.coerceIn(0, t.length)
                            val end = value.selection.max.coerceIn(0, t.length)
                            onChange(TextFieldValue(t.substring(0, start) + token + t.substring(end), TextRange(start + token.length)))
                        })
                    }
                }
            }
        },
    )
}

@Composable
fun ComposeScreen(app: App) {
    val state = app.state
    val draft by state.draft.collectAsStateWithLifecycle()
    val version by state.draftVersion.collectAsStateWithLifecycle()
    val recipients by state.recipients.collectAsStateWithLifecycle()
    val settings by state.settings.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()

    var subject by remember(version) { mutableStateOf(TextFieldValue(state.draft.value.subject)) }
    var templates by remember { mutableStateOf(state.storage.loadTemplates()) }
    var selectedTemplate by remember { mutableStateOf(templates.firstOrNull()?.name.orEmpty()) }
    var dialog by remember { mutableStateOf<String?>(null) }   // preview | test | save | load | delete | new
    var sending by remember { mutableStateOf(false) }

    val ready = draft.subject.isNotBlank() && !Html.isBlank(draft.html)
    val sample = recipients.firstOrNull() ?: Recipient("customer@example.com", "Sarah Khan")

    Page {
        item { PageHeader("Compose email", "The message the automation sends to each customer. Fields like {first_name} are filled in for every recipient.") }
        item {
            SectionCard(title = "Message", action = { Pill(if (ready) "Ready · auto-saved" else "Incomplete", if (ready) Tone.Success else Tone.Warning) }) {
                SubjectField(subject, {
                    subject = it
                    state.updateDraft(state.draft.value.copy(subject = it.text))
                })
                EmailEditor(html = draft.html, version = version, onChange = { state.updateDraft(state.draft.value.copy(html = it)) })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Preview", Icons.Filled.Visibility, Modifier.weight(1f)) { dialog = "preview" }
                    SecondaryButton(if (sending) "Sending…" else "Send test", Icons.Filled.Science, Modifier.weight(1f), enabled = !sending) {
                        if (!ready) state.notify("Add a subject and some content first.") else dialog = "test"
                    }
                }
            }
        }
        item {
            SectionCard(title = "Attachments", subtitle = "JPG, PNG or PDF files sent with every email.") {
                AttachmentsPanel(draft.attachments) { state.updateDraft(state.draft.value.copy(attachments = it)) }
            }
        }
        item {
            SectionCard(title = "Templates", subtitle = "Save and reuse your best emails.") {
                if (templates.isEmpty()) Text("No saved templates yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                else Dropdown("Template", templates.map { it.name to it.name }, selectedTemplate) { selectedTemplate = it }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Load", Icons.Filled.FolderOpen, Modifier.weight(1f), enabled = templates.isNotEmpty()) { dialog = "load" }
                    SecondaryButton("Save", Icons.Filled.Save, Modifier.weight(1f)) {
                        if (draft.subject.isBlank() && Html.isBlank(draft.html)) state.notify("Write something before saving a template.") else dialog = "save"
                    }
                    IconButton(onClick = { dialog = "delete" }, enabled = templates.isNotEmpty()) { Icon(Icons.Filled.Delete, "Delete template") }
                }
                TextButton(onClick = { dialog = "new" }) {
                    Icon(Icons.Filled.Add, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Start a new blank email")
                }
            }
        }
        item {
            SectionCard(title = "Personalisation") {
                Text("{first_name} → Sarah\n{name} → Sarah Khan\n{email} → sarah@example.com\n\nIf a customer has no name, " +
                    "“${settings.nameFallback.ifBlank { "the fallback" }}” is used (change it in Settings).",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item {
            PrimaryButton("Continue to recipients", Icons.Filled.People, Modifier.fillMaxWidth()) { state.navigate(Screen.Recipients) }
        }
    }

    when (dialog) {
        "preview" -> PreviewDialog(draft.subject, draft.html, draft.attachments, sample, settings.nameFallback,
            signatureHtml(settings.signatureHtml)) { dialog = null }
        "test" -> TextInputDialog("Send a test email", "Sends via ${backendLabel(settings)}", "Test address", settings.testEmail,
            confirm = "Send", onDismiss = { dialog = null }) { address ->
            val to = address.trim().lowercase()
            if (!Recipients.isValid(to)) { state.notify("Please enter a valid email address."); return@TextInputDialog }
            if (to != settings.testEmail) state.saveSettings { it.copy(testEmail = to) }
            val r = Recipient(to, sample.name)
            val email = OutgoingEmail(listOf(to), "[TEST] " + Html.personalize(draft.subject, r, settings.nameFallback),
                Html.buildEmail(Html.personalize(draft.html, r, settings.nameFallback, true), signatureHtml(settings.signatureHtml)),
                draft.attachments)
            sending = true
            scope.launch {
                val error = sendOne(state, email)
                sending = false
                state.notify(error?.let { "Test email failed: $it" } ?: "Test email sent to $to")
            }
        }
        "save" -> TextInputDialog("Save template", null, "Template name", selectedTemplate.ifBlank { draft.subject.take(60) },
            confirm = "Save", onDismiss = { dialog = null }) { name ->
            val n = name.trim()
            if (n.isEmpty()) return@TextInputDialog
            val updated = listOf(Template(n, draft.subject, draft.html, draft.attachments, LocalDateTime.now().withNano(0).toString())) +
                templates.filter { it.name != n }
            state.storage.saveTemplates(updated)
            templates = updated
            selectedTemplate = n
            state.notify("Template “$n” saved")
        }
        "load" -> ConfirmDialog("Load template", "Replace the current email with “$selectedTemplate”?", "Load", { dialog = null }) {
            templates.firstOrNull { it.name == selectedTemplate }?.let {
                state.replaceDraft(Draft(it.subject, it.html, it.attachments))
                state.notify("Loaded “${it.name}”")
            }
        }
        "delete" -> ConfirmDialog("Delete template", "Delete the template “$selectedTemplate”?", "Delete", { dialog = null }) {
            val updated = templates.filter { it.name != selectedTemplate }
            state.storage.saveTemplates(updated)
            templates = updated
            selectedTemplate = updated.firstOrNull()?.name.orEmpty()
        }
        "new" -> ConfirmDialog("New email", "Clear the current subject, content and attachments?", "Clear", { dialog = null }) {
            state.replaceDraft(Draft())
        }
    }
}

@Composable
fun TextInputDialog(title: String, text: String?, label: String, initial: String, confirm: String,
                    onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var value by remember { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (text != null) Text(text, style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(value, { value = it }, label = { Text(label) }, singleLine = true)
            }
        },
        confirmButton = { TextButton(onClick = { onDismiss(); onConfirm(value) }) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun PreviewDialog(subject: String, html: String, attachments: List<Attachment>, recipient: Recipient, fallback: String,
                  signature: String, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().padding(12.dp), shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Preview", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                    IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, "Close") }
                }
                MetaRow("To", if (recipient.name.isNotBlank()) "${recipient.name} <${recipient.email}>" else recipient.email)
                MetaRow("Subject", Html.personalize(subject, recipient, fallback))
                if (attachments.isNotEmpty()) MetaRow("Files", attachments.joinToString { it.name })
                HtmlView(Html.buildEmail(Html.personalize(html, recipient, fallback, true), signature),
                    Modifier.fillMaxWidth().weight(1f))
            }
        }
    }
}

@Composable
private fun MetaRow(key: String, value: String) {
    Row {
        Text(key, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(70.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}
