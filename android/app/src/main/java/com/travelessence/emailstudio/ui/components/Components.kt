package com.travelessence.emailstudio.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.travelessence.emailstudio.ui.theme.LocalTones

enum class Tone { Accent, Success, Danger, Warning, Neutral }

@Composable
fun toneColors(tone: Tone): Pair<Color, Color> {
    val t = LocalTones.current
    return when (tone) {
        Tone.Accent -> t.accentSoft to MaterialTheme.colorScheme.primary
        Tone.Success -> t.successSoft to t.success
        Tone.Danger -> t.dangerSoft to t.danger
        Tone.Warning -> t.warningSoft to t.warning
        Tone.Neutral -> MaterialTheme.colorScheme.surfaceVariant to MaterialTheme.colorScheme.onSurfaceVariant
    }
}

@Composable
fun SectionCard(
    modifier: Modifier = Modifier,
    title: String? = null,
    subtitle: String? = null,
    action: (@Composable RowScope.() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, LocalTones.current.border),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (title != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.titleMedium)
                        if (subtitle != null) {
                            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    if (action != null) Row(verticalAlignment = Alignment.CenterVertically, content = action)
                }
            }
            content()
        }
    }
}

@Composable
fun Pill(text: String, tone: Tone = Tone.Neutral) {
    val (bg, fg) = toneColors(tone)
    Text(
        text,
        modifier = Modifier.clip(RoundedCornerShape(50)).background(bg).padding(horizontal = 10.dp, vertical = 3.dp),
        color = fg, style = MaterialTheme.typography.labelSmall,
    )
}

@Composable
fun IconBadge(icon: ImageVector, tone: Tone = Tone.Accent, size: Int = 40) {
    val (bg, fg) = toneColors(tone)
    Box(Modifier.size(size.dp).clip(RoundedCornerShape(12.dp)).background(bg), contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = fg, modifier = Modifier.size((size * 0.5).dp))
    }
}

@Composable
fun StatCard(label: String, value: String, icon: ImageVector, tone: Tone, modifier: Modifier = Modifier, caption: String = "") {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, LocalTones.current.border),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            IconBadge(icon, tone, 38)
            Spacer(Modifier.width(12.dp))
            Column {
                Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(value, style = MaterialTheme.typography.headlineSmall)
                if (caption.isNotEmpty()) {
                    Text(caption, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable
fun Banner(text: String, tone: Tone = Tone.Warning, icon: ImageVector = Icons.Filled.Warning) {
    val (bg, fg) = toneColors(tone)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Icon(icon, null, tint = fg, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
fun FieldLabel(text: String) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun PageHeader(title: String, subtitle: String) {
    Column(Modifier.padding(bottom = 4.dp)) {
        Text(title, style = MaterialTheme.typography.headlineMedium)
        Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun PrimaryButton(text: String, icon: ImageVector? = null, modifier: Modifier = Modifier, enabled: Boolean = true,
                  colors: androidx.compose.material3.ButtonColors = ButtonDefaults.buttonColors(), onClick: () -> Unit) {
    Button(onClick = onClick, modifier = modifier, enabled = enabled, shape = RoundedCornerShape(10.dp), colors = colors,
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp)) {
        if (icon != null) {
            Icon(icon, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
        }
        Text(text, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun SecondaryButton(text: String, icon: ImageVector? = null, modifier: Modifier = Modifier, enabled: Boolean = true,
                    color: Color = Color.Unspecified, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier, enabled = enabled, shape = RoundedCornerShape(10.dp),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
        border = BorderStroke(1.dp, if (color == Color.Unspecified) MaterialTheme.colorScheme.outline else color)) {
        val tint = if (color == Color.Unspecified) MaterialTheme.colorScheme.onSurface else color
        if (icon != null) {
            Icon(icon, null, Modifier.size(18.dp), tint = tint); Spacer(Modifier.width(8.dp))
        }
        Text(text, fontWeight = FontWeight.SemiBold, color = tint)
    }
}

/** Read-only dropdown field. */
@Composable
fun <T> Dropdown(label: String, options: List<Pair<T, String>>, selected: T, modifier: Modifier = Modifier, onSelect: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedTextField(
            value = options.firstOrNull { it.first == selected }?.second.orEmpty(),
            onValueChange = {}, readOnly = true, label = { Text(label) }, singleLine = true,
            trailingIcon = { Icon(Icons.Filled.ArrowDropDown, null) },
            modifier = Modifier.fillMaxWidth(),
        )
        Box(Modifier.matchParentSize().clip(RoundedCornerShape(4.dp)).clickable { open = true })
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (value, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onSelect(value) })
            }
        }
    }
}

@Composable
fun ConfirmDialog(title: String, text: String, confirm: String = "Yes", onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = { onDismiss(); onConfirm() }) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun MessageDialog(title: String, text: String, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(title) }, text = { Text(text) },
        confirmButton = { TextButton(onClick = onDismiss) { Text("OK") } },
    )
}

@Composable
fun Gap(h: Int = 8) = Spacer(Modifier.height(h.dp))

fun humanSize(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    else -> "%.1f MB".format(bytes / 1024.0 / 1024.0)
}

fun formatDuration(seconds: Long): String {
    val s = seconds.coerceAtLeast(0)
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return when {
        h > 0 -> "${h}h ${"%02d".format(m)}m"
        m > 0 -> "${m}m ${"%02d".format(sec)}s"
        else -> "${sec}s"
    }
}
