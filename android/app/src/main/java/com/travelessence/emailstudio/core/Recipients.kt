package com.travelessence.emailstudio.core

/**
 * Parsing, validating and de-duplicating recipient addresses from pasted text,
 * CSV / TXT files and spreadsheet rows. Mirrors the desktop app's behaviour.
 */
object Recipients {
    val EMAIL_FIND = Regex("[A-Za-z0-9._%+'\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}")
    private val EMAIL_VALID = Regex(
        "^(?!\\.)(?!.*\\.\\.)[A-Za-z0-9._%+'\\-]+(?<!\\.)" +
            "@(?:[A-Za-z0-9](?:[A-Za-z0-9\\-]{0,61}[A-Za-z0-9])?\\.)+[A-Za-z]{2,24}$"
    )
    private val ANGLE = Regex("(?:\"?([^\"<>,;\\n\\t|]*?)\"?\\s*)?<\\s*([^<>\\s]+@[^<>\\s]+)\\s*>")
    private val SPLIT = Regex("[,;\\t|]")
    private val LETTER = Regex("[A-Za-z\\u00C0-\\u024F\\u0400-\\u04FF\\u0600-\\u06FF]")

    private val EMAIL_HEADERS = listOf("email", "e-mail", "email address", "e-mail address", "mail", "email id")
    private val NAME_HEADERS = listOf(
        "name", "full name", "fullname", "customer name", "client name", "contact name",
        "customer", "client", "contact", "display name", "guest name",
    )
    private val FIRST_HEADERS = listOf("first name", "firstname", "first", "given name", "forename")
    private val LAST_HEADERS = listOf("last name", "lastname", "last", "surname", "family name")

    fun normalize(value: String): String =
        value.trim().trim('<', '>', '"', '\'').trim().trimEnd('.').lowercase()

    fun isValid(value: String): Boolean = EMAIL_VALID.matches(value.trim())

    fun cleanName(value: String): String {
        val v = value.trim().trim('"', '\'').trim()
        if (v.isEmpty() || '@' in v || !LETTER.containsMatchIn(v)) return ""
        return v.replace(Regex("\\s+"), " ")
    }

    class Result {
        val recipients = mutableListOf<Recipient>()
        val invalid = mutableListOf<String>()
        var duplicates = 0
        private val seen = mutableSetOf<String>()

        fun add(rawEmail: String, name: String) {
            val email = normalize(rawEmail)
            if (email.isEmpty()) return
            if (!isValid(email)) {
                if (email !in invalid) invalid += email
                return
            }
            if (email in seen) {
                duplicates++
                if (name.isNotBlank()) {
                    val i = recipients.indexOfFirst { it.email == email && it.name.isEmpty() }
                    if (i >= 0) recipients[i] = recipients[i].copy(name = cleanName(name))
                }
                return
            }
            seen += email
            recipients += Recipient(email, cleanName(name))
        }
    }

    private fun parseLine(line: String, result: Result) {
        val text = line.trim()
        if (text.isEmpty() || '@' !in text) return

        val angles = ANGLE.findAll(text).toList()
        if (angles.isNotEmpty()) {
            for (m in angles) result.add(m.groupValues[2], m.groupValues[1])
            val rest = ANGLE.replace(text, " ")
            EMAIL_FIND.findAll(rest).forEach { result.add(it.value, "") }
            return
        }

        val tokens = text.split(SPLIT).map { it.trim() }.filter { it.isNotEmpty() }
        val found = EMAIL_FIND.findAll(text).map { it.value }.toList()
        if (found.size == 1) {
            val name = tokens.map { cleanName(it) }.firstOrNull { it.isNotEmpty() }.orEmpty()
            result.add(found[0], name)
        } else {
            found.forEach { result.add(it, "") }
        }

        for (raw in text.split(Regex("[\\s,;\\t|]+"))) {
            val token = raw.trim('<', '>', '"', '\'', '(', ')', '[', ']')
            if ('@' in token && !EMAIL_FIND.containsMatchIn(token)) {
                val bad = normalize(token)
                if (bad.isNotEmpty() && bad !in result.invalid) result.invalid += bad
            }
        }
    }

    fun parseText(text: String): Result {
        val result = Result()
        text.lines().forEach { parseLine(it, result) }
        return result
    }

    private fun findHeader(row: List<String>, names: List<String>): Int {
        val lowered = row.map { it.trim().lowercase() }
        for (wanted in names) {
            val i = lowered.indexOf(wanted)
            if (i >= 0) return i
        }
        return -1
    }

    fun parseRows(input: List<List<String?>>): Result {
        val rows = input.map { r -> r.map { (it ?: "").trim() } }.filter { r -> r.any { it.isNotEmpty() } }
        val result = Result()
        if (rows.isEmpty()) return result

        val header = rows[0]
        var emailIdx = findHeader(header, EMAIL_HEADERS)
        if (emailIdx < 0) {
            emailIdx = header.indexOfFirst { "mail" in it.lowercase() && '@' !in it }
        }
        if (emailIdx >= 0) {
            val nameIdx = findHeader(header, NAME_HEADERS)
            val firstIdx = findHeader(header, FIRST_HEADERS)
            val lastIdx = findHeader(header, LAST_HEADERS)
            for (row in rows.drop(1)) {
                if (emailIdx >= row.size) continue
                val cell = row[emailIdx]
                val found = EMAIL_FIND.findAll(cell).map { it.value }.toList()
                    .ifEmpty { if ('@' in cell) listOf(cell) else emptyList() }
                var name = row.getOrNull(nameIdx).orEmpty()
                if (name.isEmpty()) {
                    name = "${row.getOrNull(firstIdx).orEmpty()} ${row.getOrNull(lastIdx).orEmpty()}".trim()
                }
                found.forEach { result.add(it, if (found.size == 1) name else "") }
            }
            return result
        }
        rows.forEach { parseLine(it.joinToString(","), result) }
        return result
    }

    /** Merge [incoming] into [existing]; returns (merged, added, duplicates). */
    fun merge(existing: List<Recipient>, incoming: List<Recipient>): Triple<List<Recipient>, Int, Int> {
        val merged = existing.toMutableList()
        val index = merged.withIndex().associate { it.value.email to it.index }.toMutableMap()
        var added = 0
        var dupes = 0
        for (r in incoming) {
            val i = index[r.email]
            if (i != null) {
                dupes++
                if (r.name.isNotEmpty() && merged[i].name.isEmpty()) merged[i] = merged[i].copy(name = r.name)
                continue
            }
            index[r.email] = merged.size
            merged += r
            added++
        }
        return Triple(merged, added, dupes)
    }

    fun parseSuppression(text: String): Set<String> =
        text.split(Regex("[\\s,;]+")).map { it.trim().lowercase() }.filter { it.isNotEmpty() }.toSet()

    fun isSuppressed(email: String, entries: Set<String>): Boolean {
        val e = email.lowercase()
        if (e in entries) return true
        val domain = e.substringAfterLast('@')
        return "@$domain" in entries || domain in entries
    }

    fun toCsv(recipients: List<Recipient>): String = Csv.write(
        listOf(listOf("Email", "Name")) + recipients.map { listOf(it.email, it.name) }
    )
}
