package com.travelessence.emailstudio.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Login
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.BuildConfig
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.mail.DeviceCode
import com.travelessence.emailstudio.mail.SmtpSender
import com.travelessence.emailstudio.ui.components.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicBoolean

private val SMTP_PRESETS = listOf(
    Triple("Microsoft 365 / Outlook.com", "smtp.office365.com", "outlook.office365.com"),
    Triple("Gmail / Google Workspace", "smtp.gmail.com", "imap.gmail.com"),
    Triple("Zoho Mail", "smtp.zoho.com", "imap.zoho.com"),
    Triple("Yahoo Mail", "smtp.mail.yahoo.com", "imap.mail.yahoo.com"),
)

@Composable
fun SettingsScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val saved by state.settings.collectAsStateWithLifecycle()
    var s by remember { mutableStateOf(saved) }
    var password by remember { mutableStateOf(state.smtpPassword) }
    var interval by remember { mutableStateOf(saved.intervalSeconds.toString()) }
    var port by remember { mutableStateOf(saved.smtpPort.toString()) }
    var imapPort by remember { mutableStateOf(saved.imapPort.toString()) }
    var signedIn by remember { mutableStateOf(state.graphClient()?.isSignedIn == true) }
    var deviceCode by remember { mutableStateOf<DeviceCode?>(null) }
    var signInJob by remember { mutableStateOf<Job?>(null) }
    val cancelSignIn = remember { AtomicBoolean(false) }
    var testing by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(saved.theme) { s = s.copy(theme = saved.theme) }

    fun save(notify: Boolean = true) {
        val updated = s.copy(
            intervalSeconds = interval.toIntOrNull()?.coerceIn(10, 3600) ?: 60,
            smtpPort = port.toIntOrNull() ?: 587,
            imapPort = imapPort.toIntOrNull() ?: 993,
        )
        if (updated.testEmail.isNotBlank() && !Recipients.isValid(updated.testEmail.trim())) {
            problem = "The test email address is not valid."; return
        }
        s = updated
        state.saveSettings { updated.copy(msAccount = it.msAccount) }
        state.smtpPassword = password
        if (notify) state.notify("Settings saved")
    }

    fun signIn() {
        save(notify = false)
        val client = state.graphClient(s) ?: run { problem = "Enter the Application (client) ID first."; return }
        cancelSignIn.set(false)
        signInJob = scope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching {
                    val code = client.startDeviceLogin()
                    withContext(Dispatchers.Main) { deviceCode = code }
                    client.completeDeviceLogin(code) { cancelSignIn.get() }
                }
            }
            deviceCode = null
            outcome.onSuccess { account ->
                state.saveSettings { it.copy(msAccount = account) }
                signedIn = true
                state.notify("Signed in as $account")
            }.onFailure { if (!cancelSignIn.get()) problem = it.message }
        }
    }

    Page {
        item { PageHeader("Settings", "Choose how emails are sent and set your campaign defaults.") }
        item {
            SectionCard(title = "Sending method") {
                listOf(
                    Triple("microsoft", "Microsoft 365 / Outlook.com (recommended)", "Sends from your Outlook mailbox through Microsoft's secure sign-in. Emails are saved in Sent Items - just like the Outlook app."),
                    Triple("smtp", "SMTP / IMAP email account", "Any provider that allows SMTP (Gmail, Zoho, hosting providers). Uses an app password."),
                    Triple("simulate", "Simulation - practise without sending", "Runs campaigns exactly as normal but no email leaves the phone."),
                ).forEach { (key, title, text) ->
                    Row(Modifier.fillMaxWidth().selectable(s.backend == key) { s = s.copy(backend = key) }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.Top) {
                        RadioButton(s.backend == key, { s = s.copy(backend = key) })
                        Column(Modifier.padding(top = 12.dp)) {
                            Text(title, style = MaterialTheme.typography.bodyLarge)
                            Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        if (s.backend == "microsoft") {
            item {
                SectionCard(title = "Microsoft 365 / Outlook account",
                    action = { Pill(if (signedIn) "Signed in" else "Not signed in", if (signedIn) Tone.Success else Tone.Warning) }) {
                    if (signedIn && saved.msAccount.isNotBlank()) Text("Signed in as ${saved.msAccount}", fontWeight = FontWeight.SemiBold)
                    OutlinedTextField(s.msClientId, { s = s.copy(msClientId = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("Application (client) ID") }, placeholder = { Text("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx") })
                    OutlinedTextField(s.msTenant, { s = s.copy(msTenant = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("Tenant") }, supportingText = { Text("“common” works for most accounts, or use your organisation's tenant ID / domain") })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PrimaryButton(if (signedIn) "Sign in again" else "Sign in", Icons.AutoMirrored.Filled.Login, Modifier.weight(1f),
                            enabled = signInJob?.isActive != true) { signIn() }
                        if (signedIn) SecondaryButton("Sign out", Icons.AutoMirrored.Filled.Logout, Modifier.weight(1f)) {
                            state.graphClient()?.signOut(); state.saveSettings { it.copy(msAccount = "") }; signedIn = false
                        }
                    }
                    Text(
                        "One-time setup (by you or your IT admin): in the Microsoft Entra admin center create an App registration " +
                            "(any account type), under Authentication enable “Allow public client flows”, and add the delegated " +
                            "Microsoft Graph permissions Mail.Send, Mail.ReadWrite, Contacts.Read and User.Read. " +
                            "Paste its Application (client) ID above. Full steps are in the README.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (s.backend == "smtp") {
            item {
                SectionCard(title = "SMTP / IMAP account") {
                    Dropdown("Provider preset", SMTP_PRESETS.map { it.second to it.first } + ("" to "Custom server"),
                        SMTP_PRESETS.firstOrNull { it.second == s.smtpHost }?.second ?: "") { host ->
                        val preset = SMTP_PRESETS.firstOrNull { it.second == host }
                        if (preset != null) {
                            s = s.copy(smtpHost = preset.second, smtpSecurity = "starttls", imapHost = preset.third)
                            port = "587"; imapPort = "993"
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(s.smtpHost, { s = s.copy(smtpHost = it.trim()) }, Modifier.weight(2f), singleLine = true, label = { Text("SMTP server") })
                        OutlinedTextField(port, { port = it.filter(Char::isDigit).take(5) }, Modifier.weight(1f), singleLine = true,
                            label = { Text("Port") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                    }
                    Dropdown("Security", listOf("starttls" to "STARTTLS (port 587)", "ssl" to "SSL/TLS (port 465)", "none" to "None (not recommended)"),
                        s.smtpSecurity) { s = s.copy(smtpSecurity = it) }
                    OutlinedTextField(s.smtpUsername, { s = s.copy(smtpUsername = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("Username") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                    OutlinedTextField(password, { password = it }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Password / app password") },
                        visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        supportingText = { Text("Stored encrypted on this phone") })
                    OutlinedTextField(s.smtpFromEmail, { s = s.copy(smtpFromEmail = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("From email") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                    OutlinedTextField(s.smtpFromName, { s = s.copy(smtpFromName = it) }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("From name") })
                    FieldLabel("IMAP (optional) - saves a copy in Sent and powers Outlook data")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(s.imapHost, { s = s.copy(imapHost = it.trim()) }, Modifier.weight(2f), singleLine = true, label = { Text("IMAP server") })
                        OutlinedTextField(imapPort, { imapPort = it.filter(Char::isDigit).take(5) }, Modifier.weight(1f), singleLine = true,
                            label = { Text("Port") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                    }
                    SecondaryButton(if (testing) "Testing…" else "Test connection", Icons.Filled.CheckCircle, Modifier.fillMaxWidth(), enabled = !testing) {
                        val test = s.copy(smtpPort = port.toIntOrNull() ?: 587)
                        testing = true
                        scope.launch {
                            val error = withContext(Dispatchers.IO) {
                                runCatching { SmtpSender(test, password).use { it.open() } }.exceptionOrNull()
                            }
                            testing = false
                            problem = error?.message ?: "Connection and login succeeded."
                        }
                    }
                }
            }
        }
        item {
            SectionCard(title = "Campaign defaults") {
                OutlinedTextField(interval, { interval = it.filter(Char::isDigit).take(4) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Time between emails (seconds)") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                OutlinedTextField(s.nameFallback, { s = s.copy(nameFallback = it) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Name if unknown") }, placeholder = { Text("Valued Customer") })
                OutlinedTextField(s.testEmail, { s = s.copy(testEmail = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Send test emails to") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(s.signatureHtml, { s = s.copy(signatureHtml = it) }, Modifier.fillMaxWidth().heightIn(min = 100.dp),
                    label = { Text("Signature (added to every email)") },
                    placeholder = { Text("Kind regards,\nTravel Essence\n+44 20 1234 5678 · travelessence.com") })
            }
        }
        item {
            SectionCard(title = "Do-not-email list", subtitle = "Addresses or whole domains (e.g. @competitor.com) that campaigns always skip - use it for unsubscribe requests.") {
                OutlinedTextField(s.suppressionList, { s = s.copy(suppressionList = it) }, Modifier.fillMaxWidth().heightIn(min = 120.dp),
                    placeholder = { Text("unsubscribed@example.com\n@competitor.com") })
            }
        }
        item { PrimaryButton("Save settings", Icons.Filled.Save, Modifier.fillMaxWidth()) { save() } }
        item {
            SectionCard(title = "About") {
                Text("Travel Essence Email Studio for Android v${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyMedium)
                Text("Settings, drafts and history are stored privately on this phone. Passwords and sign-in tokens are encrypted with the Android Keystore.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }

    deviceCode?.let { code ->
        AlertDialog(
            onDismissRequest = {},
            title = { Text("Sign in to Microsoft") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("1. Tap “Open sign-in page”.\n2. Enter this code and sign in with the Travel Essence mailbox.\n3. Come back - this finishes automatically.")
                    Text(code.userCode, fontFamily = FontFamily.Monospace, fontSize = 30.sp, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(10.dp))
                        Text("Waiting for you to approve…", style = MaterialTheme.typography.bodySmall)
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("Microsoft sign-in code", code.userCode))
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(code.verificationUri))) }
                }) { Text("Copy code & open sign-in page") }
            },
            dismissButton = {
                TextButton(onClick = { cancelSignIn.set(true); signInJob?.cancel(); deviceCode = null }) { Text("Cancel") }
            },
        )
    }
    problem?.let { MessageDialog("Settings", it) { problem = null } }
}
