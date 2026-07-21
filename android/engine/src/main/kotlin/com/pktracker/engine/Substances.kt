package com.pktracker.engine

/** Built-in substance library — a faithful port of `substances.json`. */
object Substances {

    val caffeine = Substance(
        id = "caffeine", name = "Caffeine", model = MODEL_ONE_COMPARTMENT,
        halfLifeH = 5.0, ka = 5.0, ke = 0.139, f = 0.99, vLPerKg = 0.6,
        ec50 = 1.0, emax = 1.0, redoseEligible = true,
        unit = "mg", concUnit = "mg/L", concScale = 1.0, color = "#d6a04a",
        note = "Full feature set. Estimates only, not medical advice; individual metabolism varies widely.",
        sleepThreshold = 0.6, redoseFraction = 0.30, overloadAmountMg = 400.0, toxicityThreshold = 5.0,
        presets = listOf(
            Preset("Brewed coffee", 90.0), Preset("Espresso", 70.0),
            Preset("Turkish coffee", 100.0), Preset("Black tea", 45.0), Preset("Energy drink", 80.0),
        ),
    )

    val methylphenidate = Substance(
        id = "methylphenidate", name = "Methylphenidate IR", model = MODEL_ONE_COMPARTMENT,
        halfLifeH = 3.5, ka = 1.3, ke = 0.198, f = 0.30, vLPerKg = 2.5,
        ec50 = 0.011, emax = 1.0, redoseEligible = false,
        unit = "mg", concUnit = "ng/mL", concScale = 1000.0, color = "#4aa3ff",
        note = "Prescription medication: visualised only. Dosing is your prescribing physician's decision.",
        sleepThreshold = 0.004, toxicityThreshold = 0.04,
        presets = listOf(Preset("MPH 10 mg", 10.0), Preset("MPH 20 mg", 20.0)),
    )

    val alcohol = Substance(
        id = "alcohol", name = "Alcohol", model = MODEL_WIDMARK, redoseEligible = false,
        unit = "g", concUnit = "g/dL", concScale = 1.0, color = "#c0567a",
        note = "Sobriety / clearance predictor only. BAC and sober-time figures are rough estimates and must NOT be used to decide whether it is safe or legal to drive.",
        presets = listOf(
            Preset("Beer 330 ml 5%", 13.02, "g", 330.0, 5.0),
            Preset("Wine 150 ml 12%", 14.2, "g", 150.0, 12.0),
            Preset("Spirits 40 ml 40%", 12.62, "g", 40.0, 40.0),
            Preset("Pint 500 ml 5%", 19.73, "g", 500.0, 5.0),
        ),
    )

    val lisdexamfetamine = Substance(
        id = "lisdexamfetamine", name = "Lisdexamfetamine", model = MODEL_ONE_COMPARTMENT,
        halfLifeH = 11.0, ka = 0.693, ke = 0.063, f = 0.295, vLPerKg = 3.5,
        ec50 = 0.011, emax = 1.0, redoseEligible = false,
        unit = "mg", concUnit = "ng/mL", concScale = 1000.0, color = "#5ad6b0",
        note = "Prescription prodrug: visualised only. Dosing is your prescriber's decision; this tool never recommends doses.",
        sleepThreshold = 0.015, toxicityThreshold = 0.12,
        presets = listOf(Preset("30 mg", 30.0), Preset("50 mg", 50.0), Preset("70 mg", 70.0)),
    )

    val mixedAmphetamineSalts = Substance(
        id = "mixed_amphetamine_salts", name = "Mixed Amphetamine Salts", model = MODEL_ONE_COMPARTMENT,
        halfLifeH = 11.0, ka = 1.0, ke = 0.063, f = 0.75, vLPerKg = 4.0,
        ec50 = 0.011, emax = 1.0, redoseEligible = false,
        unit = "mg", concUnit = "ng/mL", concScale = 1000.0, color = "#9a7bff",
        note = "Prescription stimulant (3:1 d/l-amphetamine): visualised only. Dosing is your prescriber's decision.",
        sleepThreshold = 0.015, toxicityThreshold = 0.12,
        presets = listOf(Preset("10 mg", 10.0), Preset("20 mg", 20.0), Preset("30 mg", 30.0)),
    )

    val methylphenidateEr = Substance(
        id = "methylphenidate_er", name = "Methylphenidate ER", model = MODEL_ONE_COMPARTMENT_ER,
        halfLifeH = 3.5, ka = 1.3, ke = 0.198, f = 0.30, vLPerKg = 2.5,
        fracIr = 0.4, lagH = 5.0, ka2 = 0.5,
        ec50 = 0.011, emax = 1.0, redoseEligible = false,
        unit = "mg", concUnit = "ng/mL", concScale = 1000.0, color = "#5fa8ff",
        note = "Prescription extended-release stimulant: visualised only. Dosing is your prescriber's decision.",
        sleepThreshold = 0.004, toxicityThreshold = 0.04,
        presets = listOf(Preset("18 mg", 18.0), Preset("36 mg", 36.0), Preset("54 mg", 54.0)),
    )

    val amphetamineXr = Substance(
        id = "amphetamine_xr", name = "Amphetamine XR", model = MODEL_ONE_COMPARTMENT_ER,
        halfLifeH = 11.0, ka = 1.0, ke = 0.063, f = 0.75, vLPerKg = 4.0,
        fracIr = 0.5, lagH = 4.0, ka2 = 1.0,
        ec50 = 0.011, emax = 1.0, redoseEligible = false,
        unit = "mg", concUnit = "ng/mL", concScale = 1000.0, color = "#b08bff",
        note = "Prescription extended-release stimulant: visualised only. Dosing is your prescriber's decision.",
        sleepThreshold = 0.015, toxicityThreshold = 0.12,
        presets = listOf(Preset("10 mg", 10.0), Preset("20 mg", 20.0), Preset("30 mg", 30.0)),
    )

    /** Library in display order. */
    val builtins: List<Substance> = listOf(
        caffeine, methylphenidate, alcohol, lisdexamfetamine,
        mixedAmphetamineSalts, methylphenidateEr, amphetamineXr,
    )

    fun byId(id: String): Substance? = builtins.firstOrNull { it.id == id }
}
