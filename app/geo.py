"""City centroids (lat, lng) used to place sightings on the map.

The upstream data only carries a city name, so the map is city-level by design:
one marker per city, sized by the number of sightings. Honest about that limit in the UI.
"""
CITY_COORDS: dict[str, tuple[float, float]] = {
    "London": (51.5074, -0.1278), "Manchester": (53.4808, -2.2426), "Liverpool": (53.4084, -2.9916),
    "Lancaster": (54.0466, -2.8007), "Carlisle": (54.8925, -2.9329), "Chester": (53.1930, -2.8931),
    "Preston": (53.7632, -2.7031), "Salford": (53.4875, -2.2901), "Blackpool": (53.8175, -3.0357),
    "Newcastle upon Tyne": (54.9783, -1.6178), "Sunderland": (54.9069, -1.3838), "Durham": (54.7761, -1.5733),
    "Middlesbrough": (54.5742, -1.2350), "Leeds": (53.8008, -1.5491), "Sheffield": (53.3811, -1.4701),
    "Bradford": (53.7960, -1.7594), "York": (53.9590, -1.0815), "Hull": (53.7676, -0.3274),
    "Wakefield": (53.6830, -1.4977), "Nottingham": (52.9548, -1.1581), "Leicester": (52.6369, -1.1398),
    "Derby": (52.9225, -1.4746), "Lincoln": (53.2307, -0.5406), "Northampton": (52.2405, -0.9027),
    "Birmingham": (52.4862, -1.8904), "Coventry": (52.4068, -1.5197), "Wolverhampton": (52.5870, -2.1288),
    "Stoke-on-Trent": (53.0027, -2.1794), "Worcester": (52.1920, -2.2200), "Hereford": (52.0565, -2.7160),
    "Lichfield": (52.6810, -1.8265), "Norwich": (52.6309, 1.2974), "Cambridge": (52.2053, 0.1218),
    "Peterborough": (52.5695, -0.2405), "Chelmsford": (51.7356, 0.4685), "Ipswich": (52.0567, 1.1482),
    "St Albans": (51.7520, -0.3360), "Colchester": (51.8959, 0.8919), "Brighton": (50.8225, -0.1372),
    "Oxford": (51.7520, -1.2577), "Southampton": (50.9097, -1.4044), "Portsmouth": (50.8198, -1.0880),
    "Canterbury": (51.2802, 1.0789), "Winchester": (51.0632, -1.3080), "Reading": (51.4543, -0.9781),
    "Milton Keynes": (52.0406, -0.7594), "Guildford": (51.2362, -0.5704), "Bristol": (51.4545, -2.5879),
    "Bath": (51.3811, -2.3590), "Exeter": (50.7184, -3.5339), "Plymouth": (50.3755, -4.1427),
    "Gloucester": (51.8642, -2.2380), "Salisbury": (51.0688, -1.7945), "Truro": (50.2632, -5.0510),
    "Glasgow": (55.8642, -4.2518), "Edinburgh": (55.9533, -3.1883), "Aberdeen": (57.1497, -2.0943),
    "Dundee": (56.4620, -2.9707), "Inverness": (57.4778, -4.2247), "Stirling": (56.1165, -3.9369),
    "Perth": (56.3950, -3.4308), "Cardiff": (51.4816, -3.1791), "Swansea": (51.6214, -3.9436),
    "Newport": (51.5842, -2.9977), "Wrexham": (53.0430, -2.9925), "Belfast": (54.5973, -5.9301),
    "Derry": (54.9966, -7.3086), "Lisburn": (54.5162, -6.0580), "Armagh": (54.3503, -6.6528),
    "Newry": (54.1751, -6.3402),
}


def coords_for(city: str) -> tuple[float, float] | None:
    return CITY_COORDS.get(city)
