package com.travelessence.emailstudio.core

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/**
 * Minimal .xlsx reader (all sheets, shared + inline strings, numbers) and writer.
 * Avoids pulling the multi-megabyte Apache POI into the app.
 */
object Xlsx {
    private val CELL = Regex("<c\\b([^>]*?)(?:/>|>(.*?)</c>)", RegexOption.DOT_MATCHES_ALL)
    private val ROW = Regex("<row\\b[^>]*?(?:/>|>(.*?)</row>)", RegexOption.DOT_MATCHES_ALL)
    private val ATTR_R = Regex("\\br=\"([A-Z]+)\\d+\"")
    private val ATTR_T = Regex("\\bt=\"([^\"]+)\"")
    private val VALUE = Regex("<v>(.*?)</v>", RegexOption.DOT_MATCHES_ALL)
    private val TEXT = Regex("<t\\b[^>]*>(.*?)</t>", RegexOption.DOT_MATCHES_ALL)
    private val SI = Regex("<si>(.*?)</si>", RegexOption.DOT_MATCHES_ALL)

    fun unescape(s: String): String = s
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"")
        .replace("&apos;", "'").replace("&amp;", "&")

    private fun escape(s: String): String = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
        .replace(Regex("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]"), "")

    private fun columnIndex(letters: String): Int = letters.fold(0) { acc, ch -> acc * 26 + (ch - 'A' + 1) } - 1

    fun read(input: InputStream): List<List<List<String>>> {
        val files = mutableMapOf<String, String>()
        ZipInputStream(input).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                val name = entry.name
                if (name == "xl/sharedStrings.xml" || (name.startsWith("xl/worksheets/sheet") && name.endsWith(".xml"))) {
                    files[name] = zip.readBytes().toString(Charsets.UTF_8)
                }
                entry = zip.nextEntry
            }
        }
        val shared = files["xl/sharedStrings.xml"]?.let { xml ->
            SI.findAll(xml).map { si -> TEXT.findAll(si.groupValues[1]).joinToString("") { unescape(it.groupValues[1]) } }.toList()
        } ?: emptyList()

        val sheetNames = files.keys.filter { it.startsWith("xl/worksheets/") }
            .sortedBy { it.removePrefix("xl/worksheets/sheet").removeSuffix(".xml").toIntOrNull() ?: 0 }
        return sheetNames.map { sheet ->
            ROW.findAll(files.getValue(sheet)).map { row ->
                val cells = sortedMapOf<Int, String>()
                var next = 0
                CELL.findAll(row.groupValues[1]).forEach { c ->
                    val attrs = c.groupValues[1]
                    val body = c.groupValues[2]
                    val col = ATTR_R.find(attrs)?.groupValues?.get(1)?.let(::columnIndex) ?: next
                    next = col + 1
                    val type = ATTR_T.find(attrs)?.groupValues?.get(1)
                    val raw = VALUE.find(body)?.groupValues?.get(1)
                    val value = when (type) {
                        "s" -> raw?.toIntOrNull()?.let { shared.getOrNull(it) } ?: ""
                        "inlineStr" -> TEXT.findAll(body).joinToString("") { unescape(it.groupValues[1]) }
                        "str", "e" -> unescape(raw ?: "")
                        else -> raw?.let { v -> v.toDoubleOrNull()?.let { d -> if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString() else v } ?: unescape(v) } ?: ""
                    }
                    cells[col] = value
                }
                val width = (cells.keys.maxOrNull() ?: -1) + 1
                List(width) { cells[it] ?: "" }
            }.toList()
        }
    }

    fun read(bytes: ByteArray): List<List<List<String>>> = read(ByteArrayInputStream(bytes))

    private fun colName(i: Int): String {
        var n = i + 1
        val sb = StringBuilder()
        while (n > 0) {
            val r = (n - 1) % 26
            sb.insert(0, ('A' + r))
            n = (n - 1) / 26
        }
        return sb.toString()
    }

    fun write(rows: List<List<String>>, sheetName: String = "Sheet1"): ByteArray {
        val widths = IntArray(rows.maxOfOrNull { it.size } ?: 0)
        rows.take(500).forEach { r -> r.forEachIndexed { i, v -> widths[i] = maxOf(widths[i], minOf(v.length + 2, 60)) } }
        val sheet = buildString {
            append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>")
            append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">")
            if (widths.isNotEmpty()) {
                append("<cols>")
                widths.forEachIndexed { i, w -> append("<col min=\"${i + 1}\" max=\"${i + 1}\" width=\"${maxOf(w, 8)}\" customWidth=\"1\"/>") }
                append("</cols>")
            }
            append("<sheetData>")
            rows.forEachIndexed { ri, row ->
                append("<row r=\"${ri + 1}\">")
                row.forEachIndexed { ci, v ->
                    val style = if (ri == 0) " s=\"1\"" else ""
                    append("<c r=\"${colName(ci)}${ri + 1}\" t=\"inlineStr\"$style><is><t xml:space=\"preserve\">${escape(v)}</t></is></c>")
                }
                append("</row>")
            }
            append("</sheetData></worksheet>")
        }
        val parts = linkedMapOf(
            "[Content_Types].xml" to "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/></Types>",
            "_rels/.rels" to "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>",
            "xl/workbook.xml" to "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets><sheet name=\"${escape(sheetName)}\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>",
            "xl/_rels/workbook.xml.rels" to "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/></Relationships>",
            "xl/styles.xml" to "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><fonts count=\"2\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font><font><b/><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts><fills count=\"2\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill></fills><borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs><cellXfs count=\"2\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/><xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\"/></cellXfs></styleSheet>",
            "xl/worksheets/sheet1.xml" to sheet,
        )
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            for ((name, content) in parts) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(content.toByteArray(Charsets.UTF_8))
                zip.closeEntry()
            }
        }
        return out.toByteArray()
    }
}
