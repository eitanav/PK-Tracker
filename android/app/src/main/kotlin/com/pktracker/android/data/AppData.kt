package com.pktracker.android.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.pktracker.engine.Dose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

// ---- Room: the dose log -----------------------------------------------------
// [uid] is a globally unique id, and deletes are soft ([deleted] + [updatedAt]),
// so the log can be merged across devices without duplicates or resurrected
// rows. This is the local half of cross-device sync.
@Entity(tableName = "doses")
data class DoseEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val uid: String = "",
    val substanceId: String,
    val amount: Double,
    val unit: String,
    val takenAtEpochMs: Long,
    val note: String = "",
    val deleted: Boolean = false,
    val updatedAt: Long = 0,
)

fun DoseEntity.toDose(): Dose = Dose(substanceId, amount, unit, takenAtEpochMs, note, id, uid)

@Dao
interface DoseDao {
    @Query("SELECT * FROM doses WHERE deleted = 0 ORDER BY takenAtEpochMs")
    fun observeAll(): Flow<List<DoseEntity>>

    @Insert
    suspend fun insert(dose: DoseEntity): Long

    @Query("UPDATE doses SET deleted = 1, updatedAt = :now WHERE id = :id")
    suspend fun softDelete(id: Long, now: Long)

    @Query("SELECT * FROM doses WHERE deleted = 0 ORDER BY id DESC LIMIT 1")
    suspend fun latest(): DoseEntity?

    @Query("SELECT * FROM doses WHERE deleted = 0 ORDER BY takenAtEpochMs")
    suspend fun allOnce(): List<DoseEntity>

    // ---- sync surface (used by the cross-device sync layer) ----
    @Query("SELECT * FROM doses WHERE updatedAt > :since ORDER BY updatedAt")
    suspend fun changedSince(since: Long): List<DoseEntity>

    @Query("SELECT * FROM doses WHERE uid = :uid LIMIT 1")
    suspend fun byUid(uid: String): DoseEntity?
}

private val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE doses ADD COLUMN uid TEXT NOT NULL DEFAULT ''")
        db.execSQL("ALTER TABLE doses ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE doses ADD COLUMN updatedAt INTEGER NOT NULL DEFAULT 0")
        db.execSQL("UPDATE doses SET uid = 'legacy-' || id WHERE uid = ''")
    }
}

@Database(entities = [DoseEntity::class], version = 2, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun doseDao(): DoseDao

    companion object {
        @Volatile private var instance: AppDatabase? = null
        fun get(context: Context): AppDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext, AppDatabase::class.java, "pk_tracker.db",
            ).addMigrations(MIGRATION_1_2).build().also { instance = it }
        }
    }
}

// ---- DataStore: settings ----------------------------------------------------
data class AppSettings(
    val theme: String = "system",       // system | dark | light
    val language: String = "system",    // system | en | iw
    val bodyMassKg: Double = 70.0,
    val sex: String = "male",
    val caffeineHalfLifeH: Double = 5.0,
    val caffeineTolerance: Double = 1.0,
    val activeSubstanceId: String = "caffeine",
    val bedtime: String = "23:00",
    val sleepMode: String = "mg",       // mg | preset | hours
    val sleepMg: Int = 50,
    val sleepSensitivity: String = "average",
    val sleepHours: Int = 8,
    val timingTarget: String = "18:00",
    val timingMg: Int = 90,
    val simOn: Boolean = false,
    val simMg: Int = 90,
    val simInMin: Int = 60,
    val graphWindowH: Int = 14,
    val remindersEnabled: Boolean = false,
    val reminderLastCutoffMs: Long = 0,
    val reminderLastRedoseMs: Long = 0,
)

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore("settings")

class SettingsStore(private val context: Context) {
    private object Keys {
        val theme = stringPreferencesKey("theme")
        val language = stringPreferencesKey("language")
        val bodyMassKg = doublePreferencesKey("body_mass")
        val sex = stringPreferencesKey("sex")
        val caffeineHalfLife = doublePreferencesKey("caffeine_half_life")
        val caffeineTolerance = doublePreferencesKey("caffeine_tolerance")
        val activeSubstance = stringPreferencesKey("active_substance")
        val bedtime = stringPreferencesKey("bedtime")
        val sleepMode = stringPreferencesKey("sleep_mode")
        val sleepMg = intPreferencesKey("sleep_mg")
        val sleepSensitivity = stringPreferencesKey("sleep_sensitivity")
        val sleepHours = intPreferencesKey("sleep_hours")
        val timingTarget = stringPreferencesKey("timing_target")
        val timingMg = intPreferencesKey("timing_mg")
        val simMg = intPreferencesKey("sim_mg")
        val simInMin = intPreferencesKey("sim_in_min")
        val graphWindowH = intPreferencesKey("graph_window_h")
        val remindersEnabled = booleanPreferencesKey("reminders_enabled")
        val reminderLastCutoffMs = longPreferencesKey("reminder_last_cutoff")
        val reminderLastRedoseMs = longPreferencesKey("reminder_last_redose")
    }

    val flow: Flow<AppSettings> = context.dataStore.data.map { p ->
        AppSettings(
            theme = p[Keys.theme] ?: "system",
            language = p[Keys.language] ?: "system",
            bodyMassKg = p[Keys.bodyMassKg] ?: 70.0,
            sex = p[Keys.sex] ?: "male",
            caffeineHalfLifeH = p[Keys.caffeineHalfLife] ?: 5.0,
            caffeineTolerance = p[Keys.caffeineTolerance] ?: 1.0,
            activeSubstanceId = p[Keys.activeSubstance] ?: "caffeine",
            bedtime = p[Keys.bedtime] ?: "23:00",
            sleepMode = p[Keys.sleepMode] ?: "mg",
            sleepMg = p[Keys.sleepMg] ?: 50,
            sleepSensitivity = p[Keys.sleepSensitivity] ?: "average",
            sleepHours = p[Keys.sleepHours] ?: 8,
            timingTarget = p[Keys.timingTarget] ?: "18:00",
            timingMg = p[Keys.timingMg] ?: 90,
            simOn = false,
            simMg = p[Keys.simMg] ?: 90,
            simInMin = p[Keys.simInMin] ?: 60,
            graphWindowH = p[Keys.graphWindowH] ?: 14,
            remindersEnabled = p[Keys.remindersEnabled] ?: false,
            reminderLastCutoffMs = p[Keys.reminderLastCutoffMs] ?: 0,
            reminderLastRedoseMs = p[Keys.reminderLastRedoseMs] ?: 0,
        )
    }

    suspend fun update(block: MutablePrefs.() -> Unit) {
        context.dataStore.edit { prefs ->
            MutablePrefs(prefs).apply(block)
        }
    }

    inner class MutablePrefs(private val p: androidx.datastore.preferences.core.MutablePreferences) {
        fun theme(v: String) { p[Keys.theme] = v }
        fun language(v: String) { p[Keys.language] = v }
        fun bodyMassKg(v: Double) { p[Keys.bodyMassKg] = v }
        fun sex(v: String) { p[Keys.sex] = v }
        fun caffeineHalfLife(v: Double) { p[Keys.caffeineHalfLife] = v }
        fun caffeineTolerance(v: Double) { p[Keys.caffeineTolerance] = v }
        fun activeSubstance(v: String) { p[Keys.activeSubstance] = v }
        fun bedtime(v: String) { p[Keys.bedtime] = v }
        fun sleepMode(v: String) { p[Keys.sleepMode] = v }
        fun sleepMg(v: Int) { p[Keys.sleepMg] = v }
        fun sleepSensitivity(v: String) { p[Keys.sleepSensitivity] = v }
        fun sleepHours(v: Int) { p[Keys.sleepHours] = v }
        fun timingTarget(v: String) { p[Keys.timingTarget] = v }
        fun timingMg(v: Int) { p[Keys.timingMg] = v }
        fun simMg(v: Int) { p[Keys.simMg] = v }
        fun simInMin(v: Int) { p[Keys.simInMin] = v }
        fun graphWindowH(v: Int) { p[Keys.graphWindowH] = v }
        fun remindersEnabled(v: Boolean) { p[Keys.remindersEnabled] = v }
        fun reminderLastCutoffMs(v: Long) { p[Keys.reminderLastCutoffMs] = v }
        fun reminderLastRedoseMs(v: Long) { p[Keys.reminderLastRedoseMs] = v }
    }
}
