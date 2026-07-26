package com.pktracker.android

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pktracker.android.notify.Reminders
import com.pktracker.android.sync.CloudSync
import com.pktracker.android.ui.LocalAccent
import com.pktracker.android.ui.PkLogo
import com.pktracker.android.ui.accentColorFor
import com.pktracker.android.ui.screens.DashboardScreen
import com.pktracker.android.ui.screens.InsightsScreen
import com.pktracker.android.ui.screens.SettingsScreen
import com.pktracker.android.ui.theme.PKTrackerTheme
import com.pktracker.engine.Substances
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent {
            val vm: AppViewModel = viewModel()
            val settings by vm.settings.collectAsStateWithLifecycle()
            val dark = when (settings.theme) {
                "dark" -> true
                "light" -> false
                else -> isSystemInDarkTheme()
            }
            val context = LocalContext.current
            LaunchedEffect(settings.remindersEnabled) {
                if (settings.remindersEnabled) {
                    Reminders.ensureChannel(context)
                    Reminders.schedule(context)
                } else {
                    Reminders.cancel(context)
                }
            }
            LaunchedEffect(settings.syncEnabled) {
                if (settings.syncEnabled) CloudSync.start(context) else CloudSync.stop()
            }
            PKTrackerTheme(darkTheme = dark) {
                val sub = remember(settings.activeSubstanceId) {
                    Substances.byId(settings.activeSubstanceId) ?: Substances.caffeine
                }
                val accent by animateColorAsState(accentColorFor(sub), tween(450), label = "accent")
                CompositionLocalProvider(LocalAccent provides accent) {
                    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                        AppScaffold(vm)
                    }
                }
            }
        }
    }
}

@Composable
private fun AppTopBar(accent: Color) {
    Row(
        Modifier
            .fillMaxWidth()
            // The window is edge-to-edge, so the bar must move itself out from
            // under the status bar. Horizontal insets matter too: in landscape a
            // tablet's cutout or gesture areas sit beside the content, not above.
            .windowInsetsPadding(
                WindowInsets.safeDrawing.only(
                    WindowInsetsSides.Top + WindowInsetsSides.Horizontal,
                ),
            )
            .padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        PkLogo(28.dp, accent)
        Spacer(Modifier.width(10.dp))
        Text("PK ", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text("Tracker", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = accent)
    }
}

@Composable
private fun AppScaffold(vm: AppViewModel) {
    val accent = LocalAccent.current
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val navColors = NavigationBarItemDefaults.colors(
        selectedIconColor = accent,
        selectedTextColor = accent,
        indicatorColor = accent.copy(alpha = 0.16f),
    )
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { AppTopBar(accent) },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                NavigationBarItem(
                    selected = tab == 0, onClick = { tab = 0 }, colors = navColors,
                    icon = { Icon(Icons.Filled.Home, null) },
                    label = { Text(stringResource(R.string.nav_now)) },
                )
                NavigationBarItem(
                    selected = tab == 1, onClick = { tab = 1 }, colors = navColors,
                    icon = { Icon(Icons.Filled.BarChart, null) },
                    label = { Text(stringResource(R.string.nav_insights)) },
                )
                NavigationBarItem(
                    selected = tab == 2, onClick = { tab = 2 }, colors = navColors,
                    icon = { Icon(Icons.Filled.Settings, null) },
                    label = { Text(stringResource(R.string.nav_settings)) },
                )
            }
        },
    ) { padding ->
        val modifier = Modifier
            .padding(padding)
            // Keep content clear of a landscape cutout / gesture edges as well.
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))
        when (tab) {
            0 -> SyncRefreshable(vm, modifier) { DashboardScreen(vm, Modifier) }
            1 -> SyncRefreshable(vm, modifier) { InsightsScreen(vm, Modifier) }
            else -> SettingsScreen(vm, modifier)
        }
    }
}

/**
 * Pull down to sync. Only wraps the content when cloud sync is switched on --
 * with sync off there is nothing a refresh could fetch (the dashboard already
 * recomputes as the clock ticks), and offering a gesture that does nothing is
 * worse than not offering one.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SyncRefreshable(
    vm: AppViewModel,
    modifier: Modifier,
    content: @Composable () -> Unit,
) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    if (!settings.syncEnabled) {
        Box(modifier) { content() }
        return
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    PullToRefreshBox(
        isRefreshing = refreshing,
        onRefresh = {
            refreshing = true
            scope.launch {
                CloudSync.refreshNow(context)
                refreshing = false
            }
        },
        modifier = modifier,
    ) { content() }
}
