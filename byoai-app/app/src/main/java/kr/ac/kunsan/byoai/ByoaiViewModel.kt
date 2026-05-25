package kr.ac.kunsan.byoai

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kr.ac.kunsan.byoai.data.UserModelStore
import kr.ac.kunsan.byoai.discovery.SpaceDiscovery
import kr.ac.kunsan.byoai.llm.LlamaBridge
import kr.ac.kunsan.byoai.llm.PromptBuilder
import kr.ac.kunsan.byoai.model.Capability
import kr.ac.kunsan.byoai.model.DiscoveredSpace
import kr.ac.kunsan.byoai.model.SpaceDescriptor
import kr.ac.kunsan.byoai.net.SpineClient
import org.json.JSONObject
import java.io.File
import kotlin.math.roundToInt

/** My AI 시트용 휴대 사용자모델 스냅샷 (복리효과 가시화). */
data class AiProfile(
    val lightPct: Int,       // 조명 선호 (%)
    val warmth: Double,      // 추위민감 오프셋 (°)
    val airMax: Int,         // 공기질 상한
    val corrections: Int,    // 누적 보정 수
    val spaces: Int,         // 학습이 일어난 공간 수
)

/** 화면 흐름 상태 컨테이너. discover.py + phone_brain.py 의 앱 버전. */
class ByoaiViewModel(app: Application) : AndroidViewModel(app) {

    private val discovery = SpaceDiscovery(app)
    private val store = UserModelStore(app)
    private val brain = LlamaBridge()
    private var client: SpineClient? = null
    private var user = store.load()
    private var brainReady = false

    private val _spaces = MutableStateFlow<List<DiscoveredSpace>>(emptyList())
    val spaces = _spaces.asStateFlow()

    private val _descriptor = MutableStateFlow<SpaceDescriptor?>(null)
    val descriptor = _descriptor.asStateFlow()

    private val _status = MutableStateFlow("")          // 오류 등 짧은 한 줄
    val status = _status.asStateFlow()

    private val _connecting = MutableStateFlow<String?>(null)  // 연결 중인 serviceName
    val connecting = _connecting.asStateFlow()

    private val _thinking = MutableStateFlow(false)     // AI 결정 진행 중
    val thinking = _thinking.asStateFlow()

    private val _reason = MutableStateFlow<String?>(null)  // 마지막 결정의 이유(투명성)
    val reason = _reason.asStateFlow()

    private val _profile = MutableStateFlow(snapshot())
    val profile = _profile.asStateFlow()

    private fun snapshot() = AiProfile(
        lightPct = (user.lightPref / 10).roundToInt(),  // 0~1000lux → %
        warmth = user.climateOffset,
        airMax = user.airMax.roundToInt(),
        corrections = user.corrections.size,
        spaces = user.corrections.map { it.context.substringBefore(" ") }.distinct().size,
    )

    private fun learned() { store.save(user); _profile.value = snapshot() }

    // --- ① 공간 자동발견 ---
    fun startDiscovery() {
        _spaces.value = emptyList()
        discovery.start(
            onFound = { sp -> _spaces.value = (_spaces.value + sp).distinctBy { it.serviceName } },
            onLost = { name -> _spaces.value = _spaces.value.filterNot { it.serviceName == name } },
        )
    }

    fun stopDiscovery() = discovery.stop()

    // --- ② 공간 연결 → descriptor(기기 자동추가) + STATE/FEEDBACK 수신 ---
    fun connect(space: DiscoveredSpace) {
        if (_connecting.value != null) return
        _connecting.value = space.serviceName
        viewModelScope.launch {
            runCatching {
                val c = SpineClient(); client = c
                _descriptor.value = SpaceDescriptor.parse(c.connect(space.host, space.port))
                _status.value = ""; _reason.value = null
                launch {
                    c.listen { msg ->
                        when (msg.optString("type")) {
                            "STATE" -> mergeState(msg)
                            "FEEDBACK" -> {        // 공간측 물리 수동조작 → 휴대모델 학습
                                fun d(k: String) = msg.optDouble(k).let { if (it.isNaN()) null else it }
                                user.learn(msg.optString("capability"),
                                    d("from"), d("to"), msg.optString("context_label"))
                                learned()
                            }
                        }
                    }
                    if (client === c) disconnect()   // 스트림 종료(공간 이탈) → 목록 복귀
                }
            }.onFailure { _status.value = "Couldn't connect"; _descriptor.value = null }
            _connecting.value = null
        }
    }

    fun disconnect() {
        client?.close(); client = null
        _descriptor.value = null
        _status.value = ""; _reason.value = null; _thinking.value = false
    }

    /** STATE(1초)로 기기 현재값·목표 라이브 갱신 + 새 능력 자동 반영(온보딩). */
    private fun mergeState(msg: JSONObject) {
        val desc = _descriptor.value ?: return
        val arr = msg.optJSONArray("caps") ?: return
        val blocks = (0 until arr.length()).map { arr.getJSONObject(it) }
        val byKind = blocks.associateBy { it.getString("kind") }
        fun num(b: JSONObject, k: String) = if (b.isNull(k)) null else b.getDouble(k)
        val updated = desc.capabilities.map { c ->
            byKind[c.kind]?.let { b ->
                c.copy(current = num(b, "current"), target = num(b, "target"),
                    actuator = b.optInt("actuator", 0), typicalNow = num(b, "typical_now"))
            } ?: c
        }
        val known = desc.capabilities.map { it.kind }.toSet()
        val added = blocks.filter { it.getString("kind") !in known }.map { b ->
            val r = b.getJSONObject("range")
            Capability(b.optString("id"), b.getString("kind"), b.optString("unit"),
                r.getDouble("min"), r.getDouble("max"), num(b, "current"), num(b, "target"),
                b.optInt("actuator", 0), num(b, "typical_now"),
                b.optJSONObject("learned_model")?.toString() ?: "{}")
        }
        _descriptor.value = desc.copy(capabilities = updated + added)
    }

    // --- 폰 두뇌 로드 (GGUF는 내부저장소에 있어야 함) ---
    fun loadBrain(modelPath: String) = viewModelScope.launch(Dispatchers.IO) {
        brainReady = File(modelPath).exists() && brain.load(modelPath, threads = 4)
    }

    // --- ③ AI 최적화: 폰 Gemma 결정 → 명령 전송 (+ 이유 공개 = 투명성) ---
    fun optimize() {
        if (_thinking.value) return
        viewModelScope.launch {
            val desc = _descriptor.value ?: return@launch
            _thinking.value = true
            val (targets, why) = withContext(Dispatchers.Default) {
                if (brainReady) {
                    val out = brain.decide(PromptBuilder.build(desc, user), 200)
                    PromptBuilder.extractTargets(out)
                } else null
            } ?: heuristic(desc)
            client?.sendCommand(targets.mapValues { it.value as Double? }, why)
            _reason.value = why
            _thinking.value = false
        }
    }

    // --- 기기 수동 제어 (= 학습신호. 조용히 — 설명문구 없음) ---
    fun manualOverride(kind: String, from: Double?, to: Double) = viewModelScope.launch {
        user.learn(kind, from, to, "${_descriptor.value?.place ?: "space"} manual")
        learned()
        client?.sendCommand(mapOf(kind to (to as Double?)), "manual")
    }

    /** 공기청정 토글: ON → 휴대 선호 상한(airMax) 목표, OFF → 목표 해제(팬 정지). */
    fun airToggle(on: Boolean) = viewModelScope.launch {
        client?.sendCommand(mapOf("air_quality" to if (on) user.airMax else null),
            if (on) "manual" else "manual off")
    }

    private fun heuristic(desc: SpaceDescriptor): Pair<Map<String, Double>, String> {
        val t = desc.capabilities.filter { it.kind != "occupancy" }.associate { c ->
            c.kind to when (c.kind) {
                "climate" -> 21 + user.climateOffset
                "light" -> user.lightPref
                "air_quality" -> user.airMax
                else -> (c.min + c.max) / 2
            }
        }
        return t to "From your portable preferences"
    }

    override fun onCleared() {
        discovery.stop(); client?.close(); brain.free()
    }
}
