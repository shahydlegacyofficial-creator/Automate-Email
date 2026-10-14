package com.travelessence.emailstudio

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.Rect
import android.graphics.RectF
import android.util.Base64
import com.travelessence.emailstudio.core.Settings
import com.travelessence.emailstudio.core.Signature
import com.travelessence.emailstudio.core.SignatureConfig
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Android side of the email signature: recolours the white master icons (assets/signature_icons)
 * to the accent colour and returns them as data: URIs, which the senders embed as inline images.
 */
object SignatureAssets {
    private const val SIZE = 96
    private val cache = mutableMapOf<String, String>()

    private fun parse(color: String): Int = try {
        Color.parseColor(color)
    } catch (e: IllegalArgumentException) {
        Color.parseColor("#1E88E5")
    }

    @Synchronized
    fun icon(context: Context, kind: String, name: String, accent: String): String =
        cache.getOrPut("$kind-$name-$accent") {
            val master = context.assets.open("signature_icons/$name.png").use { BitmapFactory.decodeStream(it) }
            val out = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(out)
            val color = parse(accent)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
            if (kind == "social") {
                paint.color = color
                canvas.drawCircle(SIZE / 2f, SIZE / 2f, SIZE / 2f, paint)
                canvas.drawBitmap(master, null, RectF(SIZE * 0.2f, SIZE * 0.2f, SIZE * 0.8f, SIZE * 0.8f),
                    Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
            } else {
                paint.colorFilter = PorterDuffColorFilter(color, PorterDuff.Mode.SRC_IN)
                canvas.drawBitmap(master, null, Rect(0, 0, SIZE, SIZE), paint)
            }
            val bytes = ByteArrayOutputStream().also { out.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
            "data:image/png;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP)
        }

    fun logo(cfg: SignatureConfig): String {
        val file = File(cfg.logoPath)
        if (cfg.logoPath.isBlank() || !file.isFile) return ""
        val mime = if (file.name.lowercase().endsWith(".png")) "image/png" else "image/jpeg"
        return "data:$mime;base64," + Base64.encodeToString(file.readBytes(), Base64.NO_WRAP)
    }

    fun html(context: Context, cfg: SignatureConfig): String =
        Signature.build(cfg, { kind, name -> icon(context, kind, name, cfg.accent) }, logo(cfg))

    /** Signature to append to outgoing emails, or "" when switched off. */
    fun forSettings(context: Context, settings: Settings): String =
        if (settings.signature.enabled) html(context, settings.signature) else ""
}
