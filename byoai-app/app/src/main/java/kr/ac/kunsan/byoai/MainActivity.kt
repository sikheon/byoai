package kr.ac.kunsan.byoai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import kr.ac.kunsan.byoai.ui.App
import kr.ac.kunsan.byoai.ui.ByoaiTheme

class MainActivity : ComponentActivity() {
    private val vm: ByoaiViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 외부 파일 디렉터리에 GGUF가 있으면 온디바이스 두뇌 로드 (없으면 heuristic 폴백)
        getExternalFilesDir(null)?.listFiles { f -> f.name.endsWith(".gguf") }
            ?.firstOrNull()?.let { vm.loadBrain(it.absolutePath) }
        setContent {
            ByoaiTheme {
                App(vm)
            }
        }
    }
}
