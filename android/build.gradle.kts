// Plugins are applied per-module (see app/ and engine/ build.gradle.kts) with
// versions from gradle/libs.versions.toml, so this root build stays empty. That
// also lets the pure-Kotlin :engine module build/test without the Android SDK
// (via: gradle -c settings.local.gradle.kts :engine:test).
