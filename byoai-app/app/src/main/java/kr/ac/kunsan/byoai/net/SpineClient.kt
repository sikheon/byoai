package kr.ac.kunsan.byoai.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.PrintWriter
import java.net.Socket

/**
 * 척수(spine.py)와의 TCP 줄단위 JSON 클라이언트.
 * 접속 시 SPACE_DESCRIPTOR 1줄 수신 → 이후 STATE/FEEDBACK 스트림, COMMAND 송신.
 */
class SpineClient {
    private var socket: Socket? = null
    private var writer: PrintWriter? = null
    private var reader: BufferedReader? = null

    /** 연결 + 첫 줄(SPACE_DESCRIPTOR) 반환. */
    suspend fun connect(host: String, port: Int): JSONObject = withContext(Dispatchers.IO) {
        val s = Socket(host, port)
        socket = s
        writer = PrintWriter(s.getOutputStream(), true)
        reader = s.getInputStream().bufferedReader()
        JSONObject(reader!!.readLine())
    }

    /** STATE/FEEDBACK 메시지를 한 줄씩 콜백. 블로킹이므로 IO 코루틴에서 호출. */
    suspend fun listen(onMessage: (JSONObject) -> Unit) = withContext(Dispatchers.IO) {
        val r = reader ?: return@withContext
        while (true) {
            val line = r.readLine() ?: break
            if (line.isNotBlank()) runCatching { onMessage(JSONObject(line)) }
        }
    }

    /** 폰 대뇌 결정 전송. targets = {kind: value}. null = 해당 능력 목표 해제(예: 공기청정 OFF). */
    suspend fun sendCommand(targets: Map<String, Double?>, reason: String) =
        withContext(Dispatchers.IO) {
            val t = JSONObject()
            targets.forEach { (k, v) -> t.put(k, v ?: JSONObject.NULL) }
            val msg = JSONObject()
                .put("type", "COMMAND")
                .put("targets", t)
                .put("reason", reason)
            writer?.println(msg.toString())
        }

    fun close() {
        runCatching { socket?.close() }
        socket = null; writer = null; reader = null
    }
}
