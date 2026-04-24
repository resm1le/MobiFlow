pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
    plugins {
        id("com.android.application") version "8.9.0"
        id("com.android.library") version "8.9.0"
        id("org.jetbrains.kotlin.android") version "1.9.24"
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}

rootProject.name = "AutoA11y_Executor"

include(
    ":executor-app",
    ":executor-control",
    ":executor-reporting",
    ":core",
    ":engine",
    ":drivers:a11y-driver",
    ":drivers:shell-driver",
    ":env",
    ":monitor",
    ":shared",
    ":plugins:scenarios-googlemaps",
    ":plugins:scenarios-tiktok",
    ":plugins:scenarios-shein"
)
