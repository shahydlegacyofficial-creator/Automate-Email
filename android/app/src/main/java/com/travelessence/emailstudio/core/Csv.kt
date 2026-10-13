package com.travelessence.emailstudio.core

/** Small RFC-4180 style CSV reader / writer with delimiter sniffing. */
object Csv {
    fun sniffDelimiter(text: String): Char {
        val sample = text.lineSequence().take(10).joinToString("\n")
        return listOf(',', ';', '\t', '|').maxByOrNull { d -> sample.count { it == d } } ?: ','
    }

    fun parse(text: String, delimiter: Char = sniffDelimiter(text)): List<List<String>> {
        val rows = mutableListOf<List<String>>()
        val row = mutableListOf<String>()
        val cell = StringBuilder()
        var inQuotes = false
        var i = 0
        val src = text.removePrefix("﻿")
        while (i < src.length) {
            val c = src[i]
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < src.length && src[i + 1] == '"') {
                        cell.append('"'); i++
                    } else inQuotes = false
                } else cell.append(c)
            } else when (c) {
                '"' -> inQuotes = true
                delimiter -> { row += cell.toString(); cell.clear() }
                '\r' -> {}
                '\n' -> { row += cell.toString(); cell.clear(); rows += row.toList(); row.clear() }
                else -> cell.append(c)
            }
            i++
        }
        if (cell.isNotEmpty() || row.isNotEmpty()) {
            row += cell.toString()
            rows += row.toList()
        }
        return rows
    }

    private fun quote(value: String): String =
        if (value.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) "\"" + value.replace("\"", "\"\"") + "\""
        else value

    fun write(rows: List<List<String>>): String =
        "﻿" + rows.joinToString("\r\n") { r -> r.joinToString(",") { quote(it) } } + "\r\n"
}
