// Local-only settings for verifying the pure-Kotlin :engine module without the
// Android SDK / AGP. Run:  gradle -c settings.local.gradle.kts :engine:test
pluginManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "PKTracker"
include(":engine")
