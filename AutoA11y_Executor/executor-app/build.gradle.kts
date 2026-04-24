plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val enabledPlugins = (findProperty("autoa11y.plugins.include") as? String)?.trim().orEmpty()
val pluginModules = linkedMapOf(
    "googlemaps" to ":plugins:scenarios-googlemaps",
    "tiktok" to ":plugins:scenarios-tiktok",
    "shein" to ":plugins:scenarios-shein"
)
val selectedPluginIds = if (enabledPlugins.isBlank() || enabledPlugins.equals("all", ignoreCase = true)) {
    pluginModules.keys.toList()
} else {
    enabledPlugins.split(",")
        .map { it.trim().lowercase() }
        .filter { it.isNotBlank() && pluginModules.containsKey(it) }
}
val generatedPluginsDir = layout.buildDirectory.dir("generated/source/executorPlugins/main/kotlin")

val generateExecutorPluginRegistry by tasks.registering {
    val outputDir = generatedPluginsDir
    inputs.property("selectedPluginIds", selectedPluginIds.joinToString(","))
    outputs.dir(outputDir)
    doLast {
        val dir = outputDir.get().file("com/example/autoa11y/executor/app").asFile
        dir.mkdirs()
        val file = dir.resolve("GeneratedExecutorPluginEntries.kt")

        val entriesBlock = if (selectedPluginIds.isEmpty()) {
            "emptyList()"
        } else {
            selectedPluginIds.joinToString(
                separator = ",\n",
                prefix = "listOf(\n",
                postfix = "\n)"
            ) { id ->
                when (id) {
                    "googlemaps" -> """
                        ExecutorProfileRegistry.Entry(
                            id = "googlemaps",
                            label = "Google Maps",
                            profile = com.example.autoa11y.plugins.googlemaps.GooglemapsProfile
                        )
                    """.trimIndent()

                    "tiktok" -> """
                        ExecutorProfileRegistry.Entry(
                            id = "tiktok",
                            label = "TikTok",
                            profile = com.example.autoa11y.plugins.tiktok.TiktokProfile
                        )
                    """.trimIndent()

                    "shein" -> """
                        ExecutorProfileRegistry.Entry(
                            id = "shein",
                            label = "SHEIN",
                            profile = com.example.autoa11y.plugins.shein.SheinProfile
                        )
                    """.trimIndent()

                    else -> error("Unsupported plugin id: $id")
                }
            }
        }

        file.writeText(
            """
            package com.example.autoa11y.executor.app

            internal object GeneratedExecutorPluginEntries {
                val entries: List<ExecutorProfileRegistry.Entry> = $entriesBlock
            }
            """.trimIndent() + "\n"
        )
    }
}

android {
    namespace = "com.example.autoa11y.executor.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.autoa11y.executor.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "ENABLED_PLUGINS", "\"${if (enabledPlugins.isBlank()) "all" else enabledPlugins}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        viewBinding = true
        buildConfig = true
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
    sourceSets["main"].java.srcDir(generatedPluginsDir)
}

tasks.named("preBuild").configure {
    dependsOn(generateExecutorPluginRegistry)
}

dependencies {
    implementation(project(":executor-control"))
    implementation(project(":executor-reporting"))
    implementation(project(":core"))
    implementation(project(":engine"))
    implementation(project(":drivers:a11y-driver"))
    implementation(project(":drivers:shell-driver"))
    implementation(project(":env"))
    implementation(project(":monitor"))
    implementation(project(":shared"))
    selectedPluginIds.forEach { id ->
        implementation(project(pluginModules.getValue(id)))
    }
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    testImplementation("junit:junit:4.13.2")
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("org.robolectric:robolectric:4.14.1")
}
