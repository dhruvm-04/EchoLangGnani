"""Deterministic, clearly fictional listings for the public demo directory."""

from __future__ import annotations

import re

from .directory import DirectoryStore


# Major metros and regional centres. The second value is a common local language.
CITIES = (
    ("Delhi", "Hindi"), ("Mumbai", "Marathi"), ("Bengaluru", "Kannada"),
    ("Hyderabad", "Telugu"), ("Chennai", "Tamil"), ("Kolkata", "Bengali"),
    ("Pune", "Marathi"), ("Ahmedabad", "Gujarati"), ("Surat", "Gujarati"),
    ("Jaipur", "Hindi"), ("Lucknow", "Hindi"), ("Kanpur", "Hindi"),
    ("Nagpur", "Marathi"), ("Indore", "Hindi"), ("Bhopal", "Hindi"),
    ("Patna", "Hindi"), ("Vadodara", "Gujarati"), ("Ludhiana", "Punjabi"),
    ("Agra", "Hindi"), ("Nashik", "Marathi"), ("Rajkot", "Gujarati"),
    ("Varanasi", "Hindi"), ("Ranchi", "Hindi"), ("Guwahati", "Assamese"),
    ("Visakhapatnam", "Telugu"), ("Vijayawada", "Telugu"),
    ("Coimbatore", "Tamil"), ("Madurai", "Tamil"), ("Kochi", "Malayalam"),
    ("Thiruvananthapuram", "Malayalam"), ("Kozhikode", "Malayalam"),
    ("Chandigarh", "Punjabi"), ("Amritsar", "Punjabi"), ("Jalandhar", "Punjabi"),
    ("Jodhpur", "Hindi"), ("Udaipur", "Hindi"), ("Bhubaneswar", "Odia"),
    ("Cuttack", "Odia"), ("Raipur", "Hindi"), ("Dehradun", "Hindi"),
    ("Mysuru", "Kannada"), ("Mangaluru", "Kannada"), ("Hubballi", "Kannada"),
    ("Tiruchirappalli", "Tamil"), ("Noida", "Hindi"), ("Gurugram", "Hindi"),
    ("Faridabad", "Hindi"), ("Ghaziabad", "Hindi"), ("Meerut", "Hindi"),
    ("Prayagraj", "Hindi"), ("Gwalior", "Hindi"), ("Jabalpur", "Hindi"),
    ("Nanded", "Marathi"), ("Aurangabad", "Marathi"), ("Srinagar", "Hindi"),
    ("Jammu", "Hindi"), ("Shimla", "Hindi"), ("Panaji", "Konkani"),
    ("Puducherry", "Tamil"), ("Siliguri", "Bengali"), ("Dhanbad", "Hindi"),
    ("Jamshedpur", "Hindi"), ("Bareilly", "Hindi"), ("Aligarh", "Hindi"),
    ("Nellore", "Telugu"), ("Tirupati", "Telugu"), ("Warangal", "Telugu"),
    ("Salem", "Tamil"), ("Thrissur", "Malayalam"), ("Kolhapur", "Marathi"),
    ("Solapur", "Marathi"), ("Belagavi", "Kannada"), ("Thane", "Marathi"),
    ("Navi Mumbai", "Marathi"), ("Howrah", "Bengali"), ("Gaya", "Hindi"),
    ("Muzaffarpur", "Hindi"), ("Bikaner", "Hindi"), ("Ajmer", "Hindi"),
    ("Kota", "Hindi"), ("Ujjain", "Hindi"), ("Bilaspur", "Hindi"),
    ("Rourkela", "Odia"), ("Durgapur", "Bengali"), ("Asansol", "Bengali"),
    ("Guntur", "Telugu"), ("Kakinada", "Telugu"), ("Rajahmundry", "Telugu"),
)

# Display name, searchable phrases, and how the service is usually delivered.
SERVICES = (
    ("Plumber", ("plumber", "plumbing", "pipe repair", "tap repair"), "Home visits"),
    ("Electrician", ("electrician", "electrical work", "wiring"), "Home visits"),
    ("Fan repair", ("fan repair", "ceiling fan repair", "fan service"), "Home visits"),
    ("AC repair", ("AC repair", "air conditioner repair", "AC service"), "Home visits"),
    ("Refrigerator repair", ("refrigerator repair", "fridge repair"), "Home visits"),
    ("Washing machine repair", ("washing machine repair", "washer repair"), "Home visits"),
    ("Water purifier repair", ("water purifier repair", "RO repair", "water filter service"), "Home visits"),
    ("Mobile phone repair", ("mobile phone repair", "phone repair"), "At the shop"),
    ("Laptop repair", ("laptop repair", "computer repair"), "At the shop"),
    ("Carpenter", ("carpenter", "carpentry", "furniture repair"), "Home visits"),
    ("Painter", ("painter", "house painting", "wall painting"), "Home visits"),
    ("Mason", ("mason", "masonry", "brickwork"), "Home visits"),
    ("Locksmith", ("locksmith", "lock repair", "key maker"), "Home visits"),
    ("Pest control", ("pest control", "termite treatment"), "Home visits"),
    ("House cleaning", ("house cleaning", "home cleaning", "cleaner"), "Home visits"),
    ("Sofa cleaning", ("sofa cleaning", "upholstery cleaning"), "Home visits"),
    ("Cook", ("cook", "home cook", "cooking service"), "Home visits"),
    ("Driver", ("driver", "chauffeur", "driving service"), "Customer pickup"),
    ("Tutor", ("tutor", "home tuition", "private teacher"), "Home visits or online"),
    ("Tailor", ("tailor", "tailoring", "clothes alteration"), "At the shop"),
    ("Beautician", ("beautician", "makeup artist", "beauty service"), "Home visits"),
    ("Hairdresser", ("hairdresser", "haircut", "barber"), "At the shop"),
    ("Gardener", ("gardener", "gardening", "garden maintenance"), "Home visits"),
    ("Car mechanic", ("car mechanic", "car repair", "auto mechanic"), "At the workshop"),
    ("Two-wheeler mechanic", ("two-wheeler mechanic", "bike repair", "scooter repair"), "At the workshop"),
    ("Packers and movers", ("packers and movers", "house shifting", "moving service"), "Home visits"),
    ("Laundry", ("laundry", "dry cleaning", "clothes washing"), "Pickup and drop-off"),
    ("Photographer", ("photographer", "event photography", "portrait photography"), "On location"),
    ("Event decorator", ("event decorator", "event decoration", "wedding decoration"), "On location"),
    ("CCTV installer", ("CCTV installation", "security camera installer"), "Home visits"),
    ("Internet technician", ("internet technician", "Wi-Fi setup", "router repair"), "Home visits"),
)

# Keep the demo directory small while giving the largest metros more choice.
EXTRA_CITIES = {"Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai", "Kolkata",
                "Pune", "Ahmedabad", "Jaipur", "Lucknow"}
AREA_NAMES = {
    "Delhi": "New Delhi, Delhi", "Bengaluru": "Bengaluru, Bangalore",
    "Gurugram": "Gurugram, Gurgaon", "Prayagraj": "Prayagraj, Allahabad",
    "Thiruvananthapuram": "Thiruvananthapuram, Trivandrum",
    "Aurangabad": "Aurangabad, Chhatrapati Sambhajinagar",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def demo_listings():
    """Yield 200 sample entries with stable IDs and unreachable 000 numbers."""
    number = 0
    services_by_label = {label: (phrases, delivery) for label, phrases, delivery in SERVICES}
    for index, (city, local_language) in enumerate(CITIES):
        languages = ", ".join(dict.fromkeys((local_language, "Hindi", "English")))
        primary = "Electrician" if index % 2 == 0 else "Plumber"
        speciality = SERVICES[(index * 7 + 3) % len(SERVICES)][0]
        if speciality == primary:
            speciality = SERVICES[(index * 7 + 4) % len(SERVICES)][0]
        if city == "Udaipur":
            speciality = "Fan repair"
        if city == "Nanded":
            primary = "Plumber"
            if speciality == primary:
                speciality = "Fan repair"
        labels = [primary, speciality]
        if city in EXTRA_CITIES:
            for candidate in ("Plumber", "Electrician", "Fan repair", "AC repair", "Carpenter"):
                if candidate not in labels:
                    labels.append(candidate)
                if len(labels) == 4:
                    break
        elif city == "Udaipur":
            labels.extend(("Fan repair", "Carpenter"))
        elif city == "Nanded":
            labels.extend(("Plumber", "Fan repair"))
        variants: dict[str, int] = {}
        for label in labels:
            variants[label] = variants.get(label, 0) + 1
            variant = variants[label]
            phrases, delivery = services_by_label[label]
            number += 1
            yield {
                "id": f"demo-{_slug(city)}-{_slug(label)}-{variant}",
                "name": f"Demo — {city} {label}" + (" Team" if variant > 1 else ""),
                "area": AREA_NAMES.get(city, city),
                "delivery": delivery,
                "phone": f"000{number:07d}",
                "hours": "Daily 9:00-21:00" if variant == 1 else "24/7",
                "languages": languages,
                "price": "Demo listing; quote on request",
                "services": phrases,
            }


def seed_demo(store: DirectoryStore) -> tuple[int, int]:
    return store.seed_demo(demo_listings())
