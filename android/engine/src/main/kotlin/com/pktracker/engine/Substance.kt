package com.pktracker.engine

const val MODEL_ONE_COMPARTMENT = "one_compartment"
const val MODEL_ONE_COMPARTMENT_ER = "one_compartment_er"
const val MODEL_WIDMARK = "widmark_zero_order"
const val DEFAULT_LEGAL_BAC_LIMIT = 0.05

data class Preset(
    val label: String,
    val amount: Double,
    val unit: String = "mg",
    val volumeMl: Double? = null,
    val abvPercent: Double? = null,
)

data class Substance(
    val id: String,
    val name: String,
    val model: String,
    val halfLifeH: Double? = null,
    val ka: Double? = null,
    val ke: Double? = null,
    val f: Double = 1.0,
    val vLPerKg: Double? = null,
    val fracIr: Double? = null,
    val lagH: Double? = null,
    val ka2: Double? = null,
    val ec50: Double? = null,
    val emax: Double = 1.0,
    val redoseEligible: Boolean = false,
    val isBuiltin: Boolean = true,
    val unit: String = "mg",
    val concUnit: String = "mg/L",
    val concScale: Double = 1.0,
    val color: String = "#7ad1c7",
    val note: String = "",
    val sleepThreshold: Double? = null,
    val redoseFraction: Double? = null,
    val overloadAmountMg: Double? = null,
    val toxicityThreshold: Double? = null,
    val presets: List<Preset> = emptyList(),
) {
    val isAlcohol: Boolean get() = model == MODEL_WIDMARK

    fun keValue(): Double = ke ?: halfLifeH?.let { Models.keFromHalfLife(it) }
        ?: error("substance $id has no ke or half-life")

    fun volumeLiters(massKg: Double): Double = (vLPerKg ?: 0.0) * massKg
}

/** A logged dose. [takenAtEpochMs] is Unix time in milliseconds. [uid] is a
 *  globally unique id (stable across devices) used for cross-device sync. */
data class Dose(
    val substanceId: String,
    val amount: Double,
    val unit: String,
    val takenAtEpochMs: Long,
    val note: String = "",
    val id: Long = 0,
    val uid: String = "",
) {
    val hours: Double get() = takenAtEpochMs / 3_600_000.0
}

data class UserProfile(
    val bodyMassKg: Double = 70.0,
    val sex: String = "male",
    val rMale: Double = 0.68,
    val rFemale: Double = 0.55,
    val beta: Double = 0.015,
    val legalBacLimit: Double = DEFAULT_LEGAL_BAC_LIMIT,
    val alcoholRampMin: Double = 0.0,
    val tolerance: Map<String, Double> = emptyMap(),
    val halfLifeOverrides: Map<String, Double> = emptyMap(),
) {
    fun widmarkR(): Double = if (sex.lowercase().startsWith("f")) rFemale else rMale
    fun toleranceFor(substanceId: String): Double = tolerance[substanceId] ?: 1.0
    fun halfLifeFor(substanceId: String): Double? = halfLifeOverrides[substanceId]?.takeIf { it > 0 }
}
