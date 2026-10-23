plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.travelessence.emailstudio"
    compileSdk = 36

    defaultConfig {
        // The Google Play listing's permanent id (the Kotlin package above is internal and never shown).
        applicationId = "com.legacyai.emailstudio"
        minSdk = 26
        targetSdk = 36          // Google Play: new apps and updates must target API 36 from 31 Aug 2026
        versionCode = 4
        versionName = "1.5.0"
        // Optional: a Microsoft Entra app registration built into the release, so users can sign in to
        // Microsoft 365 / Outlook.com without creating their own. Pass -PmsClientId=... or MS_CLIENT_ID.
        val msClientId = (project.findProperty("msClientId") as String?) ?: System.getenv("MS_CLIENT_ID") ?: ""
        buildConfigField("String", "MS_CLIENT_ID", "\"$msClientId\"")
        buildConfigField("String", "PRIVACY_URL",
            "\"https://github.com/shahydlegacyofficial-creator/Automate-Email/blob/HEAD/PRIVACY.md\"")
    }

    signingConfigs {
        // Google Play upload key - NEVER committed. CI writes it from repository secrets; see PLAY_SUBMISSION.md.
        val uploadStore = System.getenv("ANDROID_UPLOAD_KEYSTORE_PATH")
        if (uploadStore != null && file(uploadStore).isFile) {
            create("upload") {
                storeFile = file(uploadStore)
                storePassword = System.getenv("ANDROID_UPLOAD_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_UPLOAD_KEY_ALIAS") ?: "upload"
                keyPassword = System.getenv("ANDROID_UPLOAD_KEY_PASSWORD") ?: System.getenv("ANDROID_UPLOAD_KEYSTORE_PASSWORD")
            }
        }
        // Key for the APK downloads on GitHub (installed by hand, outside Google Play).
        create("release") {
            // A CI secret can supply a private keystore; otherwise the bundled key is used so
            // every build can be installed over the previous one.
            val ciKeystore = System.getenv("ANDROID_KEYSTORE_PATH")
            storeFile = file(ciKeystore ?: "travel-essence-release.jks")
            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: "travelessence"
            keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "travelessence"
            keyPassword = System.getenv("ANDROID_KEY_PASSWORD") ?: "travelessence"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // -Pplay builds the Google Play bundle: signed with the upload key when it is available,
            // otherwise left unsigned (to be signed with the upload key afterwards) - never with the public key.
            signingConfig = if (project.hasProperty("play")) signingConfigs.findByName("upload")
                else signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
    packaging {
        resources {
            excludes += setOf(
                "/META-INF/{AL2.0,LGPL2.1}",
                "META-INF/LICENSE*",
                "META-INF/NOTICE*",
                "META-INF/DEPENDENCIES",
            )
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    // SMTP / IMAP
    implementation("com.sun.mail:android-mail:1.6.7")
    implementation("com.sun.mail:android-activation:1.6.7")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
