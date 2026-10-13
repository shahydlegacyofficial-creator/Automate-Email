package com.travelessence.emailstudio.data

import android.content.Context
import android.provider.ContactsContract

/** Email contacts stored on the phone - including contacts synced by the Outlook app. */
object PhoneContacts {
    fun collect(context: Context, exclude: List<String>, progress: Progress): CollectResult {
        val agg = ContactAggregator(exclude, emptySet())
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Email.ADDRESS,
            ContactsContract.Contacts.DISPLAY_NAME_PRIMARY,
        )
        var scanned = 0
        context.contentResolver.query(
            ContactsContract.CommonDataKinds.Email.CONTENT_URI, projection, null, null,
            ContactsContract.Contacts.DISPLAY_NAME_PRIMARY + " ASC",
        )?.use { cursor ->
            val total = cursor.count
            while (cursor.moveToNext()) {
                scanned++
                agg.touch(cursor.getString(0).orEmpty(), cursor.getString(1).orEmpty(), null, "")
                if (scanned % 50 == 0) progress(scanned, total, "Reading phone contacts… $scanned/$total")
            }
        }
        return CollectResult(agg.result().sortedBy { it.name.ifEmpty { it.email }.lowercase() }, emptyList(), scanned)
    }
}
