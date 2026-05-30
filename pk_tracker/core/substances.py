"""Substance definitions and the editable substance library.

A :class:`Substance` bundles the pharmacokinetic constants (half-life, ka, ke,
F, volume of distribution), the pharmacodynamic constants (EC50, Emax), display
metadata (units, colour), and the scope flags that the safety rules hinge on
(``redose_eligible``). These are *defaults* drawn from population-average
literature; every value is overridable per user in settings.

The library lives in ``data/substances.json`` so that a user can add a custom
substance from the UI without any code change. ``core`` never imports ``ui``;
this module only knows how to read and write that JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Model identifiers stored in the DB / JSON.
MODEL_ONE_COMPARTMENT = "one_compartment"
MODEL_ONE_COMPARTMENT_ER = "one_compartment_er"   # bimodal extended release
MODEL_WIDMARK = "widmark_zero_order"

# Where the bundled library lives.
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "data" / "substances.json"


@dataclass
class Preset:
    """A one-tap dose button, e.g. ``Espresso 70 mg`` or ``Beer 330 ml 5%``."""

    label: str
    amount: float
    unit: str
    # Optional, only meaningful for alcohol presets: the drink the grams came
    # from, kept so the UI can show "330 ml @ 5%" and recompute if edited.
    volume_ml: float | None = None
    abv_percent: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Preset":
        return cls(
            label=d["label"],
            amount=float(d["amount"]),
            unit=d["unit"],
            volume_ml=d.get("volume_ml"),
            abv_percent=d.get("abv_percent"),
        )


@dataclass
class Substance:
    """Everything the engine and UI need to model and present one substance."""

    id: str
    name: str
    model: str                      # MODEL_ONE_COMPARTMENT | MODEL_WIDMARK
    # --- pharmacokinetics (one-compartment) ---
    half_life_h: float | None = None
    ka: float | None = None
    ke: float | None = None
    f: float | None = None
    v_l_per_kg: float | None = None
    # --- extended-release (bimodal) parameters, only for MODEL_ONE_COMPARTMENT_ER ---
    frac_ir: float | None = None    # fraction released immediately (rest is delayed)
    lag_h: float | None = None      # delay before the second pulse (h)
    ka2: float | None = None        # absorption rate of the second pulse (defaults to ka)
    # --- pharmacodynamics ---
    ec50: float | None = None       # half-maximal effect concentration (mg/L)
    emax: float = 1.0
    # --- scope / behaviour flags ---
    redose_eligible: bool = False
    is_builtin: bool = False
    # --- display ---
    unit: str = "mg"                # dose unit ('mg' for stimulants, 'g' ethanol for alcohol)
    conc_unit: str = "mg/L"         # concentration display unit
    conc_scale: float = 1.0         # multiply internal mg/L by this for display
    color: str = "#4aa3ff"
    note: str = ""
    # --- soft thresholds (internal mg/L unless noted), all optional ---
    sleep_threshold: float | None = None        # below this, sleep treated as unaffected
    redose_fraction: float | None = None         # effect % of peak that triggers a redose nudge
    overload_amount_mg: float | None = None      # body burden warning (caffeine jitter zone)
    toxicity_threshold: float | None = None      # start of impairment / diminishing returns
    presets: list[Preset] = field(default_factory=list)

    # ----- derived helpers ---------------------------------------------------
    def volume_liters(self, body_mass_kg: float) -> float:
        """Volume of distribution in L for a given body mass."""
        if self.v_l_per_kg is None:
            raise ValueError(f"substance {self.id} has no volume of distribution")
        return self.v_l_per_kg * body_mass_kg

    def ke_value(self) -> float:
        """Elimination rate constant, preferring an explicit ke, else from half-life."""
        if self.ke is not None:
            return self.ke
        if self.half_life_h:
            from .models import ke_from_half_life

            return ke_from_half_life(self.half_life_h)
        raise ValueError(f"substance {self.id} has neither ke nor half_life_h")

    @property
    def is_alcohol(self) -> bool:
        return self.model == MODEL_WIDMARK

    # ----- serialisation -----------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "Substance":
        presets = [Preset.from_dict(p) for p in d.get("presets", [])]
        known = {f for f in cls.__dataclass_fields__ if f != "presets"}
        kwargs = {k: v for k, v in d.items() if k in known}
        return cls(presets=presets, **kwargs)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Drop Nones to keep the JSON tidy and human-editable.
        d = {k: v for k, v in d.items() if v is not None}
        d["presets"] = [
            {pk: pv for pk, pv in asdict(p).items() if pv is not None}
            for p in self.presets
        ]
        return d


def load_substances(path: str | Path = DEFAULT_LIBRARY_PATH) -> dict[str, Substance]:
    """Load the substance library, keyed by id, preserving file order."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    library: dict[str, Substance] = {}
    for entry in raw["substances"]:
        sub = Substance.from_dict(entry)
        library[sub.id] = sub
    return library


def save_substances(library: dict[str, Substance], path: str | Path = DEFAULT_LIBRARY_PATH) -> None:
    """Write the library back to JSON (used by the custom-substance builder)."""
    path = Path(path)
    payload = {"substances": [s.to_dict() for s in library.values()]}
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
