"""Western Indian Ocean monitoring regions — Kenya-first, expandable."""

REGIONS = {
    "kenya_eez": {
        "name": "Kenya EEZ / Mombasa",
        "country": "Kenya",
        "min_lon": 39.0,
        "max_lon": 45.0,
        "min_lat": -5.0,
        "max_lat": 2.0,
        "primary": True,
        "status": "ACTIVE",
    },
    "tanzania_coast": {
        "name": "Tanzania coastal EEZ",
        "country": "Tanzania",
        "min_lon": 38.5,
        "max_lon": 42.0,
        "min_lat": -11.0,
        "max_lat": -4.5,
        "primary": False,
        "status": "PLANNED",
    },
    "seychelles": {
        "name": "Seychelles EEZ (core box)",
        "country": "Seychelles",
        "min_lon": 55.0,
        "max_lon": 57.5,
        "min_lat": -6.0,
        "max_lat": -3.5,
        "primary": False,
        "status": "PLANNED",
    },
    "n_mozambique_channel": {
        "name": "Northern Mozambique Channel",
        "country": "Multi-country",
        "min_lon": 40.0,
        "max_lon": 48.0,
        "min_lat": -15.0,
        "max_lat": -10.0,
        "primary": False,
        "status": "PLANNED",
    },
}