package com.travelessence.emailstudio

import com.travelessence.emailstudio.agent.protocol.AgentTool
import com.travelessence.emailstudio.agent.protocol.McpDispatcher
import com.travelessence.emailstudio.agent.protocol.McpHttpServer
import com.travelessence.emailstudio.agent.protocol.Param
import com.travelessence.emailstudio.agent.protocol.ToolError
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

/** The phone's MCP server over real HTTP: handshake, tools, argument checks and the security rules. */
class McpServerTest {
    private val token = "test-token-123"
    private lateinit var server: McpHttpServer
    private lateinit var dispatcher: McpDispatcher
    private val calls = mutableListOf<String>()

    @Before fun setUp() {
        val tools = listOf(
            AgentTool("echo", "Echo", "Echo text back.",
                mapOf("text" to Param("string"), "times" to Param("integer", minimum = 1, maximum = 3)),
                required = listOf("text"), readOnly = true) { a ->
                McpDispatcher.obj("echo" to a.string("text"), "times" to (a.int("times") ?: 1))
            },
            AgentTool("fail", "Fail", "Always fails.") { throw ToolError("Nope - try again with a list name.") },
        )
        dispatcher = McpDispatcher(tools, "test-server", "1.0", onCall = { name, _, _ -> calls += name })
        server = McpHttpServer(dispatcher, token, port = 0)
        server.start()
    }

    @After fun tearDown() = server.stop()

    private fun post(body: String, auth: String? = token, headers: Map<String, String> = emptyMap(),
                     path: String = "/mcp", method: String = "POST"): Pair<Int, JsonObject?> {
        val c = URL("http://127.0.0.1:${server.boundPort}$path").openConnection() as HttpURLConnection
        c.requestMethod = method
        c.setRequestProperty("Content-Type", "application/json")
        auth?.let { c.setRequestProperty("Authorization", "Bearer $it") }
        headers.forEach { (k, v) -> c.setRequestProperty(k, v) }
        if (method == "POST") {
            c.doOutput = true
            c.outputStream.use { it.write(body.toByteArray()) }
        }
        val code = c.responseCode
        val text = (if (code < 400) c.inputStream else c.errorStream)?.bufferedReader()?.readText().orEmpty()
        return code to (if (text.isBlank()) null else Json.parseToJsonElement(text).let { it as? JsonObject })
    }

    private fun rpc(method: String, params: String = "{}", id: Int = 1) =
        """{"jsonrpc":"2.0","id":$id,"method":"$method","params":$params}"""

    @Test fun handshakeNegotiatesVersionAndRemembersClient() {
        val (code, body) = post(rpc("initialize", """{"protocolVersion":"2025-03-26","clientInfo":{"name":"Claude"}}"""))
        assertEquals(200, code)
        assertEquals("2025-03-26", body!!["result"]!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content)
        assertEquals("Claude", dispatcher.clientName)
        val (_, newer) = post(rpc("initialize", """{"protocolVersion":"1999-01-01"}"""))
        assertEquals("2025-11-25", newer!!["result"]!!.jsonObject["protocolVersion"]!!.jsonPrimitive.content)
        assertEquals(202, post("""{"jsonrpc":"2.0","method":"notifications/initialized"}""").first)
    }

    @Test fun listAndCallTools() {
        val tools = post(rpc("tools/list")).second!!["result"]!!.jsonObject["tools"]!!.jsonArray
        assertEquals(listOf("echo", "fail"), tools.map { it.jsonObject["name"]!!.jsonPrimitive.content })
        assertTrue(tools[0].jsonObject["annotations"]!!.jsonObject["readOnlyHint"]!!.jsonPrimitive.boolean)
        val result = post(rpc("tools/call", """{"name":"echo","arguments":{"text":"hi","times":2}}""")).second!!["result"]!!.jsonObject
        assertEquals(false, result["isError"]!!.jsonPrimitive.boolean)
        assertEquals(2, result["structuredContent"]!!.jsonObject["times"]!!.jsonPrimitive.int)
        assertEquals(listOf("echo"), calls)
    }

    @Test fun badArgumentsAreToolErrorsTheAiCanFix() {
        fun err(args: String): String {
            val r = post(rpc("tools/call", """{"name":"echo","arguments":$args}""")).second!!["result"]!!.jsonObject
            assertTrue(r["isError"]!!.jsonPrimitive.boolean)
            return r["content"]!!.jsonArray[0].jsonObject["text"]!!.jsonPrimitive.content
        }
        assertTrue(err("{}").contains("Missing required argument(s): text"))
        assertTrue(err("""{"text":5}""").contains("'text' must be a string"))
        assertTrue(err("""{"text":"x","times":9}""").contains("at most 3"))
        assertTrue(err("""{"text":"x","colour":"red"}""").contains("Unknown argument(s): colour"))
        val fail = post(rpc("tools/call", """{"name":"fail","arguments":{}}""")).second!!["result"]!!.jsonObject
        assertTrue(fail["content"]!!.jsonArray[0].jsonObject["text"]!!.jsonPrimitive.content.contains("try again"))
        assertEquals(-32602, post(rpc("tools/call", """{"name":"nope"}""")).second!!["error"]!!.jsonObject["code"]!!.jsonPrimitive.int)
        assertEquals(-32601, post(rpc("server/discover")).second!!["error"]!!.jsonObject["code"]!!.jsonPrimitive.int)
        assertEquals(400, post("{not json").first)
    }

    @Test fun batchRequests() {
        val c = URL("http://127.0.0.1:${server.boundPort}/mcp").openConnection() as HttpURLConnection
        c.requestMethod = "POST"; c.doOutput = true
        c.setRequestProperty("Authorization", "Bearer $token")
        c.outputStream.use { it.write("[${rpc("ping", id = 1)},${rpc("ping", id = 2)}]".toByteArray()) }
        val arr = Json.parseToJsonElement(c.inputStream.bufferedReader().readText()) as JsonArray
        assertEquals(listOf(1, 2), arr.map { it.jsonObject["id"]!!.jsonPrimitive.int })
    }

    /** Raw HTTP so Origin / Host can be set (HttpURLConnection silently drops both). */
    private fun raw(host: String = "127.0.0.1", origin: String? = null): Int {
        val body = rpc("ping").toByteArray()
        java.net.Socket("127.0.0.1", server.boundPort).use { s ->
            val head = "POST /mcp HTTP/1.1\r\nHost: $host\r\nAuthorization: Bearer $token\r\n" +
                (origin?.let { "Origin: $it\r\n" } ?: "") + "Content-Type: application/json\r\nContent-Length: ${body.size}\r\n\r\n"
            s.getOutputStream().write(head.toByteArray() + body)
            return s.getInputStream().bufferedReader().readLine().split(" ")[1].toInt()
        }
    }

    @Test fun securityRules() {
        assertEquals(401, post(rpc("ping"), auth = null).first)
        assertEquals(401, post(rpc("ping"), auth = "wrong").first)
        assertEquals(200, raw())
        assertEquals(403, raw(origin = "https://evil.example"))
        assertEquals(200, raw(origin = "http://localhost:3000"))
        assertEquals(403, raw(host = "evil.example"))              // DNS rebinding
        assertEquals(403, raw(host = "192.168.1.50:8765"))         // Wi-Fi access is off
        assertEquals(404, post(rpc("ping"), path = "/other").first)
        assertEquals(400, post(rpc("ping"), headers = mapOf("MCP-Protocol-Version" to "2099-01-01")).first)
        assertEquals(405, post("", method = "GET").first)
    }
}
