package com.travelessence.emailstudio.core

import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID

/** JSON persistence for settings, draft, recipients, templates and history. */
class Storage(val root: File) {
    private val json = Json { ignoreUnknownKeys = true; prettyPrint = false; encodeDefaults = true }
    private val lock = Any()

    init { root.mkdirs() }

    fun dir(name: String): File = File(root, name).apply { mkdirs() }

    private fun <T> read(file: File, serializer: KSerializer<T>, default: T): T = try {
        if (file.isFile) json.decodeFromString(serializer, file.readText()) else default
    } catch (e: Exception) {
        default
    }

    private fun <T> write(file: File, serializer: KSerializer<T>, value: T) = synchronized(lock) {
        file.parentFile?.mkdirs()
        val tmp = File(file.parentFile, file.name + ".tmp")
        tmp.writeText(json.encodeToString(serializer, value))
        if (!tmp.renameTo(file)) {
            file.delete()
            tmp.renameTo(file)
        }
    }

    fun loadSettings() = read(File(root, "settings.json"), Settings.serializer(), Settings())
    fun saveSettings(s: Settings) = write(File(root, "settings.json"), Settings.serializer(), s)

    fun loadDraft() = read(File(root, "draft.json"), Draft.serializer(), Draft())
    fun saveDraft(d: Draft) = write(File(root, "draft.json"), Draft.serializer(), d)

    fun loadRecipients() = read(File(root, "recipients.json"), ListSerializer(Recipient.serializer()), emptyList())
        .filter { Recipients.isValid(it.email) }
    fun saveRecipients(r: List<Recipient>) = write(File(root, "recipients.json"), ListSerializer(Recipient.serializer()), r)

    fun loadTemplates() = read(File(root, "templates.json"), ListSerializer(Template.serializer()), emptyList())
    fun saveTemplates(t: List<Template>) = write(File(root, "templates.json"), ListSerializer(Template.serializer()), t)

    // ------------------------------------------------------------- history
    private val history get() = dir("history")

    fun newSession(kind: String, subject: String, backend: String, interval: Int, queue: List<Recipient>,
                   attachments: List<Attachment>): Session {
        val now = LocalDateTime.now()
        return Session(
            id = now.format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS")),
            kind = kind, started = now.withNano(0).toString(), subject = subject, backend = backend,
            interval = interval, total = queue.size, queue = queue, attachments = attachments.map { it.name },
        )
    }

    fun saveSession(s: Session) = write(File(history, "${s.id}.json"), Session.serializer(), s)

    fun loadSessions(): List<Session> = (history.listFiles { f -> f.name.endsWith(".json") } ?: emptyArray())
        .mapNotNull { f -> runCatching { json.decodeFromString(Session.serializer(), f.readText()) }.getOrNull() }
        .sortedByDescending { it.started }

    fun deleteSession(id: String) { File(history, "$id.json").delete() }

    fun sessionCsv(s: Session): String = Csv.write(
        listOf(listOf("Time", "Email", "Name", "Status", "Details")) +
            s.results.map { listOf(it.time, it.email, it.name, it.status, it.message) }
    )

    data class Stats(val sent: Int, val failed: Int, val campaigns: Int)

    fun stats(): Stats {
        val all = loadSessions()
        return Stats(all.sumOf { it.sent }, all.sumOf { it.failed }, all.count { it.kind == "campaign" })
    }

    // ------------------------------------------------------------- attachments
    /** Copies a file into app storage so the attachment survives after the picker grant ends. */
    fun storeAttachment(name: String, mime: String, bytes: ByteArray): Attachment {
        val safe = name.replace(Regex("[\\\\/:*?\"<>|]"), "_").ifBlank { "attachment" }
        val folder = File(dir("attachments"), UUID.randomUUID().toString().take(8)).apply { mkdirs() }
        val file = File(folder, safe)
        file.writeBytes(bytes)
        return Attachment(safe, file.absolutePath, file.length(), mime)
    }
}
