package com.travelessence.emailstudio

import com.travelessence.emailstudio.campaign.CampaignEngine
import com.travelessence.emailstudio.core.OutgoingEmail
import com.travelessence.emailstudio.core.Recipient
import com.travelessence.emailstudio.core.SendException
import com.travelessence.emailstudio.core.Storage
import com.travelessence.emailstudio.mail.MailSender
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

class CampaignEngineTest {
    class Recording(private val failFor: Set<String> = emptySet()) : MailSender {
        override val label = "test"
        val sent = mutableListOf<OutgoingEmail>()
        val times = mutableListOf<Long>()
        var opened = false
        var closed = false
        override fun open() { opened = true }
        override fun send(email: OutgoingEmail) {
            times += System.currentTimeMillis()
            if (email.to[0] in failFor) throw SendException("mailbox unavailable")
            sent += email
        }
        override fun close() { closed = true }
    }

    private val storage = Storage(Files.createTempDirectory("te").toFile())

    private fun engine(sender: MailSender, recipients: List<Recipient>, interval: Int = 1): CampaignEngine {
        val session = storage.newSession("campaign", "Hi {first_name}", "test", interval, recipients, emptyList())
        return CampaignEngine(sender, recipients, "Hi {first_name}", "<p>Dear {name}</p>", emptyList(), interval,
            "Valued Customer", session, storage::saveSession)
    }

    @Test
    fun sendsOneByOneWithInterval() = runBlocking {
        val sender = Recording(failFor = setOf("b@x.com"))
        val e = engine(sender, listOf(Recipient("a@x.com", "Ann Lee"), Recipient("b@x.com"), Recipient("c@x.com", "Cy")))
        val session = e.run()
        assertTrue(sender.opened && sender.closed)
        assertEquals(listOf(listOf("a@x.com"), listOf("c@x.com")), sender.sent.map { it.to })
        assertEquals("Hi Ann", sender.sent[0].subject)
        assertTrue(sender.sent[0].html.contains("Dear Ann Lee"))
        val gaps = sender.times.zipWithNext { a, b -> b - a }
        assertTrue(gaps.toString(), gaps.all { it in 900..1600 })
        assertEquals(Triple(2, 1, "completed"), Triple(session.sent, session.failed, session.status))
        assertEquals(session.id, storage.loadSessions().first().id)
        assertEquals(listOf("sent", "failed", "sent"), e.state.value.items.map { it.status })
    }

    @Test
    fun stopDuringWait() = runBlocking {
        val sender = Recording()
        val e = engine(sender, (0 until 5).map { Recipient("r$it@x.com") }, interval = 30)
        val job = async { e.run() }
        delay(500)
        e.stop()
        val start = System.currentTimeMillis()
        val session = job.await()
        assertTrue(System.currentTimeMillis() - start < 2000)
        assertEquals(1, sender.sent.size)
        assertEquals("stopped", session.status)
    }

    @Test
    fun pauseFreezesCountdown() = runBlocking {
        val sender = Recording()
        val e = engine(sender, listOf(Recipient("a@x.com"), Recipient("b@x.com")), interval = 1)
        val job = async { e.run() }
        delay(200)
        e.pause()
        delay(1000)
        e.resume()
        job.await()
        assertTrue((sender.times[1] - sender.times[0]).toString(), sender.times[1] - sender.times[0] >= 1800)
    }

    @Test
    fun autoPauseAfterRepeatedFailures() = runBlocking {
        val recipients = (0 until 4).map { Recipient("r$it@x.com") }
        val sender = Recording(failFor = recipients.map { it.email }.toSet())
        val e = engine(sender, recipients, interval = 1)
        val job = async { e.run() }
        while (e.state.value.autoPausedReason.isEmpty()) delay(50)
        assertEquals("mailbox unavailable", e.state.value.autoPausedReason)
        assertEquals("paused", e.state.value.phase)
        e.stop()
        job.await()
        assertEquals(3, sender.times.size)
    }
}
