package com.travelessence.emailstudio.data

import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Html
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.SendException
import com.travelessence.emailstudio.core.Settings
import com.travelessence.emailstudio.mail.GraphClient
import com.travelessence.emailstudio.mail.Mime
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Base64
import java.util.Date
import javax.mail.FetchProfile
import javax.mail.Folder
import javax.mail.Message
import javax.mail.Multipart
import javax.mail.Part
import javax.mail.UIDFolder
import javax.mail.internet.InternetAddress
import javax.mail.internet.MimeUtility
import javax.mail.search.AndTerm
import javax.mail.search.ComparisonTerm
import javax.mail.search.ReceivedDateTerm
import javax.mail.search.SentDateTerm

data class ContactRow(
    val email: String,
    var name: String = "",
    var company: String = "",
    var phone: String = "",
    var interactions: Int = 0,
    var lastContact: LocalDateTime? = null,
    var lastSubject: String = "",
)

data class MessageRow(
    val date: LocalDateTime?,
    val folder: String,
    val sender: String,
    val recipients: String,
    val subject: String,
    val attachments: Int,
    val id: String,
)

data class CollectOptions(
    val folder: String = "sent",            // sent | inbox | both | contacts
    val from: LocalDateTime? = null,
    val to: LocalDateTime? = null,
    val subjectContains: String = "",
    val exclude: List<String> = emptyList(),
    val maxItems: Int = 2000,
)

class CollectResult(
    val contacts: List<ContactRow>,
    val messages: List<MessageRow>,
    val scanned: Int,
)

data class LoadedMessage(
    val subject: String,
    val html: String,
    val attachments: List<Attachment>,
    val skipped: List<String>,
)

val FOLDER_CHOICES = listOf(
    "sent" to "Sent Items (emails you sent)",
    "inbox" to "Inbox (customers who emailed us)",
    "both" to "Sent Items + Inbox",
    "contacts" to "Contacts",
)

val ALLOWED_TEMPLATE_EXT = listOf(".jpg", ".jpeg", ".png", ".pdf")

typealias Progress = (current: Int, total: Int, message: String) -> Unit
typealias SaveAttachment = (name: String, mime: String, bytes: ByteArray) -> Attachment

/** Aggregates addresses into customer rows (shared by every source). */
class ContactAggregator(exclude: List<String>, own: Set<String>) {
    private val rows = linkedMapOf<String, ContactRow>()
    private val excluded = exclude.map { it.trim().lowercase() }.filter { it.isNotEmpty() } + own

    private fun isExcluded(email: String): Boolean {
        val domain = email.substringAfterLast('@')
        return excluded.any { it == email || it.removePrefix("@") == domain }
    }

    fun touch(rawEmail: String, name: String, `when`: LocalDateTime?, subject: String, company: String = "", phone: String = "") {
        val email = rawEmail.trim().lowercase()
        if (!Recipients.isValid(email) || isExcluded(email)) return
        val row = rows.getOrPut(email) { ContactRow(email) }
        val clean = name.trim().trim('"', '\'')
        if (clean.isNotEmpty() && '@' !in clean && row.name.isEmpty()) row.name = clean
        if (company.isNotBlank() && row.company.isEmpty()) row.company = company
        if (phone.isNotBlank() && row.phone.isEmpty()) row.phone = phone
        row.interactions++
        if (`when` != null && (row.lastContact == null || `when`.isAfter(row.lastContact))) {
            row.lastContact = `when`
            row.lastSubject = subject
        }
    }

    fun result(): List<ContactRow> = rows.values.sortedByDescending { it.lastContact ?: LocalDateTime.MIN }
}

// ======================================================================= Microsoft Graph
object GraphMailbox {
    private fun parseDate(s: String?): LocalDateTime? = try {
        if (s.isNullOrBlank() || s == "null") null
        else LocalDateTime.ofInstant(Instant.parse(s), ZoneId.systemDefault())
    } catch (e: Exception) { null }

    private fun iso(dt: LocalDateTime): String =
        dt.atZone(ZoneId.systemDefault()).withZoneSameInstant(ZoneOffset.UTC).format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'"))

    fun collect(client: GraphClient, o: CollectOptions, progress: Progress, cancelled: () -> Boolean): CollectResult {
        val own = setOf(client.me().lowercase())
        val agg = ContactAggregator(o.exclude, own)
        val messages = mutableListOf<MessageRow>()
        var scanned = 0
        val filter = o.subjectContains.trim().lowercase()

        if (o.folder == "contacts") {
            var url: String? = "/me/contacts?\$select=displayName,emailAddresses,companyName,mobilePhone,businessPhones&\$top=100"
            while (url != null && !cancelled()) {
                val page = client.request("GET", url)
                val items = page.optJSONArray("value")
                for (i in 0 until (items?.length() ?: 0)) {
                    val c = items!!.getJSONObject(i)
                    scanned++
                    val phones = c.optJSONArray("businessPhones")
                    val phone = c.optString("mobilePhone").takeIf { it.isNotBlank() && it != "null" }
                        ?: phones?.optString(0).orEmpty()
                    val addresses = c.optJSONArray("emailAddresses")
                    for (j in 0 until (addresses?.length() ?: 0)) {
                        agg.touch(addresses!!.getJSONObject(j).optString("address"), c.optString("displayName"),
                            null, "", c.optString("companyName").takeIf { it != "null" }.orEmpty(), phone)
                    }
                }
                progress(scanned, scanned, "Reading contacts… $scanned")
                url = page.optString("@odata.nextLink").takeIf { it.isNotBlank() && it != "null" }
            }
            return CollectResult(agg.result(), emptyList(), scanned)
        }

        val folders = when (o.folder) {
            "inbox" -> listOf("inbox")
            "both" -> listOf("sentitems", "inbox")
            else -> listOf("sentitems")
        }
        for (folder in folders) {
            val sent = folder == "sentitems"
            val field = if (sent) "sentDateTime" else "receivedDateTime"
            val clauses = mutableListOf<String>()
            clauses += "$field ge ${iso(o.from ?: LocalDateTime.now().minusYears(20))}"
            o.to?.let { clauses += "$field le ${iso(it)}" }
            var url: String? = "/me/mailFolders/$folder/messages?\$select=subject,sentDateTime,receivedDateTime,from," +
                "toRecipients,ccRecipients,bccRecipients,hasAttachments&\$orderby=" + GraphClient.encode("$field desc") +
                "&\$top=100&\$filter=" +
                GraphClient.encode(clauses.joinToString(" and "))
            val label = if (sent) "Sent Items" else "Inbox"
            while (url != null && !cancelled() && messages.size < o.maxItems) {
                val page = client.request("GET", url)
                val items = page.optJSONArray("value")
                for (i in 0 until (items?.length() ?: 0)) {
                    if (messages.size >= o.maxItems) break
                    val m = items!!.getJSONObject(i)
                    scanned++
                    val subject = m.optString("subject").takeIf { it != "null" }.orEmpty()
                    if (filter.isNotEmpty() && filter !in subject.lowercase()) continue
                    val date = parseDate(m.optString(field))
                    val to = mutableListOf<String>()
                    for (key in listOf("toRecipients", "ccRecipients", "bccRecipients")) {
                        val arr = m.optJSONArray(key) ?: continue
                        for (j in 0 until arr.length()) {
                            val ea = arr.getJSONObject(j).optJSONObject("emailAddress") ?: continue
                            val address = ea.optString("address").lowercase()
                            to += address
                            if (sent) agg.touch(address, ea.optString("name"), date, subject)
                        }
                    }
                    val fromEa = m.optJSONObject("from")?.optJSONObject("emailAddress")
                    val sender = fromEa?.optString("address").orEmpty().lowercase()
                    if (!sent) agg.touch(sender, fromEa?.optString("name").orEmpty(), date, subject)
                    messages += MessageRow(date, label, sender, to.joinToString("; "), subject,
                        if (m.optBoolean("hasAttachments")) 1 else 0, "graph:" + m.getString("id"))
                }
                progress(messages.size, o.maxItems, "Reading $label… ${messages.size} emails")
                url = page.optString("@odata.nextLink").takeIf { it.isNotBlank() && it != "null" }
            }
        }
        return CollectResult(agg.result(), messages.sortedByDescending { it.date ?: LocalDateTime.MIN }, scanned)
    }

    fun load(client: GraphClient, id: String, save: SaveAttachment): LoadedMessage {
        val path = "/me/messages/" + GraphClient.encode(id)
        val msg = client.request("GET", "$path?\$select=subject,body")
        var html = msg.optJSONObject("body")?.optString("content").orEmpty()
        if (msg.optJSONObject("body")?.optString("contentType").equals("text", true)) {
            html = "<p>" + Html.escape(html).replace("\n", "<br>") + "</p>"
        }
        val attachments = mutableListOf<Attachment>()
        val skipped = mutableListOf<String>()
        val inline = mutableMapOf<String, Pair<String, ByteArray>>()
        val list = client.request("GET", "$path/attachments").optJSONArray("value")
        for (i in 0 until (list?.length() ?: 0)) {
            val a = list!!.getJSONObject(i)
            val name = a.optString("name", "attachment")
            if (!a.has("contentBytes")) { skipped += name; continue }
            val bytes = Base64.getDecoder().decode(a.getString("contentBytes"))
            val mime = a.optString("contentType", "application/octet-stream")
            val cid = a.optString("contentId").takeIf { it.isNotBlank() && it != "null" }
            if (a.optBoolean("isInline") && cid != null) {
                inline[cid.trim('<', '>')] = mime to bytes
            } else if (ALLOWED_TEMPLATE_EXT.any { name.lowercase().endsWith(it) }) {
                attachments += save(name, mime, bytes)
            } else skipped += name
        }
        return LoadedMessage(msg.optString("subject"), Html.inlineCids(Html.bodyInner(html), inline), attachments, skipped)
    }
}

// ======================================================================= IMAP
object ImapMailbox {
    private fun local(d: Date?): LocalDateTime? = d?.toInstant()?.let { LocalDateTime.ofInstant(it, ZoneId.systemDefault()) }
    private fun date(dt: LocalDateTime): Date = Date.from(dt.atZone(ZoneId.systemDefault()).toInstant())

    private fun <T> withStore(settings: Settings, password: String, block: (javax.mail.Store) -> T): T {
        if (settings.imapHost.isBlank()) throw SendException("Set the IMAP server in Settings (SMTP section) to read your mailbox.")
        val store = Mime.smtpSession(settings).getStore("imaps")
        try {
            store.connect(settings.imapHost, settings.imapPort, settings.smtpUsername, password)
        } catch (e: Exception) {
            throw SendException("Could not sign in to ${settings.imapHost}: ${e.message}", e)
        }
        try {
            return block(store)
        } finally {
            runCatching { store.close() }
        }
    }

    fun collect(settings: Settings, password: String, o: CollectOptions, progress: Progress, cancelled: () -> Boolean): CollectResult =
        withStore(settings, password) { store ->
            val own = setOf(settings.smtpUsername.lowercase(), settings.smtpFromEmail.lowercase()) - ""
            val agg = ContactAggregator(o.exclude, own)
            val messages = mutableListOf<MessageRow>()
            var scanned = 0
            val filter = o.subjectContains.trim().lowercase()
            val folders = when (o.folder) {
                "inbox" -> listOf(store.getFolder("INBOX"))
                "both" -> listOfNotNull(Mime.findSentFolder(store), store.getFolder("INBOX"))
                "contacts" -> throw SendException("IMAP accounts don't include contacts - use Phone contacts or Microsoft 365.")
                else -> listOf(Mime.findSentFolder(store) ?: throw SendException("No Sent folder found in this mailbox."))
            }
            for (folder in folders) {
                if (cancelled()) break
                val sent = folder.fullName != "INBOX"
                folder.open(Folder.READ_ONLY)
                try {
                    val fromDate = date(o.from ?: LocalDateTime.now().minusYears(20))
                    val toDate = date(o.to ?: LocalDateTime.now().plusDays(1))
                    val term = if (sent) AndTerm(SentDateTerm(ComparisonTerm.GE, fromDate), SentDateTerm(ComparisonTerm.LE, toDate))
                    else AndTerm(ReceivedDateTerm(ComparisonTerm.GE, fromDate), ReceivedDateTerm(ComparisonTerm.LE, toDate))
                    val found = folder.search(term).takeLast(o.maxItems).reversed()
                    val fp = FetchProfile().apply { add(FetchProfile.Item.ENVELOPE); add(FetchProfile.Item.CONTENT_INFO); add(UIDFolder.FetchProfileItem.UID) }
                    found.chunked(100).forEach { batch ->
                        if (cancelled()) return@forEach
                        folder.fetch(batch.toTypedArray(), fp)
                        for (m in batch) {
                            scanned++
                            val subject = m.subject.orEmpty()
                            if (filter.isNotEmpty() && filter !in subject.lowercase()) continue
                            val whenDt = local(if (sent) m.sentDate else (m.receivedDate ?: m.sentDate))
                            val to = listOf(Message.RecipientType.TO, Message.RecipientType.CC)
                                .flatMap { type -> m.getRecipients(type)?.toList() ?: emptyList() }
                                .filterIsInstance<InternetAddress>()
                            if (sent) to.forEach { agg.touch(it.address.orEmpty(), it.personal.orEmpty(), whenDt, subject) }
                            val from = m.from?.filterIsInstance<InternetAddress>()?.firstOrNull()
                            if (!sent && from != null) agg.touch(from.address.orEmpty(), from.personal.orEmpty(), whenDt, subject)
                            val uid = (folder as UIDFolder).getUID(m)
                            messages += MessageRow(whenDt, folder.name, from?.address.orEmpty().lowercase(),
                                to.joinToString("; ") { it.address.orEmpty().lowercase() }, subject,
                                if (m.contentType?.lowercase()?.startsWith("multipart/mixed") == true) 1 else 0,
                                "imap:${folder.fullName}\n$uid")
                        }
                        progress(scanned, found.size, "Reading ${folder.name}… $scanned/${found.size}")
                    }
                } finally {
                    runCatching { folder.close(false) }
                }
            }
            CollectResult(agg.result(), messages.sortedByDescending { it.date ?: LocalDateTime.MIN }, scanned)
        }

    fun load(settings: Settings, password: String, id: String, save: SaveAttachment): LoadedMessage =
        withStore(settings, password) { store ->
            val (folderName, uidText) = id.split("\n", limit = 2)
            val folder = store.getFolder(folderName)
            folder.open(Folder.READ_ONLY)
            try {
                val msg = (folder as UIDFolder).getMessageByUID(uidText.toLong())
                    ?: throw SendException("That email no longer exists in the mailbox.")
                var html: String? = null
                var text: String? = null
                val inline = mutableMapOf<String, Pair<String, ByteArray>>()
                val attachments = mutableListOf<Attachment>()
                val skipped = mutableListOf<String>()

                fun walk(part: Part) {
                    val type = part.contentType?.lowercase().orEmpty()
                    val name = part.fileName?.let { runCatching { MimeUtility.decodeText(it) }.getOrDefault(it) }
                    when {
                        part.isMimeType("multipart/*") -> {
                            val mp = part.content as Multipart
                            for (i in 0 until mp.count) walk(mp.getBodyPart(i))
                        }
                        Part.ATTACHMENT.equals(part.disposition, true) || (name != null && !type.startsWith("image/")) -> {
                            val n = name ?: "attachment"
                            if (ALLOWED_TEMPLATE_EXT.any { n.lowercase().endsWith(it) }) {
                                attachments += save(n, type.substringBefore(';'), part.inputStream.readBytes())
                            } else skipped += n
                        }
                        type.startsWith("image/") -> {
                            val cid = (part.getHeader("Content-ID")?.firstOrNull() ?: name ?: "").trim('<', '>', ' ')
                            if (cid.isNotEmpty()) inline[cid] = type.substringBefore(';') to part.inputStream.readBytes()
                        }
                        type.startsWith("text/html") && html == null -> html = part.content.toString()
                        type.startsWith("text/plain") && text == null -> text = part.content.toString()
                    }
                }
                walk(msg)
                val body = html?.let { Html.bodyInner(it) }
                    ?: ("<p>" + Html.escape(text.orEmpty()).replace("\n", "<br>") + "</p>")
                LoadedMessage(msg.subject.orEmpty(), Html.inlineCids(body, inline), attachments, skipped)
            } finally {
                runCatching { folder.close(false) }
            }
        }
}

fun formatDate(dt: LocalDateTime?): String = dt?.format(DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm")) ?: ""
