plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "kr.ac.kunsan.byoai"
    compileSdk = 35
    ndkPath = "C:/Users/HS/gemma-test/gpu-build/android-ndk-r26d"   // 기보유 NDK 재사용
    ndkVersion = "26.3.11579264"                                    // r26d 실버전 (AGP 기본값 27과 불일치 방지)

    defaultConfig {
        applicationId = "kr.ac.kunsan.byoai"
        minSdk = 31              // S22 울트라(Android 12+). llama.cpp는 arm64-v8a.
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
        ndk { abiFilters += "arm64-v8a" }
        externalNativeBuild {
            cmake {
                arguments += "-DGGML_OPENMP=OFF"
                arguments += "-DCMAKE_BUILD_TYPE=Release"   // Debug ggml은 추론 ~10배 느림
            }
        }
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    // llama.cpp 소스가 클론된 경우에만 JNI 빌드 (없으면 heuristic 폴백 APK — D-4)
    if (file("src/main/cpp/llama.cpp").exists()) {
        externalNativeBuild {
            cmake {
                path = file("src/main/cpp/CMakeLists.txt")
                version = "3.22.1"
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.10.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")  // collectAsStateWithLifecycle
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    // JSON은 안드로이드 내장 org.json 사용 (별도 의존성·플러그인 불필요)
}
