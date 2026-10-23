package com.travelessence.emailstudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.ui.components.*
import com.travelessence.emailstudio.ui.theme.LocalTones

/** First run: who is sending, and what the app does. Everything here can be changed later. */
@Composable
fun WelcomeScreen(app: App) {
    val state = app.state
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var website by remember { mutableStateOf("") }
    var problem by remember { mutableStateOf<String?>(null) }

    fun finish(save: Boolean) {
        val address = Recipients.normalize(email)
        if (save && address.isNotEmpty() && !Recipients.isValid(address)) {
            problem = "That email address doesn't look right."
            return
        }
        state.saveSettings { s ->
            if (!save) s.copy(onboarded = true)
            else s.copy(
                onboarded = true,
                businessName = name.trim(),
                smtpFromName = s.smtpFromName.ifBlank { name.trim() },
                smtpFromEmail = s.smtpFromEmail.ifBlank { address },
                testEmail = s.testEmail.ifBlank { address },
                signature = s.signature.copy(
                    name = s.signature.name.ifBlank { name.trim() },
                    email = s.signature.email.ifBlank { address },
                    phone = s.signature.phone.ifBlank { phone.trim() },
                    website = s.signature.website.ifBlank { website.trim() },
                ),
            )
        }
    }

    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).systemBarsPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Box(
            Modifier.size(64.dp).background(
                Brush.linearGradient(listOf(LocalTones.current.gradientStart, LocalTones.current.gradientEnd)),
                MaterialTheme.shapes.large,
            ),
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Filled.MarkEmailRead, null, tint = Color.White, modifier = Modifier.size(34.dp)) }
        Text("Welcome to Legacy AI Email Studio", style = MaterialTheme.typography.headlineSmall)
        Text("Write an email once and send it to each of your customers one at a time - by hand, or with your " +
            "AI agent doing the work while you approve every send.", style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        SectionCard {
            Feature(Icons.Filled.Bolt, "Campaigns, one email at a time", "Personalised with each customer's name, with a pause between sends and a live progress bar.")
            Feature(Icons.Filled.SmartToy, "Works with your AI agent", "Claude, Legacy AI or any MCP-compatible assistant can write and send through the app - only with your approval.")
            Feature(Icons.Filled.Science, "Try it safely first", "The app starts in Simulation mode: everything works, but no email is sent until you connect your mailbox in Settings.")
        }

        SectionCard(title = "About you", subtitle = "Used for your email signature and as the sender name. You can change it any time.") {
            OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Your name or business name") }, leadingIcon = { Icon(Icons.Filled.Storefront, null) })
            OutlinedTextField(email, { email = it.trim() }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Your email address") }, leadingIcon = { Icon(Icons.Filled.Email, null) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
            OutlinedTextField(phone, { phone = it }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Phone (optional)") }, leadingIcon = { Icon(Icons.Filled.PhoneAndroid, null) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
            OutlinedTextField(website, { website = it.trim() }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("Website (optional)") }, leadingIcon = { Icon(Icons.Filled.Link, null) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        }

        PrimaryButton("Get started", Icons.Filled.ArrowForward, Modifier.fillMaxWidth()) { finish(true) }
        TextButton(onClick = { finish(false) }, modifier = Modifier.align(Alignment.CenterHorizontally)) { Text("Skip for now") }
    }
    problem?.let { MessageDialog("Welcome", it) { problem = null } }
}

@Composable
private fun Feature(icon: ImageVector, title: String, text: String) {
    Row(verticalAlignment = Alignment.Top) {
        IconBadge(icon, Tone.Accent, 40)
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
