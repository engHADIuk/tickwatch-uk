"""Synthetic data shaped exactly like the real upstream payload, plus deliberate mess."""
import random
from datetime import datetime, timedelta

SPECIES = [
    ("Ixodes ricinus", "Castor bean tick"), ("Ixodes hexagonus", "Hedgehog tick"),
    ("Ixodes apronophorus", "Marsh tick"), ("Ixodes acuminatus", "Southern rodent tick"),
    ("Dermacentor frontalis", "Passerine tick"), ("Haemaphysalis punctata", "Red sheep tick"),
]
CITIES = ["Manchester", "London", "Glasgow", "Edinburgh", "Cardiff", "Belfast", "Bristol", "Leeds", "Norwich", "Exeter"]


def clean_payload(n=300, seed=7):
    rnd = random.Random(seed)
    start = datetime(2018, 1, 1)
    out = []
    for i in range(n):
        latin, common = rnd.choice(SPECIES)
        # bias towards spring/summer so seasonality has a signal
        d = start + timedelta(days=rnd.randint(0, 365 * 4), seconds=rnd.randint(0, 86399))
        out.append({"id": f"id{i:05d}", "date": d.strftime("%Y-%m-%dT%H:%M:%S"),
                    "latinName": latin, "location": rnd.choice(CITIES), "species": common})
    return out


def messy_payload():
    base = clean_payload(50)
    return base + [
        dict(base[0]),                                                     # exact duplicate id
        {**base[1], "species": "Something else"},                          # same id, conflicting content
        {**base[2], "id": "dup-content"},                                  # same event, new id
        {"id": "m1", "date": "not a date", "latinName": "Ixodes ricinus", "location": "London", "species": "Castor bean tick"},
        {"id": "m2", "date": "2021-05-05T10:00:00", "latinName": "Ixodes ricinus", "location": None, "species": "Castor bean tick"},
        {"id": "m3", "date": None, "latinName": "Ixodes ricinus", "location": "London", "species": "Castor bean tick"},
        {"date": "2021-05-05T10:00:00", "latinName": "Ixodes ricinus", "location": "London", "species": "Castor bean tick"},
        {"id": "m4", "date": "2999-01-01T00:00:00", "latinName": "Ixodes ricinus", "location": "London", "species": "Castor bean tick"},
        {"id": "m5", "date": "12/06/2021", "latinName": "ixodes RICINUS", "location": "  LONDON ", "species": "castor bean TICK"},
        {"id": "m6", "date": "2021-06-13T08:00:00Z", "latinName": "Ixodes ricinus", "location": "Newcastle", "species": None},
        {"id": "m7", "date": "2021-06-14T08:00:00", "latinName": None, "location": "Atlantis", "species": "Hedgehog tick"},
        "garbage-row",
    ]
