"""Garage setup exports (.htm): parsing, strict alignment, own vs official."""

import os

import pytest

from tenths import garage_export as ge


def _export(setup="lemans", values=(("Tire type", "Dry"), ("ARB blades", "3"),
                                    ("Spring rate", "1200 lbs/in"))):
    # Mirrors iRacing's layout: garbled headings, help text, then Label:<U>value</U>.
    rows = "".join(f"<H2><U><br><H2><U>ng:</U></H2>{label}:<U>{value}</U><br><br>"
                   for label, value in values)
    return (f'<H2 align="center">iRacing.com Motorsport Simulations<br>'
            f'fordmustanggt3 setup: &lt;{setup}&gt;<br>track: roadatlanta full</H2>'
            f"<H2><U>help text: ignore me</U></H2>{rows}"
            "If the setup fails tech inspection, it is likely ...")


KEYS = ["UpdateCount", "TiresAero.TireType.TireType", "Chassis.FrontBrakesLights.ArbBlades",
        "Chassis.LeftRear.SpringRate"]


def test_parse_reads_labelled_values_and_header():
    parsed = ge.parse_export_text(_export())
    assert parsed["setup"] == "lemans" and parsed["track"] == "roadatlanta full"
    assert parsed["values"] == [("Tire type", "Dry"), ("ARB blades", "3"),
                                ("Spring rate", "1200 lbs/in")]


def test_align_checks_every_label():
    values = ge.parse_export_text(_export())["values"]
    assert ge.align(values, KEYS) == {"TiresAero.TireType.TireType": "Dry",
                                      "Chassis.FrontBrakesLights.ArbBlades": "3",
                                      "Chassis.LeftRear.SpringRate": "1200 lbs/in"}


def test_misaligned_export_is_refused():
    values = [("Tire type", "Dry"), ("Spring rate", "1200 lbs/in"), ("ARB blades", "3")]
    with pytest.raises(ge.ExportFormatError):
        ge.align(values, KEYS)
    with pytest.raises(ge.ExportFormatError):
        ge.align(values[:2], KEYS)


def test_normalised_labels_match_awkward_keys():
    assert ge._norm("%F WtDist") == ge._norm("FWtdist")
    assert ge._norm("Last temps O M I") == ge._norm("LastTempsOMI")
    assert ge._norm("Front master cyl.") == ge._norm("FrontMasterCyl")


def test_own_vs_official_is_decided_by_file_name(tmp_path):
    # 2026-09-26: the official Le Mans export and the driver's lemans.sto both
    # carry the internal name "lemans" but are different setups.
    (tmp_path / "lemans.sto").write_bytes(b"")
    (tmp_path / "lemans export.htm").write_text(_export("lemans"), encoding="utf-8")
    (tmp_path / "lemans_ir.htm").write_text(
        _export("lemans", (("Tire type", "Dry"), ("ARB blades", "4"),
                           ("Spring rate", "1029 lbs/in"))), encoding="utf-8")
    setups, skipped = ge.load_exports(str(tmp_path), KEYS)
    by_name = {s["setup"]: s for s in setups}
    assert skipped == []
    assert by_name["lemans"]["source"] == "own"
    assert by_name["lemans_ir"]["source"] == "official"
    assert by_name["lemans_ir"]["values"]["Chassis.FrontBrakesLights.ArbBlades"] == "4"


def test_render_marks_values_outside_every_official(tmp_path):
    own = {"setup": "lemans", "source": "own",
           "values": {"Chassis.FrontBrakesLights.ArbBlades": "3"}}
    off = [{"setup": n, "source": "official",
            "values": {"Chassis.FrontBrakesLights.ArbBlades": v}} for n, v in (("a", "4"), ("b", "5"))]
    md = ge.render_reference("Ford Mustang GT3", [own] + off, current="lemans")
    assert "| FrontBrakesLights ArbBlades | **3** (outside) | 4 / 5 | 0 of 2 |" in md
