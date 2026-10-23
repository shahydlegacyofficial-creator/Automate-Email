package com.travelessence.emailstudio.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.SignatureAssets
import com.travelessence.emailstudio.core.Signature
import com.travelessence.emailstudio.core.SignatureConfig
import com.travelessence.emailstudio.ui.Files
import com.travelessence.emailstudio.ui.HtmlView
import com.travelessence.emailstudio.ui.components.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val ACCENTS = listOf("#1E88E5", "#0B7A8F", "#14B8C9", "#16A34A", "#E0A526", "#EA580C", "#DC2626", "#7C3AED", "#111827")
private val SOCIAL_HINTS = mapOf(
    "facebook" to "yourpage", "instagram" to "@yourbusiness", "whatsapp" to "+1 555 010 2030",
    "tiktok" to "@yourbusiness", "linkedin" to "your-company", "youtube" to "@yourchannel", "x" to "@yourbusiness",
)

@Composable
fun SignatureScreen(app: App) {
    val state = app.state
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val saved by state.settings.collectAsStateWithLifecycle()
    var cfg by remember { mutableStateOf(saved.signature) }
    var preview by remember { mutableStateOf("") }
    var confirmReset by remember { mutableStateOf(false) }

    // Autosave and refresh the preview shortly after the last edit.
    LaunchedEffect(cfg) {
        delay(350)
        if (cfg != state.settings.value.signature) state.saveSettings { it.copy(signature = cfg) }
        val sig = withContext(Dispatchers.IO) { SignatureAssets.html(context, cfg) }
        preview = "<!DOCTYPE html><html><body style=\"margin:12px;background:#FFFFFF\">" +
            "<p style=\"font-family:Calibri,Arial;font-size:11pt;color:#1F2937\">Dear Sarah,<br><br>" +
            "Thank you for getting in touch…<br><br>Kind regards,</p>$sig</body></html>"
    }

    val logoPicker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            val path = withContext(Dispatchers.IO) {
                val mime = context.contentResolver.getType(uri) ?: "image/png"
                val ext = if (mime == "image/png") "png" else "jpg"
                val dir = state.storage.dir("signature")
                dir.listFiles()?.filter { it.name.startsWith("logo.") }?.forEach { it.delete() }
                File(dir, "logo.$ext").apply { writeBytes(Files.read(context, uri)) }.absolutePath
            }
            cfg = cfg.copy(logoPath = path)
            state.notify("Logo added to the signature")
        }
    }

    Page {
        item { PageHeader("Email signature", "Your contact details, social links and logo - added below every email.") }
        item {
            SectionCard(title = "Preview", subtitle = "How the signature appears under your emails.") {
                HtmlView(preview, Modifier.fillMaxWidth().height(330.dp))
            }
        }
        item {
            SectionCard(title = "Style") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Add to every email", style = MaterialTheme.typography.bodyLarge)
                        Text("Campaigns, test emails and Write & send", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(cfg.enabled, { cfg = cfg.copy(enabled = it) })
                }
                FieldLabel("Background")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("dark" to "Dark card", "light" to "Light").forEach { (key, label) ->
                        FilterChip(cfg.theme == key, { cfg = cfg.copy(theme = key) }, label = { Text(label) })
                    }
                }
                FieldLabel("Icon & link colour")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    ACCENTS.forEach { hex ->
                        val selected = cfg.accent.equals(hex, true)
                        Box(
                            Modifier.size(30.dp).clip(CircleShape).background(Color(android.graphics.Color.parseColor(hex)))
                                .border(if (selected) 3.dp else 1.dp,
                                    if (selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.outline, CircleShape)
                                .clickable { cfg = cfg.copy(accent = hex) }
                        )
                    }
                }
                OutlinedTextField(cfg.accent, { v ->
                    val hex = (if (v.startsWith("#")) v else "#$v").take(7).uppercase()
                    cfg = cfg.copy(accent = hex)
                }, Modifier.fillMaxWidth(), singleLine = true, label = { Text("Custom colour (hex)") })
            }
        }
        item {
            SectionCard(title = "Contact details", subtitle = "Leave a field empty to hide it.") {
                OutlinedTextField(cfg.name, { cfg = cfg.copy(name = it) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Name (optional)") })
                OutlinedTextField(cfg.title, { cfg = cfg.copy(title = it) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Job title (optional)") })
                OutlinedTextField(cfg.email, { cfg = cfg.copy(email = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Email") }, leadingIcon = { Icon(Icons.Filled.Email, null) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(cfg.phone, { cfg = cfg.copy(phone = it) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Phone") }, leadingIcon = { Icon(Icons.Filled.PhoneAndroid, null) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
                OutlinedTextField(cfg.address, { cfg = cfg.copy(address = it) }, Modifier.fillMaxWidth(),
                    label = { Text("Address") }, leadingIcon = { Icon(Icons.Filled.Place, null) }, minLines = 2)
                OutlinedTextField(cfg.website, { cfg = cfg.copy(website = it.trim()) }, Modifier.fillMaxWidth(), singleLine = true,
                    label = { Text("Website") }, leadingIcon = { Icon(Icons.Filled.Link, null) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            }
        }
        item {
            SectionCard(title = "Logo", subtitle = "PNG or JPG. A transparent PNG looks best on the dark card.") {
                val hasLogo = cfg.logoPath.isNotBlank() && File(cfg.logoPath).isFile
                Text(if (hasLogo) File(cfg.logoPath).name else "No logo selected", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Choose logo", Icons.Filled.Image, Modifier.weight(1f)) {
                        logoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                    }
                    if (hasLogo) SecondaryButton("Remove", Icons.Filled.Delete, Modifier.weight(1f)) { cfg = cfg.copy(logoPath = "") }
                }
                Text("Logo width: ${cfg.logoWidth} px", style = MaterialTheme.typography.bodySmall)
                Slider(cfg.logoWidth.toFloat(), { cfg = cfg.copy(logoWidth = it.toInt()) }, valueRange = 80f..360f, steps = 27)
            }
        }
        item {
            SectionCard(title = "Social media", subtitle = "Paste a full link or just the page name / handle. WhatsApp takes a phone number.") {
                Signature.SOCIALS.forEach { (key, label, _) ->
                    OutlinedTextField(cfg.socials[key].orEmpty(), { v -> cfg = cfg.copy(socials = cfg.socials + (key to v.trim())) },
                        Modifier.fillMaxWidth(), singleLine = true, label = { Text(label) },
                        placeholder = { Text(SOCIAL_HINTS[key].orEmpty()) })
                }
            }
        }
        item {
            TextButton(onClick = { confirmReset = true }) {
                Icon(Icons.Filled.Refresh, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Reset style")
            }
        }
    }

    if (confirmReset) {
        ConfirmDialog("Reset style", "Go back to the default colours and layout? Your details, logo and social links are kept.",
            "Reset", { confirmReset = false }) {
            val d = SignatureConfig()
            cfg = cfg.copy(enabled = d.enabled, theme = d.theme, accent = d.accent, logoWidth = d.logoWidth)
        }
    }
}
