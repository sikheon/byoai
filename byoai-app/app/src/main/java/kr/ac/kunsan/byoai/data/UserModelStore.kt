package kr.ac.kunsan.byoai.data

import android.content.Context
import kr.ac.kunsan.byoai.model.UserModel
import org.json.JSONObject
import java.io.File

/** 휴대용 사용자모델 영속화 (앱 내부저장소 JSON). 공간 이동에도 유지 = 복리효과. */
class UserModelStore(context: Context) {
    private val file = File(context.filesDir, "user_model.json")

    fun load(): UserModel =
        if (file.exists()) runCatching { UserModel.fromJson(JSONObject(file.readText())) }
            .getOrDefault(UserModel()) else UserModel()

    fun save(um: UserModel) = runCatching { file.writeText(um.toJson().toString()) }
}
