package com.travelessence.emailstudio.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Base64
import com.travelessence.emailstudio.core.Attachment
import com.travelessence.emailstudio.core.Csv
import com.travelessence.emailstudio.core.Recipients
import com.travelessence.emailstudio.core.Storage
import com.travelessence.emailstudio.core.Xlsx
import java.io.ByteArrayOutputStream

object Files {
    val ATTACHMENT_MIMES = arrayOf("image/jpeg", "image/png", "application/pdf")
    private val ALLOWED_EXT = listOf(".jpg", ".jpeg", ".png", ".pdf")
    const val WARN_BYTES = 20L * 1024 * 1024

    fun displayName(context: Context, uri: Uri): String {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0)?.let { return it }
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "file"
    }

    fun read(context: Context, uri: Uri): ByteArray =
        context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: ByteArray(0)

    fun write(context: Context, uri: Uri, bytes: ByteArray) {
        context.contentResolver.openOutputStream(uri, "wt")?.use { it.write(bytes) }
    }

    /** Copies picked files into app storage. Returns (attachments, rejected file names). */
    fun importAttachments(context: Context, storage: Storage, uris: List<Uri>): Pair<List<Attachment>, List<String>> {
        val added = mutableListOf<Attachment>()
        val rejected = mutableListOf<String>()
        for (uri in uris) {
            val name = displayName(context, uri)
            val mime = context.contentResolver.getType(uri) ?: ""
            val ok = ALLOWED_EXT.any { name.lowercase().endsWith(it) } || mime in ATTACHMENT_MIMES
            if (!ok) { rejected += name; continue }
            val fixedMime = when {
                mime in ATTACHMENT_MIMES -> mime
                name.lowercase().endsWith(".pdf") -> "application/pdf"
                name.lowercase().endsWith(".png") -> "image/png"
                else -> "image/jpeg"
            }
            added += storage.storeAttachment(name, fixedMime, read(context, uri))
        }
        return added to rejected
    }

    /** Reads CSV / TXT / XLSX recipient files. */
    fun parseRecipients(context: Context, uri: Uri): Pair<String, Recipients.Result> {
        val name = displayName(context, uri)
        val bytes = read(context, uri)
        val lower = name.lowercase()
        val isZip = bytes.size > 4 && bytes[0] == 'P'.code.toByte() && bytes[1] == 'K'.code.toByte()
        if (lower.endsWith(".xlsx") || lower.endsWith(".xlsm") || isZip) {
            val combined = Recipients.Result()
            Xlsx.read(bytes).forEach { sheet ->
                val r = Recipients.parseRows(sheet)
                r.invalid.forEach { if (it !in combined.invalid) combined.invalid += it }
                combined.duplicates += r.duplicates
                r.recipients.forEach { combined.add(it.email, it.name) }
            }
            return name to combined
        }
        val text = decode(bytes)
        return name to if (lower.endsWith(".csv") || lower.endsWith(".tsv")) Recipients.parseRows(Csv.parse(text))
        else Recipients.parseText(text)
    }

    private fun decode(bytes: ByteArray): String {
        if (bytes.size >= 2 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xFE.toByte()) return String(bytes, Charsets.UTF_16LE)
        val utf8 = Charsets.UTF_8.newDecoder()
        return try {
            utf8.decode(java.nio.ByteBuffer.wrap(bytes)).toString().removePrefix("﻿")
        } catch (e: Exception) {
            String(bytes, charset("windows-1252"))
        }
    }

    /** Downscales a picked photo and returns it as a data: URI for inline use in the email body. */
    fun imageDataUri(context: Context, uri: Uri, maxWidth: Int = 1200): String? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        if (bounds.outWidth <= 0) return null
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxWidth) sample *= 2
        val bmp = context.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        val scaled = if (bmp.width > maxWidth) Bitmap.createScaledBitmap(bmp, maxWidth, bmp.height * maxWidth / bmp.width, true) else bmp
        val png = context.contentResolver.getType(uri) == "image/png"
        val out = ByteArrayOutputStream()
        scaled.compress(if (png) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG, 85, out)
        return "data:${if (png) "image/png" else "image/jpeg"};base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }
}
