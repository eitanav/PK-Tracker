package com.pktracker.android.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.core.content.ContextCompat
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.os.LocaleListCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pktracker.android.AppViewModel
import com.pktracker.android.R
import com.pktracker.android.ui.SectionCard
import kotlinx.coroutines.launch
import java.time.Instant
import java.util.Locale
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChipRow(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { (value, label) ->
            FilterChip(selected = selected == value, onClick = { onSelect(value) }, label = { Text(label) })
        }
    }
}

@Composable
private fun LabeledValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.SemiBold)
    }
}

private const val RELEASES_URL = "https://github.com/eitanav/PK-Tracker/releases"

private fun applyLanguage(code: String) {
    val locales = when (code) {
        "en" -> LocaleListCompat.forLanguageTags("en")
        "iw" -> LocaleListCompat.forLanguageTags("he")
        else -> LocaleListCompat.getEmptyLocaleList()
    }
    AppCompatDelegate.setApplicationLocales(locales)
}

@Composable
fun SettingsScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(stringResource(R.string.nav_settings), style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 4.dp))

        // Appearance
        SectionCard(title = stringResource(R.string.appearance)) {
            Text(stringResource(R.string.theme), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            ChipRow(
                listOf(
                    "system" to stringResource(R.string.theme_system),
                    "dark" to stringResource(R.string.theme_dark),
                    "light" to stringResource(R.string.theme_light),
                ),
                settings.theme,
            ) { vm.updateSettings { theme(it) } }
            Spacer(Modifier.height(12.dp))
            Text(stringResource(R.string.language), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            ChipRow(
                listOf(
                    "system" to stringResource(R.string.language_system),
                    "en" to stringResource(R.string.language_en),
                    "iw" to stringResource(R.string.language_he),
                ),
                settings.language,
            ) { code -> vm.updateSettings { language(code) }; applyLanguage(code) }
            Spacer(Modifier.height(12.dp))
            LabeledValue(
                stringResource(R.string.graph_window),
                stringResource(R.string.graph_window_value, settings.graphWindowH),
            )
            Slider(
                value = settings.graphWindowH.toFloat(), valueRange = 4f..48f,
                onValueChange = { vm.updateSettings { graphWindowH(it.roundToInt()) } },
            )
        }

        // Body & calibration
        SectionCard(title = stringResource(R.string.body_calibration)) {
            LabeledValue(stringResource(R.string.body_mass), "${settings.bodyMassKg.roundToInt()} ${stringResource(R.string.kg)}")
            Slider(
                value = settings.bodyMassKg.toFloat(), valueRange = 40f..150f,
                onValueChange = { vm.updateSettings { bodyMassKg(it.toDouble()) } },
            )
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.sex), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            ChipRow(
                listOf("male" to stringResource(R.string.sex_male), "female" to stringResource(R.string.sex_female)),
                settings.sex,
            ) { vm.updateSettings { sex(it) } }
            Spacer(Modifier.height(12.dp))
            LabeledValue(stringResource(R.string.caffeine_half_life),
                "${String.format(Locale.US, "%.1f", settings.caffeineHalfLifeH)} ${stringResource(R.string.hours_short)}")
            Slider(
                value = settings.caffeineHalfLifeH.toFloat(), valueRange = 1.5f..15f,
                onValueChange = { vm.updateSettings { caffeineHalfLife((it * 2).roundToInt() / 2.0) } },
            )
            Text(stringResource(R.string.half_life_hint), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            LabeledValue(stringResource(R.string.tolerance), String.format(Locale.US, "%.2f", settings.caffeineTolerance))
            Slider(
                value = settings.caffeineTolerance.toFloat(), valueRange = 0.5f..1.5f,
                onValueChange = { vm.updateSettings { caffeineTolerance((it * 20).roundToInt() / 20.0) } },
            )
            Text(stringResource(R.string.tolerance_hint), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Sleep cutoff
        SectionCard(title = stringResource(R.string.sleep_settings)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.bedtime) + " ", color = MaterialTheme.colorScheme.onSurfaceVariant)
                TimeButton(settings.bedtime) { vm.updateSettings { bedtime(it) } }
            }
            Spacer(Modifier.height(10.dp))
            Text(stringResource(R.string.method), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(6.dp))
            ChipRow(
                listOf(
                    "mg" to stringResource(R.string.method_mg),
                    "preset" to stringResource(R.string.method_preset),
                    "hours" to stringResource(R.string.method_hours),
                ),
                settings.sleepMode,
            ) { vm.updateSettings { sleepMode(it) } }
            Spacer(Modifier.height(10.dp))
            when (settings.sleepMode) {
                "hours" -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.hours_before_bed) + " ", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Stepper(settings.sleepHours, { vm.updateSettings { sleepHours(it) } }, 1, 3..14, " ${stringResource(R.string.hours_short)}")
                }
                "preset" -> ChipRow(
                    listOf(
                        "sensitive" to stringResource(R.string.sensitivity_sensitive),
                        "average" to stringResource(R.string.sensitivity_average),
                        "resistant" to stringResource(R.string.sensitivity_resistant),
                    ),
                    settings.sleepSensitivity,
                ) { vm.updateSettings { sleepSensitivity(it) } }
                else -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.target_mg) + " ", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Stepper(settings.sleepMg, { vm.updateSettings { sleepMg(it) } }, 5, 10..200, " ${stringResource(R.string.mg)}")
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.sleep_research), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Reminders
        SectionCard(title = stringResource(R.string.reminders_title)) {
            val notifLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
                vm.updateSettings { remindersEnabled(granted) }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.reminders_toggle), modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                Switch(checked = settings.remindersEnabled, onCheckedChange = { on ->
                    if (on) {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                        ) {
                            notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            vm.updateSettings { remindersEnabled(true) }
                        }
                    } else {
                        vm.updateSettings { remindersEnabled(false) }
                    }
                })
            }
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.reminders_hint), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Cloud sync
        SectionCard(title = stringResource(R.string.sync_title)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.sync_toggle), modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                Switch(checked = settings.syncEnabled, onCheckedChange = { on -> vm.updateSettings { syncEnabled(on) } })
            }
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.sync_hint), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Data
        SectionCard(title = stringResource(R.string.data)) {
            OutlinedButton(onClick = {
                scope.launch {
                    val doses = vm.allDosesOnce()
                    val sb = StringBuilder("substance,amount,unit,taken_at,note\n")
                    doses.forEach {
                        sb.append("${it.substanceId},${it.amount},${it.unit},${Instant.ofEpochMilli(it.takenAtEpochMs)},${it.note}\n")
                    }
                    val intent = Intent(Intent.ACTION_SEND).apply {
                        type = "text/csv"
                        putExtra(Intent.EXTRA_SUBJECT, "PK Tracker export")
                        putExtra(Intent.EXTRA_TEXT, sb.toString())
                    }
                    context.startActivity(Intent.createChooser(intent, null))
                }
            }) { Text(stringResource(R.string.export)) }
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.export_hint), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // About
        SectionCard(title = stringResource(R.string.about)) {
            Text(stringResource(R.string.about_body), style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.version, "2.4.0"), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(10.dp))
            OutlinedButton(onClick = {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(RELEASES_URL)))
            }) { Text(stringResource(R.string.download_latest)) }
            Spacer(Modifier.height(14.dp))
            Text(stringResource(R.string.whats_new), color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.changelog_2_4_0), style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_2_3_0), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_2_2_0), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_2_1_0), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_2_0_0), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_1_0_3), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_1_0_2), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.changelog_1_0_1), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            Text(stringResource(R.string.disclaimer), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(16.dp))
    }
}
