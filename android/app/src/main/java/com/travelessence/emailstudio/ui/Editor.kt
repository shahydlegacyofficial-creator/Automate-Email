package com.travelessence.emailstudio.ui

import android.annotation.SuppressLint
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.FormatAlignLeft
import androidx.compose.material.icons.automirrored.filled.FormatAlignRight
import androidx.compose.material.icons.automirrored.filled.FormatListBulleted
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DataObject
import androidx.compose.material.icons.filled.FormatAlignCenter
import androidx.compose.material.icons.filled.FormatAlignJustify
import androidx.compose.material.icons.filled.FormatBold
import androidx.compose.material.icons.filled.FormatClear
import androidx.compose.material.icons.filled.FormatColorFill
import androidx.compose.material.icons.filled.FormatColorText
import androidx.compose.material.icons.filled.FormatItalic
import androidx.compose.material.icons.filled.FormatListNumbered
import androidx.compose.material.icons.filled.FormatSize
import androidx.compose.material.icons.filled.FormatStrikethrough
import androidx.compose.material.icons.filled.FormatUnderlined
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.travelessence.emailstudio.App
import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.ui.components.SecondaryButton
import com.travelessence.emailstudio.ui.components.humanSize
import com.travelessence.emailstudio.ui.theme.LocalTones
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

private data class FormatState(
    val bold: Boolean = false, val italic: Boolean = false, val underline: Boolean = false, val strike: Boolean = false,
    val ul: Boolean = false, val ol: Boolean = false,
    val left: Boolean = false, val center: Boolean = false, val right: Boolean = false, val justify: Boolean = false,
)

private val FONTS = listOf("Calibri", "Arial", "Georgia", "Times New Roman", "Verdana", "Tahoma", "Trebuchet MS", "Courier New")
private val SIZES = listOf("Small" to "2", "Normal" to "3", "Large" to "4", "Extra large" to "5", "Huge" to "6")
private val PALETTE = listOf(
    "#000000", "#1F2937", "#475569", "#94A3B8", "#FFFFFF", "#0B7A8F",
    "#14B8C9", "#1D4ED8", "#7C3AED", "#DB2777", "#DC2626", "#EA580C",
    "#E0A526", "#FACC15", "#16A34A", "#065F46", "#FEF3C7", "#DCFCE7",
)

/** Rich-text email editor: a contenteditable WebView with a native formatting toolbar. */
@SuppressLint("SetJavaScriptEnabled", "ClickableViewAccessibility", "JavascriptInterface")
@Composable
fun EmailEditor(
    html: String,
    version: Int,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    height: Dp = 440.dp,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val latestHtml by rememberUpdatedState(html)
    val latestOnChange by rememberUpdatedState(onChange)
    var webView by remember { mutableStateOf<WebView?>(null) }
    var loaded by remember { mutableStateOf(false) }
    var fmt by remember { mutableStateOf(FormatState()) }
    var dialog by remember { mutableStateOf<String?>(null) }   // link | color | highlight

    fun js(code: String) { webView?.evaluateJavascript(code, null) }
    fun cmd(name: String, value: String? = null) =
        js(if (value == null) "cmd('$name')" else "cmd('$name', ${JSONObject.quote(value)})")

    val bridge = remember {
        object {
            private val main = Handler(Looper.getMainLooper())
            @JavascriptInterface
            fun onChange(value: String) { main.post { latestOnChange(value) } }
            @JavascriptInterface
            fun onState(json: String) {
                main.post {
                    runCatching {
                        val o = JSONObject(json)
                        fmt = FormatState(o.optBoolean("bold"), o.optBoolean("italic"), o.optBoolean("underline"),
                            o.optBoolean("strike"), o.optBoolean("ul"), o.optBoolean("ol"), o.optBoolean("left"),
                            o.optBoolean("center"), o.optBoolean("right"), o.optBoolean("justify"))
                    }
                }
            }
        }
    }

    LaunchedEffect(version, loaded) {
        if (loaded) js("setHtml(${JSONObject.quote(latestHtml)})")
    }

    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            val data = withContext(Dispatchers.IO) { runCatching { Files.imageDataUri(context, uri) }.getOrNull() }
            if (data != null) js("insertImage(${JSONObject.quote(data)})")
            else App.instance.state.notify("That picture could not be opened")
        }
    }

    val tones = LocalTones.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .border(1.dp, tones.border, RoundedCornerShape(12.dp))
                .horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Tool(Icons.AutoMirrored.Filled.Undo, "Undo") { cmd("undo") }
            Tool(Icons.AutoMirrored.Filled.Redo, "Redo") { cmd("redo") }
            Sep()
            MenuTool(Icons.Filled.TextFields, "Font", FONTS.map { it to it }) { cmd("fontName", it) }
            MenuTool(Icons.Filled.FormatSize, "Size", SIZES) { cmd("fontSize", it) }
            Sep()
            Tool(Icons.Filled.FormatBold, "Bold", fmt.bold) { cmd("bold") }
            Tool(Icons.Filled.FormatItalic, "Italic", fmt.italic) { cmd("italic") }
            Tool(Icons.Filled.FormatUnderlined, "Underline", fmt.underline) { cmd("underline") }
            Tool(Icons.Filled.FormatStrikethrough, "Strikethrough", fmt.strike) { cmd("strikeThrough") }
            Tool(Icons.Filled.FormatColorText, "Text colour") { dialog = "color" }
            Tool(Icons.Filled.FormatColorFill, "Highlight") { dialog = "highlight" }
            Sep()
            Tool(Icons.AutoMirrored.Filled.FormatAlignLeft, "Align left", fmt.left) { cmd("justifyLeft") }
            Tool(Icons.Filled.FormatAlignCenter, "Center", fmt.center) { cmd("justifyCenter") }
            Tool(Icons.AutoMirrored.Filled.FormatAlignRight, "Align right", fmt.right) { cmd("justifyRight") }
            Tool(Icons.Filled.FormatAlignJustify, "Justify", fmt.justify) { cmd("justifyFull") }
            Sep()
            Tool(Icons.AutoMirrored.Filled.FormatListBulleted, "Bulleted list", fmt.ul) { cmd("insertUnorderedList") }
            Tool(Icons.Filled.FormatListNumbered, "Numbered list", fmt.ol) { cmd("insertOrderedList") }
            Sep()
            Tool(Icons.Filled.Link, "Insert link") { dialog = "link" }
            Tool(Icons.Filled.Image, "Insert picture") {
                imagePicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }
            Tool(Icons.Filled.FormatClear, "Clear formatting") { cmd("removeFormat") }
            Sep()
            MenuTool(Icons.Filled.DataObject, "Insert field", Html.PLACEHOLDERS.map { (k, v) -> "{$k}" to "$v   {$k}" },
                tint = MaterialTheme.colorScheme.primary) { js("insertText(${JSONObject.quote(it)})") }
        }

        AndroidView(
            modifier = Modifier.fillMaxWidth().height(height).clip(RoundedCornerShape(12.dp))
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp)),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = false
                    setBackgroundColor(android.graphics.Color.WHITE)
                    addJavascriptInterface(bridge, "Android")
                    webViewClient = object : WebViewClient() {
                        override fun onPageFinished(view: WebView?, url: String?) { loaded = true }
                        override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?) = true
                    }
                    setOnTouchListener { v, e ->
                        if (e.action == MotionEvent.ACTION_DOWN) v.parent?.requestDisallowInterceptTouchEvent(true)
                        false
                    }
                    loadUrl("file:///android_asset/editor.html")
                    webView = this
                }
            },
        )
    }

    when (dialog) {
        "link" -> LinkDialog(onDismiss = { dialog = null }) { url, text -> js("link(${JSONObject.quote(url)}, ${JSONObject.quote(text)})") }
        "color", "highlight" -> {
            val highlight = dialog == "highlight"
            ColorDialog(if (highlight) "Highlight colour" else "Text colour", onDismiss = { dialog = null }) { color ->
                cmd(if (highlight) "hiliteColor" else "foreColor", color)
            }
        }
    }
}

@Composable
private fun Tool(icon: ImageVector, description: String, active: Boolean = false, onClick: () -> Unit) {
    val bg = if (active) LocalTones.current.accentSoft else Color.Transparent
    IconButton(onClick = onClick, modifier = Modifier.size(40.dp)) {
        Box(Modifier.size(34.dp).clip(RoundedCornerShape(8.dp)).background(bg), contentAlignment = Alignment.Center) {
            Icon(icon, description, tint = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.size(20.dp))
        }
    }
}

@Composable
private fun MenuTool(icon: ImageVector, description: String, options: List<Pair<String, String>>,
                     tint: Color = MaterialTheme.colorScheme.onSurface, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { open = true }, modifier = Modifier.size(40.dp)) {
            Icon(icon, description, tint = tint, modifier = Modifier.size(20.dp))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (value, label) ->
                DropdownMenuItem(text = { Text(label) }, onClick = { open = false; onPick(value) })
            }
        }
    }
}

@Composable
private fun Sep() {
    Box(Modifier.padding(horizontal = 3.dp).width(1.dp).height(22.dp).background(MaterialTheme.colorScheme.outline))
}

@Composable
private fun LinkDialog(onDismiss: () -> Unit, onInsert: (String, String) -> Unit) {
    var url by remember { mutableStateOf("https://") }
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Insert link") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(url, { url = it }, label = { Text("Web address") }, singleLine = true)
                OutlinedTextField(text, { text = it }, label = { Text("Text to show (if nothing is selected)") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                var u = url.trim()
                if (u.isNotEmpty() && u != "https://") {
                    if ("://" !in u && !u.startsWith("mailto:")) u = if ('@' in u && '/' !in u) "mailto:$u" else "https://$u"
                    onInsert(u, text.trim())
                }
                onDismiss()
            }) { Text("Insert") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ColorDialog(title: String, onDismiss: () -> Unit, onPick: (String) -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            LazyVerticalGrid(GridCells.Fixed(6), horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(PALETTE) { hex ->
                    Box(
                        Modifier.size(36.dp).clip(CircleShape)
                            .background(Color(android.graphics.Color.parseColor(hex)))
                            .border(1.dp, MaterialTheme.colorScheme.outline, CircleShape)
                            .clickable { onPick(hex); onDismiss() }
                    )
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
}

/** Read-only rendering of an email, used by Preview. */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun HtmlView(html: String, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = false
                setBackgroundColor(android.graphics.Color.WHITE)
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?) = true
                }
            }
        },
        update = { it.loadDataWithBaseURL(null, html, "text/html", "utf-8", null) },
    )
}

/** Attachment list with an "Add files" picker limited to JPG, PNG and PDF. */
@Composable
fun AttachmentsPanel(attachments: List<Attachment>, onChange: (List<Attachment>) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state = App.instance.state
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) scope.launch {
            val (added, rejected) = withContext(Dispatchers.IO) { Files.importAttachments(context, state.storage, uris) }
            val names = attachments.map { it.name }.toSet()
            val merged = attachments + added.filter { it.name !in names }
            onChange(merged)
            if (rejected.isNotEmpty()) state.notify("Only JPG, PNG and PDF can be attached. Skipped: ${rejected.joinToString()}")
            if (merged.sumOf { it.size } > Files.WARN_BYTES) {
                state.notify("Attachments total ${humanSize(merged.sumOf { it.size })} - many mail servers reject emails over 20 MB.")
            }
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (attachments.isEmpty()) {
            Text("No attachments · JPG, PNG or PDF", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        attachments.forEach { a ->
            val missing = !File(a.path).isFile
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(start = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(if (a.mime == "application/pdf") Icons.Filled.PictureAsPdf else Icons.Filled.Image, null,
                    tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(a.name, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
                    Text(if (missing) "File missing" else humanSize(a.size), style = MaterialTheme.typography.bodySmall,
                        color = if (missing) LocalTones.current.danger else MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = { onChange(attachments - a) }) { Icon(Icons.Filled.Close, "Remove") }
            }
        }
        if (attachments.isNotEmpty()) {
            Text("${attachments.size} file${if (attachments.size == 1) "" else "s"} · ${humanSize(attachments.sumOf { it.size })}",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        SecondaryButton("Add files", Icons.Filled.AttachFile) { picker.launch(Files.ATTACHMENT_MIMES) }
    }
}
