"""Profile a downloaded payload with the same cleaning rules the pipeline uses.

    python scripts/profile_data.py sightings.json
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cleaning import process_batch  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "sightings.json"
raw = json.load(open(path))
res = process_batch(raw)
print(f"records in file      : {len(raw)}")
print(f"accepted             : {len(res.clean)}")
print(f"rejected             : {len(res.rejected)}  {res.reject_reasons}")
print(f"flags on accepted    : {res.flag_counts}")
keys = Counter(k for r in raw if isinstance(r, dict) for k in r)
print(f"field names seen     : {dict(keys)}")
dates = sorted(r.occurred_at for r in res.clean)
if dates:
    print(f"date range           : {dates[0].date()} -> {dates[-1].date()}")
print(f"cities               : {dict(Counter(r.location for r in res.clean).most_common())}")
print(f"unmapped cities      : {sorted({r.location for r in res.clean if r.region == 'Unknown'})}")
print(f"species              : {dict(Counter((r.species, r.latin_name) for r in res.clean).most_common())}")
raw_loc = Counter(r.get('location') for r in raw if isinstance(r, dict))
print(f"raw location spellings: {len(raw_loc)} distinct -> {len({r.location for r in res.clean})} after cleaning")
if res.rejected:
    print("sample rejections    :", [(x.reason, x.raw) for x in res.rejected[:5]])
