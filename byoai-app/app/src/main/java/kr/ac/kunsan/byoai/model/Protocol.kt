package kr.ac.kunsan.byoai.model

import org.json.JSONObject

/** spine.py 의 SPACE_DESCRIPTOR / capability 와 1:1 대응. */
data class Capability(
    val id: String,
    val kind: String,        // light / air_quality / climate
    val unit: String,
    val min: Double,
    val max: Double,
    val current: Double?,
    val target: Double?,
    val actuator: Int,
    val typicalNow: Double?,   // 이 공간의 '이 시간대 평소값' (척수가 집계, 폰은 읽기만)
    val learnedModel: String,
)

data class SpaceDescriptor(
    val spaceId: String,
    val place: String,
    val outsideTemp: Double?,
    val capabilities: List<Capability>,
    val present: Boolean,
) {
    companion object {
        fun parse(j: JSONObject): SpaceDescriptor {
            val caps = j.getJSONArray("capabilities").let { arr ->
                (0 until arr.length()).map { i ->
                    val c = arr.getJSONObject(i)
                    val r = c.getJSONObject("range")
                    Capability(
                        id = c.optString("id"),
                        kind = c.getString("kind"),
                        unit = c.optString("unit"),
                        min = r.getDouble("min"),
                        max = r.getDouble("max"),
                        current = if (c.isNull("current")) null else c.getDouble("current"),
                        target = if (c.isNull("target")) null else c.getDouble("target"),
                        actuator = c.optInt("actuator", 0),
                        typicalNow = if (c.isNull("typical_now")) null else c.getDouble("typical_now"),
                        learnedModel = c.optJSONObject("learned_model")?.toString() ?: "{}",
                    )
                }
            }
            val occ = j.optJSONObject("occupancy")
            return SpaceDescriptor(
                spaceId = j.optString("space_id"),
                place = j.optString("place"),
                outsideTemp = if (j.isNull("outside_temp")) null else j.optDouble("outside_temp"),
                capabilities = caps,
                present = occ?.optBoolean("present", true) ?: true,
            )
        }
    }
}

/** mDNS 로 자동 발견된 공간(아직 연결 전). */
data class DiscoveredSpace(
    val serviceName: String,
    val host: String,
    val port: Int,
    val place: String,
    val caps: String,
)

/** 폰이 들고 다니는 휴대용 사용자모델 (공간 이동 시 이식 = 복리효과). */
data class UserModel(
    var climateOffset: Double = 2.0,
    var lightPref: Double = 350.0,
    var airMax: Double = 40.0,
    val corrections: MutableList<Correction> = mutableListOf(),
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("climate_offset", climateOffset)
        put("light_pref", lightPref)
        put("air_max", airMax)
        put("corrections", org.json.JSONArray().also { a ->
            corrections.forEach { c ->
                a.put(JSONObject().put("capability", c.capability)
                    .put("context", c.context).put("delta", c.delta))
            }
        })
    }

    /** 수동보정(FEEDBACK) 학습 — phone_brain.learn() 과 동일 규칙. */
    fun learn(capability: String, from: Double?, to: Double?, context: String) {
        val delta = (to ?: 0.0) - (from ?: 0.0)
        corrections.add(Correction(capability, context, delta))
        when (capability) {
            "climate" -> if (kotlin.math.abs(delta) >= 1.0)
                climateOffset += 0.5 * if (delta > 0) 1 else -1
            "light" -> if (to != null) lightPref = to
            "air_quality" -> if (to != null) airMax = to
        }
    }

    companion object {
        fun fromJson(j: JSONObject): UserModel {
            val um = UserModel(
                climateOffset = j.optDouble("climate_offset", 2.0),
                lightPref = j.optDouble("light_pref", 350.0),
                airMax = j.optDouble("air_max", 40.0),
            )
            j.optJSONArray("corrections")?.let { a ->
                for (i in 0 until a.length()) {
                    val c = a.getJSONObject(i)
                    um.corrections.add(
                        Correction(c.optString("capability"), c.optString("context"),
                            c.optDouble("delta"))
                    )
                }
            }
            return um
        }
    }
}

data class Correction(val capability: String, val context: String, val delta: Double)
