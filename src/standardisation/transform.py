"""Build claim, lab_result, and medication row dicts for the loader.

Lab storage is long-format (one row per test). The five-column-per-test layout
from FR-2.2 is rebuilt afterwards as claim_tests_wide so new tests stay a YAML change.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from src.config_loader import clinic_config, load_all
from src.ingestion.parser import ParsedFile, ParsedSection
from src.standardisation.composites import looks_combined, split_combined
from src.standardisation.demographics import parse_age, parse_date, parse_gender
from src.standardisation.medicines import map_medicine
from src.standardisation.names import resolve_test_name
from src.standardisation.numeric import parse_numeric, parse_range
from src.standardisation.units import canonical_unit, convert_value
from src.validation.classify import classify_result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(*parts: Any) -> str:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _test_meta(canonical: str | None) -> dict:
    tests = load_all()["canonical_tests"].get("tests") or {}
    return tests.get(canonical or "") or {}


def _standardise_one_test(
    parsed: ParsedFile,
    raw: dict,
    processed_at: str,
    extra: dict | None = None,
) -> dict:
    extra = extra or {}
    original = extra.get("test_name_original", raw.get("test_name"))
    resolved = {
        "test_name_canonical": extra.get("test_name_canonical"),
        "normalization_method": extra.get("normalization_method"),
        "normalization_confidence": extra.get("normalization_confidence"),
    }
    if resolved["test_name_canonical"] is None:
        resolved = resolve_test_name(original)

    meta = _test_meta(resolved["test_name_canonical"])
    value_type = meta.get("value_type") or "numeric"
    target_unit = meta.get("canonical_unit")

    numeric = parse_numeric(extra.get("result", raw.get("result")))
    ranged = parse_range(extra.get("range", raw.get("range")))
    unit_original = extra.get("unit", raw.get("unit"))
    unit_canon = canonical_unit(unit_original)
    value, unit_canon = convert_value(numeric.get("result_value"), unit_original, target_unit or unit_canon)

    contradictory = bool(numeric.get("contradictory")) or bool(extra.get("from_combined") is False and looks_combined(original, str(raw.get("result") or "")))
    analytics = classify_result(
        resolved["test_name_canonical"],
        value,
        numeric.get("parse_status") or "missing",
        value_type,
        ranged.get("range_low"),
        ranged.get("range_high"),
        contradictory=contradictory,
        number_count=int(numeric.get("number_count") or 1),
    )

    page = raw.get("page_no")
    return {
        "id": make_id(parsed.document_id, "lab", resolved["test_name_canonical"], original, page, extra.get("result", raw.get("result"))),
        "document_id": parsed.document_id,
        "record_type": "lab_result",
        "file_gcs_path": parsed.file_path,
        "trace_id": parsed.trace_id,
        "correlation_id": parsed.correlation_id,
        "source_system": parsed.source_system,
        "claim_no": parsed.claim_no,
        "nt_code": parsed.nt_code,
        "consumer_client_id": parsed.consumer_client_id,
        "destination_identifier": parsed.destination_identifier,
        "test_name_canonical": resolved["test_name_canonical"],
        "test_name_original": original,
        "result_value": value,
        "result_text": numeric.get("result_text"),
        "result_text_original": str(raw.get("result")) if raw.get("result") is not None else extra.get("result"),
        "unit_canonical": unit_canon,
        "unit_original": unit_original,
        "range_low": ranged.get("range_low"),
        "range_high": ranged.get("range_high"),
        "range_text": ranged.get("range_text"),
        "range_text_original": raw.get("range"),
        "test_analytics": analytics,
        "normalization_method": resolved["normalization_method"],
        "normalization_confidence": resolved["normalization_confidence"],
        "page_no": page,
        "processed_at": processed_at,
        "ingested_at": processed_at,
    }


def lab_rows(parsed: ParsedFile, section: ParsedSection, processed_at: str | None = None) -> list[dict]:
    processed_at = processed_at or _now()
    cfg = clinic_config(parsed.source_system)
    details = section.data.get("report_details") or []
    rows: list[dict] = []
    if not isinstance(details, list):
        return rows
    for item in details:
        if not isinstance(item, dict):
            continue
        name = item.get(cfg["lab"]["test_fields"]["test_name"])
        result = item.get(cfg["lab"]["test_fields"]["result"])
        unit = item.get(cfg["lab"]["test_fields"]["unit"])
        range_text = item.get(cfg["lab"]["test_fields"]["range"])
        if looks_combined(str(name or ""), str(result or "")):
            children = split_combined(str(name or ""), str(result or ""), unit, range_text)
            if children:
                for child in children:
                    raw = dict(item)
                    rows.append(_standardise_one_test(parsed, raw, processed_at, extra=child))
                continue
        rows.append(_standardise_one_test(parsed, item, processed_at))
    return rows


def _demographics_from_lab(section: ParsedSection, formats: list[str]) -> dict:
    info = section.data.get("basic_info") or {}
    age = parse_age(info.get("age"))
    return {
        "patient_name": info.get("patient_name"),
        "age": info.get("age"),
        "age_text": age["age_text"],
        "age_years": age["age_years"],
        "gender": parse_gender(info.get("gender")),
        "uhid": info.get("uhid"),
        "lab_or_hospital_name": info.get("lab_or_hospital_name"),
        "hospital_name": info.get("lab_or_hospital_name"),
        "bill_date": parse_date(info.get("bill_date"), formats),
        "reports_date": parse_date(info.get("reports_date"), formats),
        "report_date": parse_date(info.get("reports_date"), formats),
        "basic_info_age": info.get("age"),
        "basic_info_bill_date": info.get("bill_date"),
    }


def _demographics_from_discharge(section: ParsedSection, formats: list[str]) -> dict:
    data = section.data
    age = parse_age(data.get("age"))
    return {
        "patient_name": data.get("patientName"),
        "age": data.get("age"),
        "age_text": age["age_text"],
        "age_years": age["age_years"],
        "gender": parse_gender(data.get("gender")),
        "hospital_name": data.get("hospitalName"),
        "hospital_address": data.get("hospitalAddress"),
        "doctor_name": data.get("doctorName"),
        "diagnosis": data.get("diagnosis"),
        "brief_history": data.get("briefHistory"),
        "general_examinations": data.get("generalExaminations"),
        "recommendations": data.get("recommendations"),
        "ward": data.get("ward"),
        "post_discharge_advice": data.get("postDischargeAdvice"),
        "admission_date": parse_date(data.get("admissionDate"), formats),
        "discharge_date": parse_date(data.get("dischargeDate"), formats),
        "medicine_injections_investigation": _join(data.get("medicineInjectionsInvestigation")),
        "course_during_hospitalisation": _join(data.get("courseDuringHospitalisation")),
    }


def _join(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def claim_row(parsed: ParsedFile, sections: list[ParsedSection], processed_at: str | None = None) -> dict:
    processed_at = processed_at or _now()
    formats = clinic_config(parsed.source_system).get("date_formats") or []
    merged: dict[str, Any] = {
        "id": make_id("claim", parsed.document_id),
        "document_id": parsed.document_id,
        "record_type": "claim",
        "file_gcs_path": parsed.file_path,
        "trace_id": parsed.trace_id,
        "correlation_id": parsed.correlation_id,
        "source_system": parsed.source_system,
        "claim_no": parsed.claim_no,
        "nt_code": parsed.nt_code,
        "consumer_client_id": parsed.consumer_client_id,
        "destination_identifier": parsed.destination_identifier,
        "metadetails": str(parsed.meta),
        "raw_json": parsed.raw_text,
        "processed_at": processed_at,
        "ingested_at": processed_at,
    }
    for section in sections:
        if section.classifier == "lab_report":
            merged.update({k: v for k, v in _demographics_from_lab(section, formats).items() if v is not None})
        elif section.classifier == "discharge_summary":
            merged.update({k: v for k, v in _demographics_from_discharge(section, formats).items() if v is not None})
    return merged


def medication_rows(parsed: ParsedFile, section: ParsedSection, processed_at: str | None = None) -> list[dict]:
    processed_at = processed_at or _now()
    meds = section.data.get("dischargeMedications") or []
    rows = []
    if not isinstance(meds, list):
        return rows
    for idx, item in enumerate(meds):
        if not isinstance(item, dict):
            continue
        mapped = map_medicine(item.get("medicine"))
        if mapped.get("skipped"):
            continue
        rows.append(
            {
                "id": make_id(parsed.document_id, "med", idx, mapped["original"]),
                "document_id": parsed.document_id,
                "record_type": "medication",
                "file_gcs_path": parsed.file_path,
                "trace_id": parsed.trace_id,
                "correlation_id": parsed.correlation_id,
                "source_system": parsed.source_system,
                "claim_no": parsed.claim_no,
                "medicine": mapped["generic"],
                "medication_name": mapped["generic"],
                "medication_medicine": mapped["original"],
                "dose": item.get("dose"),
                "frequency": item.get("frequency"),
                "medicine_type": item.get("type"),
                "medication_dose": item.get("dose"),
                "medication_frequency": item.get("frequency"),
                "processed_at": processed_at,
                "ingested_at": processed_at,
            }
        )
    return rows
