"""CRM Price Master ↔ Euler Coulson OEM catalog.

Canonical CRM model names stay as the dealership types them (Turbo Max, Hi-Load,
Neo HiRange, Storm, HiCity). OEM names (Turbo, HiLoad +, HiRange, …) are matched
via fingerprints. Ex-showroom is overwritten from Coulson; RTO / insurance are
never taken from OEM.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _alnum(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def body_class(load_body):
    s = (load_body or "").upper().replace(" ", "")
    if not s or s in ("STANDARD", "NA", "-"):
        return "STANDARD"
    if "TIPPER" in s or s == "DAC":
        return "TIPPER"
    for token in ("DV330", "DV260", "DV220", "DV200", "DV170", "DV120",
                  "FB170", "FB120", "PV120"):
        if s.startswith(token) or token in s:
            return token if token != "PV120" else "PV"
    if s.startswith("DV"):
        return s[:5] if len(s) >= 5 else s
    if s.startswith("HD"):
        return "HD"
    if s.startswith("FB"):
        return "FB"
    if s.startswith("PV"):
        return "PV"
    return s


def charger_kw(charger_type):
    t = str(charger_type or "")
    if "6.6" in t:
        return "6.6"
    if "3.3" in t:
        return "3.3"
    return ""


def chimera_of(row):
    return str(row.get("chimera_type") or "").strip()


@dataclass(frozen=True)
class CatalogSku:
    key: str
    crm_model: str
    crm_variant: str
    body_type: str
    oem_model: str
    oem_variant: str
    body_class: str
    chimera: str = ""
    charger: str = ""
    sap_contains: str = ""
    sap_excludes: str = ""
    aliases: tuple = field(default_factory=tuple)
    expected_price: float = 0.0


def _sku(**kw):
    return CatalogSku(**kw)


# Approved mapping (owner 31 Aug 2026): OEM Turbo City/FastCharge prices;
# drop City (DAC); DV200→DV220 on Maxx/FastCharge; TR-NC / TR With GBT include
# body; Storm HD C10 → T1250; add OEM-only SKUs; drop CRM-only Storm.
CATALOG: tuple[CatalogSku, ...] = (
    # ----- Turbo Max / OEM Turbo -----
    _sku(key="turbo.city.fb", crm_model="Turbo Max", crm_variant="City (FB)", body_type="FB",
         oem_model="Turbo", oem_variant="City", body_class="FB", expected_price=625000),
    _sku(key="turbo.city.pv", crm_model="Turbo Max", crm_variant="City (PV)", body_type="PV",
         oem_model="Turbo", oem_variant="City", body_class="PV", expected_price=650000),
    _sku(key="turbo.city.hd", crm_model="Turbo Max", crm_variant="City (HD)", body_type="HD",
         oem_model="Turbo", oem_variant="City", body_class="HD", expected_price=683000),
    _sku(key="turbo.city.dv200", crm_model="Turbo Max", crm_variant="City (DV200)", body_type="DV200",
         oem_model="Turbo", oem_variant="City", body_class="DV200", expected_price=685000),
    _sku(key="turbo.city.tipper", crm_model="Turbo Max", crm_variant="City (Tipper)", body_type="Tipper",
         oem_model="Turbo", oem_variant="City", body_class="TIPPER", sap_excludes="DAV", expected_price=750000),
    _sku(key="turbo.city.tipper_dav", crm_model="Turbo Max", crm_variant="City (Tipper DAV)", body_type="Tipper",
         oem_model="Turbo", oem_variant="City", body_class="TIPPER", sap_contains="DAV", expected_price=799000),
    _sku(key="turbo.maxx.fb", crm_model="Turbo Max", crm_variant="Maxx (FB)", body_type="FB",
         oem_model="Turbo", oem_variant="Range Maxx", body_class="FB", expected_price=760000),
    _sku(key="turbo.maxx.pv", crm_model="Turbo Max", crm_variant="Maxx (PV)", body_type="PV",
         oem_model="Turbo", oem_variant="Range Maxx", body_class="PV", expected_price=770000),
    _sku(key="turbo.maxx.hd", crm_model="Turbo Max", crm_variant="Maxx (HD)", body_type="HD",
         oem_model="Turbo", oem_variant="Range Maxx", body_class="HD", expected_price=808000),
    _sku(key="turbo.maxx.dv220", crm_model="Turbo Max", crm_variant="Maxx (DV220)", body_type="DV220",
         oem_model="Turbo", oem_variant="Range Maxx", body_class="DV220", expected_price=809999,
         aliases=(("Turbo Max", "Maxx (DV200)"),)),
    _sku(key="turbo.maxx.tipper", crm_model="Turbo Max", crm_variant="Maxx (Tipper)", body_type="Tipper",
         oem_model="Turbo", oem_variant="Range Maxx", body_class="TIPPER", expected_price=895000),
    _sku(key="turbo.fc.fb", crm_model="Turbo Max", crm_variant="FastCharge (FB)", body_type="FB",
         oem_model="Turbo", oem_variant="Fast Charge", body_class="FB", expected_price=860000),
    _sku(key="turbo.fc.pv", crm_model="Turbo Max", crm_variant="FastCharge (PV)", body_type="PV",
         oem_model="Turbo", oem_variant="Fast Charge", body_class="PV", expected_price=870000),
    _sku(key="turbo.fc.hd", crm_model="Turbo Max", crm_variant="FastCharge (HD)", body_type="HD",
         oem_model="Turbo", oem_variant="Fast Charge", body_class="HD", expected_price=908000),
    _sku(key="turbo.fc.dv220", crm_model="Turbo Max", crm_variant="FastCharge (DV220)", body_type="DV220",
         oem_model="Turbo", oem_variant="Fast Charge", body_class="DV220", expected_price=909999,
         aliases=(("Turbo Max", "FastCharge (DV200)"),)),
    # ----- Hi-Load / OEM HiLoad + -----
    _sku(key="hiload.xr.dv120", crm_model="Hi-Load", crm_variant="XR (DV120)", body_type="DV120",
         oem_model="HiLoad +", oem_variant="XR", body_class="DV120", expected_price=471433),
    _sku(key="hiload.xr.dv170", crm_model="Hi-Load", crm_variant="XR (DV170)", body_type="DV170",
         oem_model="HiLoad +", oem_variant="XR", body_class="DV170", expected_price=481634),
    _sku(key="hiload.xr.pv", crm_model="Hi-Load", crm_variant="XR (PV)", body_type="PV",
         oem_model="HiLoad +", oem_variant="XR", body_class="PV", expected_price=456134),
    _sku(key="hiload.xr.hd", crm_model="Hi-Load", crm_variant="XR (HD)", body_type="HD",
         oem_model="HiLoad +", oem_variant="XR", body_class="HD", expected_price=469394),
    _sku(key="hiload.xr.fb170", crm_model="Hi-Load", crm_variant="XR (FB170)", body_type="FB170",
         oem_model="HiLoad +", oem_variant="XR", body_class="FB170", expected_price=448994),
    _sku(key="hiload.xr.fb120", crm_model="Hi-Load", crm_variant="XR (FB120)", body_type="FB120",
         oem_model="HiLoad +", oem_variant="XR", body_class="FB120", expected_price=446953),
    _sku(key="hiload.trnc.fb120", crm_model="Hi-Load", crm_variant="TR-NC (FB120)", body_type="FB120",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="FB120", expected_price=406154,
         aliases=(("Hi-Load", "TR-NC (HiLoad) @406154"),)),
    _sku(key="hiload.trnc.fb170", crm_model="Hi-Load", crm_variant="TR-NC (FB170)", body_type="FB170",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="FB170", expected_price=408193,
         aliases=(("Hi-Load", "TR-NC (HiLoad) @408193"),)),
    _sku(key="hiload.trnc.pv", crm_model="Hi-Load", crm_variant="TR-NC (PV)", body_type="PV",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="PV", expected_price=415334,
         aliases=(("Hi-Load", "TR-NC (HiLoad) @415334"),)),
    _sku(key="hiload.trnc.hd", crm_model="Hi-Load", crm_variant="TR-NC (HD)", body_type="HD",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="HD", expected_price=428594,
         aliases=(("Hi-Load", "TR-NC (HiLoad) @428594"),)),
    _sku(key="hiload.trnc.dv120", crm_model="Hi-Load", crm_variant="TR-NC (DV120)", body_type="DV120",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="DV120", expected_price=430634,
         aliases=(("Hi-Load", "TR-NC (HiLoad)"),)),
    _sku(key="hiload.trnc.dv170", crm_model="Hi-Load", crm_variant="TR-NC (DV170)", body_type="DV170",
         oem_model="HiLoad +", oem_variant="TR-NC", body_class="DV170", expected_price=440834,
         aliases=(("Hi-Load", "TR-NC (HiLoad) @440834"),)),
    _sku(key="hiload.trgbt.fb120", crm_model="Hi-Load", crm_variant="TR With GBT (FB120)", body_type="FB120",
         oem_model="HiLoad +", oem_variant="TR", body_class="FB120", expected_price=471954,
         aliases=(("Hi-Load", "TR With GBT (HiLoad) @471954"),)),
    _sku(key="hiload.trgbt.fb170", crm_model="Hi-Load", crm_variant="TR With GBT (FB170)", body_type="FB170",
         oem_model="HiLoad +", oem_variant="TR", body_class="FB170", expected_price=473994,
         aliases=(("Hi-Load", "TR With GBT (HiLoad) @473994"),)),
    _sku(key="hiload.trgbt.pv", crm_model="Hi-Load", crm_variant="TR With GBT (PV)", body_type="PV",
         oem_model="HiLoad +", oem_variant="TR", body_class="PV", expected_price=481134,
         aliases=(("Hi-Load", "TR With GBT (HiLoad) @481134"),)),
    _sku(key="hiload.trgbt.hd", crm_model="Hi-Load", crm_variant="TR With GBT (HD)", body_type="HD",
         oem_model="HiLoad +", oem_variant="TR", body_class="HD", expected_price=494393,
         aliases=(("Hi-Load", "TR With GBT (HiLoad) @494393"),)),
    _sku(key="hiload.trgbt.dv120", crm_model="Hi-Load", crm_variant="TR With GBT (DV120)", body_type="DV120",
         oem_model="HiLoad +", oem_variant="TR", body_class="DV120", expected_price=496433,
         aliases=(("Hi-Load", "TR With GBT (HiLoad)"),)),
    _sku(key="hiload.trgbt.dv170", crm_model="Hi-Load", crm_variant="TR With GBT (DV170)", body_type="DV170",
         oem_model="HiLoad +", oem_variant="TR", body_class="DV170", expected_price=506635,
         aliases=(("Hi-Load", "TR With GBT (HiLoad) @506635"),)),
    _sku(key="hiload.sr.fb120", crm_model="Hi-Load", crm_variant="SR (FB120)", body_type="FB120",
         oem_model="HiLoad +", oem_variant="SR", body_class="FB120", expected_price=421156),
    _sku(key="hiload.sr.fb170", crm_model="Hi-Load", crm_variant="SR (FB170)", body_type="FB170",
         oem_model="HiLoad +", oem_variant="SR", body_class="FB170", expected_price=423193),
    _sku(key="hiload.sr.pv", crm_model="Hi-Load", crm_variant="SR (PV)", body_type="PV",
         oem_model="HiLoad +", oem_variant="SR", body_class="PV", expected_price=430334),
    _sku(key="hiload.sr.hd", crm_model="Hi-Load", crm_variant="SR (HD)", body_type="HD",
         oem_model="HiLoad +", oem_variant="SR", body_class="HD", expected_price=443593),
    _sku(key="hiload.sr.dv120", crm_model="Hi-Load", crm_variant="SR (DV120)", body_type="DV120",
         oem_model="HiLoad +", oem_variant="SR", body_class="DV120", expected_price=445634),
    # ----- HiCity (misfiled CRM Hi-Load / XR @ 435000) -----
    _sku(key="hicity.xr", crm_model="HiCity", crm_variant="XR", body_type="Standard",
         oem_model="HiCity", oem_variant="XR", body_class="STANDARD", expected_price=435000,
         aliases=(("Hi-Load", "XR"),)),
    _sku(key="hicity.sr", crm_model="HiCity", crm_variant="SR", body_type="Standard",
         oem_model="HiCity", oem_variant="SR", body_class="STANDARD", expected_price=398657),
    _sku(key="hicity.tr", crm_model="HiCity", crm_variant="TR", body_type="Standard",
         oem_model="HiCity", oem_variant="TR", body_class="STANDARD", expected_price=453412),
    # ----- Neo HiRange / OEM HiRange -----
    _sku(key="hirange.xr", crm_model="Neo HiRange", crm_variant="XR", body_type="Standard",
         oem_model="HiRange", oem_variant="XR", body_class="STANDARD", expected_price=437999),
    _sku(key="hirange.tr", crm_model="Neo HiRange", crm_variant="TR", body_type="Standard",
         oem_model="HiRange", oem_variant="TR", body_class="STANDARD", expected_price=378000),
    _sku(key="hirange.sr", crm_model="Neo HiRange", crm_variant="SR", body_type="Standard",
         oem_model="HiRange", oem_variant="SR", body_class="STANDARD", expected_price=309999),
    # ----- Storm T1500 (CRM Storm TR) -----
    _sku(key="storm.tr.fb.c7.33", crm_model="Storm", crm_variant="Storm TR (FB) Reg C7 3.3kWh", body_type="FB",
         oem_model="Storm", oem_variant="T1500", body_class="FB", chimera="7", charger="3.3", expected_price=950000),
    _sku(key="storm.tr.hd.c7.33", crm_model="Storm", crm_variant="Storm TR (HD) Reg C7 3.3kWh", body_type="HD",
         oem_model="Storm", oem_variant="T1500", body_class="HD", chimera="7", charger="3.3", expected_price=999999),
    _sku(key="storm.tr.pv.c7.33", crm_model="Storm", crm_variant="Storm TR (PV) Reg C7 3.3kWh", body_type="PV",
         oem_model="Storm", oem_variant="T1500", body_class="PV", chimera="7", charger="3.3", expected_price=965000),
    _sku(key="storm.tr.dv260.c7.33", crm_model="Storm", crm_variant="Storm TR (DV260) Reg C7 3.3kWh", body_type="DV260",
         oem_model="Storm", oem_variant="T1500", body_class="DV260", chimera="7", charger="3.3", expected_price=999999),
    _sku(key="storm.tr.pv.c7.66", crm_model="Storm", crm_variant="Storm TR (PV) Reg C7 6.6kWh", body_type="PV",
         oem_model="Storm", oem_variant="T1500", body_class="PV", chimera="7", charger="6.6", expected_price=985000),
    _sku(key="storm.tr.dv260.c7.66", crm_model="Storm", crm_variant="Storm TR (DV260) Reg C7 6.6kWh", body_type="DV260",
         oem_model="Storm", oem_variant="T1500", body_class="DV260", chimera="7", charger="6.6", expected_price=1019999),
    _sku(key="storm.tr.pv.c10.33", crm_model="Storm", crm_variant="Storm TR (PV) Reg C10 3.3kWh", body_type="PV",
         oem_model="Storm", oem_variant="T1500", body_class="PV", chimera="10", charger="3.3", expected_price=995000),
    _sku(key="storm.tr.dv260.c10.33", crm_model="Storm", crm_variant="Storm TR (DV260) Reg C10 3.3kWh", body_type="DV260",
         oem_model="Storm", oem_variant="T1500", body_class="DV260", chimera="10", charger="3.3", expected_price=1029999),
    _sku(key="storm.tr.pv.c10.66", crm_model="Storm", crm_variant="Storm TR (PV) Reg C10 6.6kWh", body_type="PV",
         oem_model="Storm", oem_variant="T1500", body_class="PV", chimera="10", charger="6.6", expected_price=1015000),
    _sku(key="storm.tr.dv260.c10.66", crm_model="Storm", crm_variant="Storm TR (DV260) Reg C10 6.6kWh", body_type="DV260",
         oem_model="Storm", oem_variant="T1500", body_class="DV260", chimera="10", charger="6.6", expected_price=1049999),
    _sku(key="storm.tr.pv.arm.c7.33", crm_model="Storm", crm_variant="Storm TR (PV) Arm C7 3.3kWh", body_type="PV",
         oem_model="Storm", oem_variant="T1500 Armoured", body_class="PV", chimera="7", charger="3.3", expected_price=1015000),
    _sku(key="storm.tr.hd.arm.c7.33", crm_model="Storm", crm_variant="Storm TR (HD) Arm C7 3.3kWh", body_type="HD",
         oem_model="Storm", oem_variant="T1500 Armoured", body_class="HD", chimera="7", charger="3.3", expected_price=1049999),
    _sku(key="storm.tr.dv220.c7.33", crm_model="Storm", crm_variant="Storm TR (DV220) Reg C7 3.3kWh", body_type="DV220",
         oem_model="Storm", oem_variant="T1500", body_class="DV220", chimera="7", charger="3.3", expected_price=980000),
    _sku(key="storm.tr.dv220.c7.66", crm_model="Storm", crm_variant="Storm TR (DV220) Reg C7 6.6kWh", body_type="DV220",
         oem_model="Storm", oem_variant="T1500", body_class="DV220", chimera="7", charger="6.6", expected_price=1000000),
    _sku(key="storm.tr.dv220.c10.33", crm_model="Storm", crm_variant="Storm TR (DV220) Reg C10 3.3kWh", body_type="DV220",
         oem_model="Storm", oem_variant="T1500", body_class="DV220", chimera="10", charger="3.3", expected_price=1010000),
    _sku(key="storm.tr.dv220.c10.66", crm_model="Storm", crm_variant="Storm TR (DV220) Reg C10 6.6kWh", body_type="DV220",
         oem_model="Storm", oem_variant="T1500", body_class="DV220", chimera="10", charger="6.6", expected_price=1030000),
    _sku(key="storm.tr.tipper", crm_model="Storm", crm_variant="Storm TR (Tipper)", body_type="Tipper",
         oem_model="Storm", oem_variant="T1500", body_class="STANDARD", sap_contains="Tipper", expected_price=1095000),
    # ----- Storm T1250 (was CRM Storm TR HD C10) -----
    _sku(key="storm.t1250.hd.c10.33", crm_model="Storm", crm_variant="Storm T1250 (HD) Reg C10 3.3kWh", body_type="HD",
         oem_model="Storm", oem_variant="T1250", body_class="HD", chimera="10", charger="3.3", expected_price=1029999,
         aliases=(("Storm", "Storm TR (HD) Reg C10 3.3kWh"),)),
    _sku(key="storm.t1250.hd.c10.66", crm_model="Storm", crm_variant="Storm T1250 (HD) Reg C10 6.6kWh", body_type="HD",
         oem_model="Storm", oem_variant="T1250", body_class="HD", chimera="10", charger="6.6", expected_price=1049999,
         aliases=(("Storm", "Storm TR (HD) Reg C10 6.6kWh"),)),
    _sku(key="storm.t1250.dv260.arm.c7.33", crm_model="Storm", crm_variant="Storm T1250 (DV260) Arm C7 3.3kWh",
         body_type="DV260", oem_model="Storm", oem_variant="T1250 Armoured", body_class="DV260",
         chimera="7", charger="", expected_price=1040000),
    # ----- Storm LR200 -----
    _sku(key="storm.lr.fb.c7", crm_model="Storm", crm_variant="Storm LR (FB) Reg C7 6.6kWh", body_type="FB",
         oem_model="Storm", oem_variant="LR200", body_class="FB", chimera="7", expected_price=1390000),
    _sku(key="storm.lr.hd.c7", crm_model="Storm", crm_variant="Storm LR (HD) Reg C7 6.6kWh", body_type="HD",
         oem_model="Storm", oem_variant="LR200", body_class="HD", chimera="7", expected_price=1430000),
    _sku(key="storm.lr.pv.c7", crm_model="Storm", crm_variant="Storm LR (PV) Reg C7 6.6kWh", body_type="PV",
         oem_model="Storm", oem_variant="LR200", body_class="PV", chimera="7", expected_price=1410000),
    _sku(key="storm.lr.dv330.c7", crm_model="Storm", crm_variant="Storm LR (DV330) Reg C7 6.6kWh", body_type="DV330",
         oem_model="Storm", oem_variant="LR200", body_class="DV330", chimera="7", expected_price=1450000),
    _sku(key="storm.lr.fb.c10", crm_model="Storm", crm_variant="Storm LR (FB) Reg C10 6.6kWh", body_type="FB",
         oem_model="Storm", oem_variant="LR200", body_class="FB", chimera="10", expected_price=1420000),
    _sku(key="storm.lr.hd.c10", crm_model="Storm", crm_variant="Storm LR (HD) Reg C10 6.6kWh", body_type="HD",
         oem_model="Storm", oem_variant="LR200", body_class="HD", chimera="10", expected_price=1460000),
    _sku(key="storm.lr.pv.c10", crm_model="Storm", crm_variant="Storm LR (PV) Reg C10 6.6kWh", body_type="PV",
         oem_model="Storm", oem_variant="LR200", body_class="PV", chimera="10", expected_price=1440000),
    _sku(key="storm.lr.dv330.c10", crm_model="Storm", crm_variant="Storm LR (DV330) Reg C10 6.6kWh", body_type="DV330",
         oem_model="Storm", oem_variant="LR200", body_class="DV330", chimera="10", expected_price=1480000,
         aliases=(("Storm", "Storm LR (Storm LR) Reg C10 6.6kWh"),)),
)

# CRM-only rows the owner asked to drop (no OEM SKU).
DROP_VARIANTS = (
    ("Turbo Max", "City (DAC)"),
    ("Storm", "Storm TR (FB) Reg C10 3.3kWh"),
    ("Storm", "Storm TR (FB) Reg C10 6.6kWh"),
    ("Storm", "Storm TR (DV260) Arm C7 3.3kWh"),
    ("Storm", "Storm TR (FB) Arm C7 3.3kWh"),
    ("Storm", "Storm TR (DV260) Arm C10 3.3kWh"),
    ("Storm", "Storm TR (PV) Arm C10 3.3kWh"),
    ("Storm", "Storm TR (HD) Arm C10 3.3kWh"),
    ("Storm", "Storm TR (FB) Arm C10 3.3kWh"),
    ("Storm", "Storm TR (DV260) Arm C10 6.6kWh"),
    ("Storm", "Storm TR (PV) Arm C10 6.6kWh"),
    ("Storm", "Storm TR (HD) Arm C10 6.6kWh"),
    ("Storm", "Storm TR (FB) Arm C10 6.6kWh"),
)

MODEL_ALIASES = {
    "turbo": "Turbo Max",
    "turbomax": "Turbo Max",
    "hiload": "Hi-Load",
    "hiloadplus": "Hi-Load",
    "hirange": "Neo HiRange",
    "neohirange": "Neo HiRange",
    "hicity": "HiCity",
    "storm": "Storm",
}


def _norm_pair(model, variant):
    return (str(model or "").strip().lower(), str(variant or "").strip().lower())


def build_alias_index():
    """(model, variant) lowercased → CatalogSku. Canonical names included."""
    idx = {}
    for sku in CATALOG:
        idx[_norm_pair(sku.crm_model, sku.crm_variant)] = sku
        for am, av in sku.aliases:
            idx[_norm_pair(am, av)] = sku
    return idx


ALIAS_INDEX = build_alias_index()


def resolve_sku(model, variant):
    """Return the catalog SKU for a CRM (or alias) model/variant, or None."""
    return ALIAS_INDEX.get(_norm_pair(model, variant))


def canonical_model_variant(model, variant):
    sku = resolve_sku(model, variant)
    if sku:
        return sku.crm_model, sku.crm_variant
    return str(model or "").strip(), str(variant or "").strip()


def match_oem_row(sku: CatalogSku, oem: dict) -> bool:
    if (oem.get("model") or "").strip() != sku.oem_model:
        return False
    if (oem.get("variant") or "").strip() != sku.oem_variant:
        return False
    bc = body_class(oem.get("load_body"))
    if sku.body_class == "STANDARD":
        if bc not in ("STANDARD", ""):
            # Storm tipper has null load_body → STANDARD; HiCity/HiRange are Standard.
            if sku.sap_contains and sku.sap_contains.lower() in (oem.get("sap_product_name") or "").lower():
                pass
            else:
                return False
    elif bc != sku.body_class:
        return False
    if sku.chimera and chimera_of(oem) != sku.chimera:
        return False
    if sku.charger and charger_kw(oem.get("charger_type")) != sku.charger:
        return False
    sap = oem.get("sap_product_name") or ""
    if sku.sap_contains and sku.sap_contains.lower() not in sap.lower():
        # Tipper with empty sap name: allow registered name
        reg = oem.get("model_registered_name") or ""
        if sku.sap_contains.lower() not in reg.lower():
            return False
    if sku.sap_excludes and sku.sap_excludes.lower() in sap.lower():
        return False
    return True


def sku_for_oem_row(oem: dict):
    hits = [s for s in CATALOG if match_oem_row(s, oem)]
    return hits[0] if len(hits) == 1 else (hits[0] if hits else None)


def jaipur_price(oem: dict):
    v = oem.get("showroom_price_non_delhi")
    if v in (None, ""):
        v = oem.get("showroom_price_delhi")
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def catalog_by_key():
    return {s.key: s for s in CATALOG}
