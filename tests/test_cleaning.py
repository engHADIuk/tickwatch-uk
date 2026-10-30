from datetime import datetime

from app.cleaning import clean_record, parse_date, process_batch
from tests.factories import messy_payload

NOW = datetime(2026, 10, 30)


def test_parse_date_formats():
    assert parse_date("2022-08-01T06:40:31") == datetime(2022, 8, 1, 6, 40, 31)
    assert parse_date("2022-08-01T06:40:31Z") == datetime(2022, 8, 1, 6, 40, 31)
    assert parse_date("2022-08-01T07:40:31+01:00") == datetime(2022, 8, 1, 6, 40, 31)
    assert parse_date("01/08/2022") == datetime(2022, 8, 1)
    assert parse_date("garbage") is None and parse_date(None) is None and parse_date("") is None


def test_normalises_case_whitespace_and_aliases():
    r = clean_record({"id": " a1 ", "date": "2021-05-05T10:00:00", "latinName": "ixodes RICINUS",
                      "location": "  newcastle ", "species": "castor BEAN tick"}, NOW)
    assert (r.id, r.latin_name, r.species, r.location, r.region) == (
        "a1", "Ixodes ricinus", "Castor bean tick", "Newcastle upon Tyne", "North East")
    assert "location_normalised" in r.flags


def test_rejection_reasons():
    ok = {"id": "x", "date": "2021-05-05T10:00:00", "location": "London", "species": "s", "latinName": "A b"}
    assert clean_record({**ok, "id": None}, NOW) == "missing_id"
    assert clean_record({**ok, "date": None}, NOW) == "missing_date"
    assert clean_record({**ok, "date": "nope"}, NOW) == "invalid_date"
    assert clean_record({**ok, "date": "2999-01-01"}, NOW) == "future_date"
    assert clean_record({**ok, "location": "  "}, NOW) == "missing_location"
    assert clean_record("string", NOW) == "not_an_object"


def test_unknown_city_kept_and_flagged():
    r = clean_record({"id": "x", "date": "2021-05-05", "location": "Atlantis"}, NOW)
    assert r.region == "Unknown" and "unknown_region" in r.flags


def test_batch_dedupes_and_infers():
    res = process_batch(messy_payload(), now=NOW)
    reasons = res.reject_reasons
    assert reasons["duplicate_exact"] == 1
    assert reasons["duplicate_id_conflict"] == 1
    assert reasons["duplicate_content"] == 1
    assert reasons["invalid_date"] == 1 and reasons["missing_location"] == 1
    assert reasons["missing_date"] == 1 and reasons["missing_id"] == 1
    assert reasons["future_date"] == 1 and reasons["not_an_object"] == 1
    by_id = {r.id: r for r in res.clean}
    assert by_id["m6"].species == "Castor bean tick" and "species_inferred" in by_id["m6"].flags
    assert by_id["m7"].latin_name and "latin_name_inferred" in by_id["m7"].flags
    assert len({r.id for r in res.clean}) == len(res.clean)


def test_cross_sync_duplicate_detected():
    rec = {"id": "new-id", "date": "2021-05-05T10:00:00", "location": "London", "latinName": "A b", "species": "S"}
    first = process_batch([rec], now=NOW).clean[0]
    res = process_batch([rec], known_hashes=lambda hs: {first.content_hash: "old-id"}, now=NOW)
    assert res.clean == [] and res.reject_reasons == {"duplicate_content": 1}
