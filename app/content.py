"""Educational content served to the frontend (kept server-side so it is versioned with the API)."""

SPECIES_GUIDE = [
    {
        "species": "Castor bean tick", "latin_name": "Ixodes ricinus", "in_dataset": False,
        "headline": "The UK's most common tick, and the main carrier of Lyme disease.",
        "size": "Adults about 3 mm unfed; nymphs about the size of a poppy seed",
        "look": "Reddish-brown to dark body, dark legs, no pattern on the back. Swells and turns grey-blue when fed.",
        "habitat": "Woodland, heathland, moorland, rough grass and parks with leaf litter.",
        "hosts": "Deer, sheep, small mammals, birds, dogs, cats and people.",
        "why": "Can carry the bacteria that cause Lyme disease. Not in the provided dataset, shown here for identification context.",
    },
    {
        "species": "Fox/badger tick", "latin_name": "Ixodes canisuga", "in_dataset": True,
        "headline": "Linked to dens and burrows, and sometimes found on dogs.",
        "size": "Small; similar in size to other Ixodes ticks",
        "look": "Brownish body with a rounded outline. Hard to tell from other Ixodes ticks without a microscope.",
        "habitat": "Dens, setts, kennels and the ground around them.",
        "hosts": "Foxes, badgers, dogs.",
        "why": "Mostly a nuisance for dogs and wildlife. Check dogs that spend time in dens or kennels.",
    },
    {
        "species": "Southern rodent tick", "latin_name": "Ixodes acuminatus", "in_dataset": True,
        "headline": "Lives in the nests and burrows of small mammals.",
        "size": "Small; adults only a few millimetres",
        "look": "Dark, compact body. Usually seen only when it has moved onto a pet or person.",
        "habitat": "Rodent burrows and nests, scrub and hedgerow bases.",
        "hosts": "Small rodents; occasionally carnivores.",
        "why": "Rarely meets people, but may reach pets that hunt small mammals.",
    },
    {
        "species": "Marsh tick", "latin_name": "Ixodes apronophorus", "in_dataset": True,
        "headline": "A wetland specialist.",
        "size": "Small; a few millimetres",
        "look": "Brown body, similar to other Ixodes ticks.",
        "habitat": "Marshes, fens, damp meadows and reedy ground.",
        "hosts": "Small mammals and ground-feeding birds.",
        "why": "Take extra care after walking through wet, reedy areas.",
    },
    {
        "species": "Tree-hole tick", "latin_name": "Ixodes arboricola", "in_dataset": True,
        "headline": "Found where birds nest in tree holes and boxes.",
        "size": "Small; a few millimetres",
        "look": "Brown, rounded body.",
        "habitat": "Tree holes, nest boxes and the surrounding trunk.",
        "hosts": "Hole-nesting birds such as tits and starlings.",
        "why": "Mostly a concern for people who handle nest boxes or ring birds. Wear gloves.",
    },
    {
        "species": "Passerine tick", "latin_name": "Dermacentor frontalis", "in_dataset": True,
        "headline": "A bird-associated tick recorded in the dataset.",
        "size": "Small; a few millimetres",
        "look": "Brown body, may show faint markings on the back.",
        "habitat": "Hedgerows, gardens and woodland edges where birds feed.",
        "hosts": "Passerine (perching) birds.",
        "why": "Ground-feeding birds can carry ticks into gardens. Check pets after garden play.",
    },
]

PREVENTION_TIPS = [
    {"icon": "shirt", "title": "Cover up", "text": "In grass, woodland or heath wear long trousers tucked into socks and light-coloured clothes so ticks are easier to spot."},
    {"icon": "spray", "title": "Use repellent", "text": "Apply a repellent containing DEET to exposed skin and clothing, following the label."},
    {"icon": "path", "title": "Stay on paths", "text": "Walk in the middle of paths and avoid brushing against long grass and bracken."},
    {"icon": "search", "title": "Check your body", "text": "After outdoor time check yourself and your children. Look in warm, hidden places: armpits, groin, behind knees, scalp and hairline."},
    {"icon": "paw", "title": "Check your pets", "text": "Run your hands over your dog or cat after walks, especially ears, neck, chest and between toes. Ask your vet about tick treatment suited to your pet."},
    {"icon": "home", "title": "Tidy your garden", "text": "Keep grass short, clear leaf litter and leave a gap between lawns and wooded edges."},
]

REMOVAL_STEPS = [
    "Use fine-tipped tweezers or a tick removal tool. Do not use petroleum jelly, alcohol or heat.",
    "Grip the tick as close to the skin as possible.",
    "Pull steadily upwards, without twisting or squeezing the body.",
    "Clean the bite and your hands with soap and water or an antiseptic.",
    "Note the date. Watch the bite for a few weeks.",
]

SEE_A_PROFESSIONAL = (
    "See a doctor if you develop an expanding red rash, flu-like symptoms, fever, headache or aching joints "
    "in the weeks after a tick bite. Contact your vet if a pet is unwell after a tick bite or you cannot remove the tick."
)

DISCLAIMER = "Educational information only. It is not medical or veterinary advice."
