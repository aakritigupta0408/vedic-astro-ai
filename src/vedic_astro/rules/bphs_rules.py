"""
bphs_rules.py — Hardcoded classical Parashari rules from
Brihat Parashara Hora Shastra (BPHS).

Organised into lookup tables keyed by planet, house, sign, domain, and
yoga type so rule_selector.py can pull the most relevant subset for any chart.

Sources: BPHS chapters on Bhava Phala, Graha Drishti, Dasha Phala,
Yoga Adhyaya, and Stri Jataka.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Planetary dignities
# ─────────────────────────────────────────────────────────────────────────────

EXALTATION_SIGN: dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
    "Saturn": "Libra", "Rahu": "Gemini", "Ketu": "Sagittarius",
}

DEBILITATION_SIGN: dict[str, str] = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
    "Saturn": "Aries", "Rahu": "Sagittarius", "Ketu": "Gemini",
}

OWN_SIGNS: dict[str, list[str]] = {
    "Sun":     ["Leo"],
    "Moon":    ["Cancer"],
    "Mars":    ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"],
    "Jupiter": ["Sagittarius", "Pisces"],
    "Venus":   ["Taurus", "Libra"],
    "Saturn":  ["Capricorn", "Aquarius"],
}

MOOLATRIKONA: dict[str, str] = {
    "Sun": "Leo", "Moon": "Taurus", "Mars": "Aries",
    "Mercury": "Virgo", "Jupiter": "Sagittarius",
    "Venus": "Libra", "Saturn": "Aquarius",
}

# Natural friendships (BPHS Ch. 3)
NATURAL_FRIENDS: dict[str, list[str]] = {
    "Sun":     ["Moon", "Mars", "Jupiter"],
    "Moon":    ["Sun", "Mercury"],
    "Mars":    ["Sun", "Moon", "Jupiter"],
    "Mercury": ["Sun", "Venus"],
    "Jupiter": ["Sun", "Moon", "Mars"],
    "Venus":   ["Mercury", "Saturn"],
    "Saturn":  ["Mercury", "Venus"],
    "Rahu":    ["Venus", "Saturn"],
    "Ketu":    ["Mars", "Jupiter"],
}

NATURAL_ENEMIES: dict[str, list[str]] = {
    "Sun":     ["Venus", "Saturn"],
    "Moon":    ["None"],
    "Mars":    ["Mercury"],
    "Mercury": ["Moon"],
    "Jupiter": ["Mercury", "Venus"],
    "Venus":   ["Sun", "Moon"],
    "Saturn":  ["Sun", "Moon", "Mars"],
    "Rahu":    ["Sun", "Moon"],
    "Ketu":    ["Venus"],
}

DIGNITY_RULES: dict[str, str] = {
    "exalted":      "An exalted planet gives full, unobstructed results of its significations; it strengthens its house and the houses it aspects.",
    "debilitated":  "A debilitated planet gives weak, distorted, or delayed results; it harms the houses it rules unless a cancellation (Neecha Bhanga) applies.",
    "own_sign":     "A planet in its own sign is strong and stable; it protects and sustains its house significations.",
    "moolatrikona": "A planet in Moolatrikona gives excellent, reliable results — stronger than own sign for many purposes.",
    "friendly":     "A planet in a friendly sign is comfortable and gives good results, though less powerful than own sign.",
    "enemy":        "A planet in an enemy sign is uncomfortable and gives mixed or troubled results.",
    "combust":      "A combust planet (within 6° of Sun) loses its power and independence; its significations suffer.",
    "retrograde":   "A retrograde planet intensifies its significations and revisits themes of its house; it can give unusual or delayed results.",
}

NEECHA_BHANGA_RULES: list[str] = [
    "Neecha Bhanga (cancellation of debilitation) occurs when: (1) the lord of the debilitation sign is in a kendra from Lagna or Moon; (2) the exaltation lord of the debilitated planet is in a kendra; (3) the debilitated planet is aspected by its exaltation lord; (4) the debilitated planet is in conjunction with or aspected by the lord of its sign.",
    "When Neecha Bhanga applies, the debilitated planet behaves like an exalted planet and confers Raj Yoga results.",
]

# ─────────────────────────────────────────────────────────────────────────────
# House (Bhava) significations — BPHS Ch. 11
# ─────────────────────────────────────────────────────────────────────────────

HOUSE_SIGNIFICATIONS: dict[int, dict] = {
    1:  {"name": "Tanu Bhava",    "governs": ["self", "body", "health", "appearance", "vitality", "fame", "character", "longevity"],
         "karaka": "Sun"},
    2:  {"name": "Dhana Bhava",   "governs": ["wealth", "family", "speech", "food", "right eye", "face", "accumulated assets", "oral tradition"],
         "karaka": "Jupiter"},
    3:  {"name": "Sahaja Bhava",  "governs": ["courage", "siblings", "communication", "short travel", "right ear", "arts", "effort", "valor"],
         "karaka": "Mars"},
    4:  {"name": "Sukha Bhava",   "governs": ["mother", "home", "property", "vehicles", "education", "happiness", "heart", "chest"],
         "karaka": "Moon"},
    5:  {"name": "Putra Bhava",   "governs": ["children", "intellect", "past merit", "Purva Punya", "romance", "speculation", "creativity", "mantra"],
         "karaka": "Jupiter"},
    6:  {"name": "Shatru Bhava",  "governs": ["enemies", "disease", "debt", "service", "litigation", "digestion", "maternal uncle"],
         "karaka": "Mars/Saturn"},
    7:  {"name": "Kalatra Bhava", "governs": ["spouse", "marriage", "partnerships", "desires", "trade", "foreign travel", "loins"],
         "karaka": "Venus"},
    8:  {"name": "Ayur Bhava",    "governs": ["longevity", "death", "transformation", "hidden matters", "inheritance", "occult", "chronic disease"],
         "karaka": "Saturn"},
    9:  {"name": "Dharma Bhava",  "governs": ["father", "dharma", "fortune", "guru", "higher learning", "pilgrimage", "religion", "past life merit"],
         "karaka": "Sun/Jupiter"},
    10: {"name": "Karma Bhava",   "governs": ["career", "profession", "status", "authority", "actions", "public life", "government", "honors"],
         "karaka": "Sun/Mercury/Jupiter/Saturn"},
    11: {"name": "Labha Bhava",   "governs": ["gains", "income", "elder siblings", "ambitions", "fulfillment of desires", "left ear", "friends"],
         "karaka": "Jupiter"},
    12: {"name": "Vyaya Bhava",   "governs": ["losses", "expenditure", "liberation", "foreign lands", "bed pleasures", "left eye", "sleep", "charity"],
         "karaka": "Saturn"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Planet in house results — BPHS Bhava Phala chapters
# ─────────────────────────────────────────────────────────────────────────────

PLANET_IN_HOUSE: dict[str, dict[int, str]] = {
    "Sun": {
        1:  "Sun in Lagna gives strong constitution, commanding personality, vitality, and leadership; native is bold, proud, and fond of power.",
        2:  "Sun in 2nd: fluctuating wealth, harsh speech, family disputes; can harm father's finances; good for government service.",
        3:  "Sun in 3rd: courageous, strong-willed, may harm siblings; good for self-effort; bold communication.",
        4:  "Sun in 4th: unhappy domestic life, troubled relationship with mother; may lose ancestral property but gain from government.",
        5:  "Sun in 5th: few children or delay; intelligent, good administrative ability; inclined to positions of authority.",
        6:  "Sun in 6th: defeats enemies, government service, good health; may harm maternal relations.",
        7:  "Sun in 7th: spouse may be domineering or weak; delays in marriage; business partnerships with powerful people.",
        8:  "Sun in 8th: eye trouble, weak constitution, short life unless cancelled; father's early death; obstacles to inheritance.",
        9:  "Sun in 9th: fortunate, devoted to dharma; good relationship with father; becomes a respected teacher or authority.",
        10: "Sun in 10th: powerful career, fame, authority; rise in government or corporate hierarchy; strong Karma Bhava.",
        11: "Sun in 11th: steady income, fulfillment of ambitions, gains through government; powerful elder sibling.",
        12: "Sun in 12th: expenditure on charitable causes; weak eyesight; possible foreign settlement; spiritual inclinations.",
    },
    "Moon": {
        1:  "Moon in Lagna: attractive, emotional, imaginative, fond of travel; mind sensitive to environment; strong if waxing.",
        2:  "Moon in 2nd: wealth through mother or fluids/food; beautiful face; melodious speech; fluctuating finances.",
        3:  "Moon in 3rd: courageous but restless; mental siblings; good writing or communication skills; travels frequently.",
        4:  "Moon in 4th (own house): very auspicious; happy home, devoted mother, property, vehicles; emotional comfort.",
        5:  "Moon in 5th: intelligent, creative, many children; romantic; stomach disorders possible; good memory.",
        6:  "Moon in 6th: digestive problems, enemies among women; maternal relations troubled; service-oriented.",
        7:  "Moon in 7th: attractive spouse, fond of pleasures; multiple relationships; emotional in partnerships.",
        8:  "Moon in 8th: weak constitution, chronic ailments, mental anxiety; mother's health troubled; occult interests.",
        9:  "Moon in 9th: fortunate, devoted to mother and guru; pilgrimages; spiritual mind; father prosperous.",
        10: "Moon in 10th: fame, public popularity, career in public service or creative fields; changes in profession.",
        11: "Moon in 11th: steady gains, fulfilled desires, good elder siblings; income through women or public.",
        12: "Moon in 12th: expenses through women, sleep disorders, possible addiction; spiritual liberation; foreign residence.",
    },
    "Mars": {
        1:  "Mars in Lagna: bold, aggressive, athletic; prone to accidents and disputes; Manglik dosha active; leadership qualities.",
        2:  "Mars in 2nd: harsh speech, family quarrels, financial fluctuations; Manglik dosha; may cut or injure face.",
        3:  "Mars in 3rd (own house for Scorpio): courageous, enterprising; good for martial arts, sports, siblings.",
        4:  "Mars in 4th: property disputes, difficult relationship with mother; Manglik dosha; disrupted home life.",
        5:  "Mars in 5th: few children, possible abortion; speculative losses; clever intellect; leadership in education.",
        6:  "Mars in 6th: defeats enemies, excellent for competition and litigation; strong digestion; military or police.",
        7:  "Mars in 7th: Manglik dosha strong; marital conflicts, domineering spouse or aggressive partner; business litigation.",
        8:  "Mars in 8th: Manglik dosha; accidents, surgeries, short life tendency; inheritance through conflict; occult interest.",
        9:  "Mars in 9th: strong dharmic convictions, disputes with father or guru; courageous religious stance.",
        10: "Mars in 10th: powerful career in engineering, military, surgery, law; authoritative; risk of sudden fall from position.",
        11: "Mars in 11th: gains through property, land, machinery; disputes with elder siblings; ambitious and achieving.",
        12: "Mars in 12th: secret enemies, expenditure on disputes; bed pleasures; foreign lands for work; spiritual warrior.",
    },
    "Mercury": {
        1:  "Mercury in Lagna: intelligent, witty, good communicator; versatile; youthful appearance; business-minded.",
        2:  "Mercury in 2nd: eloquent speech, multiple income sources, learning languages; wealth through communication.",
        3:  "Mercury in 3rd: excellent writer, speaker, communicator; business acumen; good with siblings.",
        4:  "Mercury in 4th: educated, property through intellect; good relationship with mother; conveyances; analytical mind.",
        5:  "Mercury in 5th: sharp intellect, good with mathematics and strategy; multiple children; creative mind.",
        6:  "Mercury in 6th: defeats enemies through intellect; good for medicine, law, analysis; digestive issues.",
        7:  "Mercury in 7th: intelligent, business-minded spouse; multiple partnerships; commerce; witty partner.",
        8:  "Mercury in 8th: interest in occult and research; longevity through intellect; inheritance through writing.",
        9:  "Mercury in 9th: learned, philosophical mind; good teacher; gains through father; writing on dharmic topics.",
        10: "Mercury in 10th: career in writing, teaching, business, accounting, law; communication-based profession.",
        11: "Mercury in 11th: gains through intellect and communication; multiple income streams; learned elder siblings.",
        12: "Mercury in 12th: expenditure on education or communication; writing for liberation; possible foreign career.",
    },
    "Jupiter": {
        1:  "Jupiter in Lagna: wise, generous, optimistic, spiritually inclined; good health; respected; natural teacher.",
        2:  "Jupiter in 2nd: great wealth, eloquent speech, large family; excellent for finances; charitable disposition.",
        3:  "Jupiter in 3rd: religious siblings; moderate courage; publishing, teaching, or spiritual writing.",
        4:  "Jupiter in 4th: happy home, educated mother, property and vehicles; emotional contentment; strong roots.",
        5:  "Jupiter in 5th (natural house): brilliant intellect, good children, powerful past merit; mantra siddhi; prosperity.",
        6:  "Jupiter in 6th: defeats enemies through wisdom; service to dharma; digestive issues; teacher in service.",
        7:  "Jupiter in 7th: noble and wise spouse; blessed marriage; strong business partnerships; gains after marriage.",
        8:  "Jupiter in 8th: longevity, inheritance, interest in philosophy of death; occult wisdom; recovery from illness.",
        9:  "Jupiter in 9th (own house): extremely fortunate, wise, devoted; guru's blessings; father is noble; Dharma Yoga.",
        10: "Jupiter in 10th: respected career in law, education, religion, government; high status; honors.",
        11: "Jupiter in 11th: abundant gains, powerful connections, fulfillment of all wishes; wealthy elder siblings.",
        12: "Jupiter in 12th: spiritual liberation, foreign travel for learning; expenditure on dharmic causes; moksha-oriented.",
    },
    "Venus": {
        1:  "Venus in Lagna: beautiful, charming, artistic, fond of luxury; magnetic personality; pleasure-seeking.",
        2:  "Venus in 2nd: wealthy, beautiful voice, good family life; gains from women; arts and luxury goods.",
        3:  "Venus in 3rd: artistic communication, beautiful voice; gains through media or arts; harmonious siblings.",
        4:  "Venus in 4th: luxurious home, good relationship with mother; beautiful vehicles; emotional happiness.",
        5:  "Venus in 5th: romantic, creative, multiple love affairs; artistic children; good for creative professions.",
        6:  "Venus in 6th: defeats enemies through charm; health issues related to kidneys or reproductive system; workplace romances.",
        7:  "Venus in 7th (natural karaka): beautiful and devoted spouse; happy marriage; strong desires; gains through partnership.",
        8:  "Venus in 8th: long life (Venus as longevity karaka); gains from spouse's wealth; interest in hidden beauty.",
        9:  "Venus in 9th: fortunate, beautiful, artistic; gains from father; devoted to dharma through beauty and arts.",
        10: "Venus in 10th: career in arts, fashion, music, entertainment, diplomacy; public admiration; beautiful work.",
        11: "Venus in 11th: gains through women, arts, or luxury; fulfilled romantic desires; beautiful elder siblings.",
        12: "Venus in 12th: bed pleasures, expenditure on luxury; possible foreign romance; spiritual devotion through beauty.",
    },
    "Saturn": {
        1:  "Saturn in Lagna: delays in life events, serious demeanor, hardworking; health issues early in life; wisdom through hardship.",
        2:  "Saturn in 2nd: slow wealth accumulation, restricted speech; delayed family growth; speaks carefully.",
        3:  "Saturn in 3rd: determined, disciplined effort; few siblings or strained relations; steady communication.",
        4:  "Saturn in 4th: property delays, difficult relationship with mother; old home; unhappy domestic environment.",
        5:  "Saturn in 5th: few children or delayed; serious intellect; past-life karma through children; disciplined creativity.",
        6:  "Saturn in 6th (strong placement): powerful destruction of enemies; excellent for service, law, medicine.",
        7:  "Saturn in 7th: delayed marriage, older spouse; serious partnerships; business requires patience.",
        8:  "Saturn in 8th (natural house): long life; interest in occult; chronic ailments; inheritance delayed.",
        9:  "Saturn in 9th: disciplined dharma, philosophical mind; father may be absent or strict; slow fortune.",
        10: "Saturn in 10th (exalted in Libra/10th): powerful career through sustained effort; rise after age 36; authority.",
        11: "Saturn in 11th: gains after sustained effort; income through service, industry, or real estate; older friends.",
        12: "Saturn in 12th (own house Aquarius): spiritual liberation, solitude, foreign lands; disciplined expenditure.",
    },
    "Rahu": {
        1:  "Rahu in Lagna: ambitious, unconventional personality; strong desire for recognition; foreign or unusual qualities.",
        2:  "Rahu in 2nd: wealth through unusual means; unorthodox speech; foreign foods or languages; fluctuating family.",
        3:  "Rahu in 3rd: courageous and ambitious; gains through media or foreign communication; bold siblings.",
        4:  "Rahu in 4th: disrupted home life, unusual mother; property through unconventional means; foreign residence.",
        5:  "Rahu in 5th: unconventional intellect; foreign children or adoption; speculative gains; past-life obsessions.",
        6:  "Rahu in 6th: powerful for destroying enemies; good for foreign service; digestive issues.",
        7:  "Rahu in 7th: unconventional or foreign spouse; multiple relationships; business with foreigners.",
        8:  "Rahu in 8th: occult power, sudden gains/losses; interest in death and transformation; foreign inheritance.",
        9:  "Rahu in 9th: unconventional dharma; foreign guru; gains through foreign cultures; challenges to father.",
        10: "Rahu in 10th: rise through foreign or unconventional career; fame through unusual means; political ambition.",
        11: "Rahu in 11th: large gains, fulfillment of unusual desires; gains through foreigners or technology.",
        12: "Rahu in 12th: foreign travel, bed pleasures; spiritual confusion; losses through deception; hidden enemies.",
    },
    "Ketu": {
        1:  "Ketu in Lagna: spiritual, detached personality; past-life mastery over self; unusual or mysterious appearance.",
        2:  "Ketu in 2nd: spiritual speech, detachment from wealth; unusual family; past-life wealth karma.",
        3:  "Ketu in 3rd: past-life courage; detachment from siblings; spiritual communication; pilgrimage travel.",
        4:  "Ketu in 4th: detachment from home and mother; spiritual roots; past-life connection to land.",
        5:  "Ketu in 5th: past-life children karma; spiritual intellect; interest in occult and mantras.",
        6:  "Ketu in 6th: good for overcoming enemies and disease through spiritual means; past-life service.",
        7:  "Ketu in 7th: detachment from marriage; unusual spouse; past-life partner karma; spiritual partnerships.",
        8:  "Ketu in 8th: moksha indicator; past-life occult mastery; sudden events; liberation through transformation.",
        9:  "Ketu in 9th: past-life dharma; detachment from father or guru; unconventional spiritual path.",
        10: "Ketu in 10th: past-life career mastery; detachment from status; spiritual actions; public service.",
        11: "Ketu in 11th: past-life gains exhausted; detachment from desires; spiritual community.",
        12: "Ketu in 12th (own house for Scorpio): moksha, liberation, deep spirituality; past-life foreign settlement.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# House lord results — BPHS Bhavesh Phala
# ─────────────────────────────────────────────────────────────────────────────

HOUSE_LORD_IN_HOUSE: dict[int, dict[int, str]] = {
    # Lord of house X placed in house Y
    1: {
        1: "Lagna lord in Lagna: self-made, strong constitution, prominent personality, confident.",
        4: "Lagna lord in 4th: happiness, property, vehicles, devoted to mother; comforts at home.",
        5: "Lagna lord in 5th: intelligent, good children, fortunate through past merit.",
        7: "Lagna lord in 7th: life revolves around partnership and marriage; identity through relationships.",
        9: "Lagna lord in 9th: highly fortunate, dharmic, blessed by father and guru; fortune follows.",
        10: "Lagna lord in 10th: strong career focus; life purpose tied to profession; success in public life.",
        11: "Lagna lord in 11th: gains and income are central to life; ambitious and achieving.",
    },
    7: {
        1: "7th lord in Lagna: spouse is prominent in native's life; early marriage; partner affects health.",
        2: "7th lord in 2nd: gains from marriage; spouse contributes to family wealth; speech about partnerships.",
        7: "7th lord in own house: strong marriage focus; devoted and faithful spouse; gains through partnerships.",
        9: "7th lord in 9th: fortunate marriage; spouse is dharmic and wise; marriage brings great fortune.",
        10: "7th lord in 10th: career through partnership; public partnerships; spouse may be career-focused.",
        11: "7th lord in 11th: gains from marriage and partnerships; spouse brings income; fulfilling relationships.",
    },
    10: {
        1: "10th lord in Lagna: career tied to personality; self-employed tendency; career is identity.",
        2: "10th lord in 2nd: career brings wealth; profession in finance, speech, or family business.",
        9: "10th lord in 9th: career in dharma, education, or law; Dharma-Karma Adhipati Yoga if same planet.",
        10: "10th lord in own house: strong career, rise to prominence in profession; karma is clear.",
        11: "10th lord in 11th: career brings abundant gains; fulfills career ambitions; income from profession.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Major Yogas — BPHS Yoga Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

YOGA_RULES: dict[str, str] = {
    # Raj Yogas
    "Raj Yoga": "Raj Yoga forms when lords of a kendra (1,4,7,10) and a trikona (1,5,9) conjoin or mutually aspect each other. It confers power, authority, and status — results depend on the strength of the planets involved.",
    "Dharma-Karma Adhipati Yoga": "When the 9th lord (dharma) and 10th lord (karma) conjoin or exchange, this powerful Raj Yoga gives success in career through righteous means, fame, and high status.",
    "Gaj Kesari Yoga": "Jupiter in a kendra (1,4,7,10) from Moon makes the native wise, eloquent, prosperous, and famous — like the noble combination of elephant and lion.",
    "Budha-Aditya Yoga": "Sun and Mercury conjoin in any house, giving intelligence, administrative ability, and career success in government or business. Strengthened if in Leo or Virgo.",
    "Hamsa Yoga": "Jupiter in own or exaltation sign in a kendra — a Pancha Mahapurusha Yoga giving wisdom, spirituality, respected status, and prosperity.",
    "Malavya Yoga": "Venus in own or exaltation sign in a kendra — Pancha Mahapurusha Yoga giving beauty, luxury, arts, marital happiness, and material comfort.",
    "Ruchaka Yoga": "Mars in own or exaltation sign (Aries, Scorpio, Capricorn) in a kendra — Pancha Mahapurusha Yoga giving courage, physical prowess, leadership, and military success.",
    "Sasa Yoga": "Saturn in own or exaltation sign (Capricorn, Aquarius, Libra) in a kendra — Pancha Mahapurusha Yoga giving discipline, authority, wealth through hard work, and longevity.",
    "Bhadra Yoga": "Mercury in own or exaltation sign (Gemini, Virgo) in a kendra — Pancha Mahapurusha Yoga giving intelligence, communication skills, business success, and wisdom.",
    "Dhana Yoga": "Lords of 2nd and 11th houses conjoin, exchange, or mutually aspect; or Lagna lord joins 2nd/11th lord. Gives wealth accumulation proportional to the planets' strength.",
    "Viparita Raja Yoga": "Lords of 6th, 8th, or 12th in each other's houses or conjoined — native rises through others' adversity; gains from misfortune; hidden power.",
    "Chandra-Mangala Yoga": "Moon and Mars conjoin or mutually aspect — gives wealth through business, especially involving land, property, or food.",
    "Lakshmi Yoga": "9th lord strong and in own or exaltation sign, and Lagna lord in a kendra or trikona — gives great wealth, prosperity, and goddess Lakshmi's blessings.",
    "Saraswati Yoga": "Jupiter, Venus, and Mercury all in kendras or trikonas — gives exceptional learning, artistic talent, eloquence, and prosperity.",
    # Doshas
    "Manglik Dosha": "Mars in 1st, 2nd, 4th, 7th, 8th, or 12th house causes Manglik Dosha — can bring delays in marriage, marital conflict, or harm to spouse unless cancelled by matching chart or placement.",
    "Kemadruma Yoga": "No planet in the 2nd or 12th from Moon and Moon is not in a kendra from Lagna — gives poverty, mental instability, and misfortune. Cancelled if Moon is with a planet or in a kendra.",
    "Shakat Yoga": "Moon in 6th, 8th, or 12th from Jupiter — ups and downs in fortune; wheel of fate; rises and falls in status.",
    "Grahan Yoga": "Sun or Moon conjunct Rahu or Ketu — eclipse yoga; obstacles to the bhava involved; psychological complexity; karmic lessons.",
    "Daridra Yoga": "Lords of 6th, 8th, 12th in kendras or trikonas without benefic influence — persistent financial hardship.",
    "Voshi Yoga": "Planet other than Moon in 12th from Sun — native is skilled, charitable, and endowed with the qualities of that planet.",
    "Veshi Yoga": "Planet other than Moon in 2nd from Sun — gives strength, speech, and financial characteristics of that planet.",
}

# ─────────────────────────────────────────────────────────────────────────────
# Dasha lord results — BPHS Vimshottari Dasha Phala
# ─────────────────────────────────────────────────────────────────────────────

DASHA_LORD_RULES: dict[str, str] = {
    "Sun":     "Sun Mahadasha (6 years): career advancement, government dealings, father's health prominent; results depend on Sun's house, sign, and dignity.",
    "Moon":    "Moon Mahadasha (10 years): emotional changes, travel, mother prominent; business and property matters; fluctuating mind.",
    "Mars":    "Mars Mahadasha (7 years): energy, ambition, property and land matters; siblings prominent; conflict and litigation; surgery possible.",
    "Rahu":    "Rahu Mahadasha (18 years): unconventional experiences, foreign travel, sudden gains or losses; ambition, material focus; confusion in dharma.",
    "Jupiter": "Jupiter Mahadasha (16 years): expansion, marriage, children, learning, wealth; a generally auspicious period unless Jupiter is afflicted.",
    "Saturn":  "Saturn Mahadasha (19 years): hard work, discipline, delays, service; results come slowly but last; karma is settled; health of joints.",
    "Mercury": "Mercury Mahadasha (17 years): business, communication, intellect; education, writing, commerce; results depend on Mercury's position.",
    "Ketu":    "Ketu Mahadasha (7 years): spirituality, detachment, occult, past-life themes; sudden unexpected events; liberation themes.",
    "Venus":   "Venus Mahadasha (20 years): marriage, love, luxury, arts, comforts; prosperity for most; results depend on Venus's sign and house.",
}

ANTARDASHA_RULES: dict[str, dict[str, str]] = {
    "Jupiter": {
        "Saturn": "Jupiter-Saturn antardasha: discipline meets expansion; career consolidation; slow but lasting gains; possible religious-material tension.",
        "Mercury": "Jupiter-Mercury antardasha: excellent for learning, business, writing, education; intellectual and financial growth.",
        "Venus": "Jupiter-Venus antardasha: highly auspicious for marriage, pleasure, wealth; artistic and spiritual harmony.",
        "Mars": "Jupiter-Mars antardasha: courage meets wisdom; good for property, legal matters, and bold ventures.",
        "Rahu": "Jupiter-Rahu antardasha: ambition in spiritual or foreign matters; confusion in dharma; unexpected opportunities.",
        "Ketu": "Jupiter-Ketu antardasha: spiritual wisdom; past-life connections; detachment from material expansion.",
        "Sun": "Jupiter-Sun antardasha: governmental success, father's well-being, authority and recognition.",
        "Moon": "Jupiter-Moon antardasha: emotional well-being, property and mother matters; good for business.",
    },
    "Saturn": {
        "Mercury": "Saturn-Mercury antardasha: hard work in communication or business; steady intellectual progress.",
        "Venus": "Saturn-Venus antardasha: delayed but stable relationship results; artistic discipline; material gains through effort.",
        "Sun": "Saturn-Sun antardasha: tension between authority and restriction; career challenges; government conflicts.",
        "Moon": "Saturn-Moon antardasha: emotional restriction, mental pressure; health of mother; property matters delayed.",
        "Mars": "Saturn-Mars antardasha: accident or surgery risk; property disputes; discipline in competitive matters.",
        "Rahu": "Saturn-Rahu antardasha: one of the most challenging periods — confusion, delays, sudden disruptions.",
        "Jupiter": "Saturn-Jupiter antardasha: dharma through discipline; spiritual progress; financial consolidation.",
        "Ketu": "Saturn-Ketu antardasha: spiritual detachment; karmic completion; unexpected health issues.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Domain-specific rules from BPHS
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_RULES: dict[str, list[str]] = {
    "marriage": [
        "The 7th house, its lord, and Venus (natural karaka) together determine marriage — all three must be assessed.",
        "Jupiter aspects on the 7th house or its lord bless marriage with wisdom and prosperity.",
        "Affliction of 7th lord by Mars (Manglik), Saturn, or Rahu/Ketu delays or troubles marriage.",
        "Venus in own sign, exaltation, or kendra from Lagna gives an attractive and devoted spouse.",
        "Moon in 7th or aspecting 7th: emotional, changeable marriage; spouse is sensitive and nurturing.",
        "Saturn aspecting or in 7th: delays marriage after 30, or spouse is older, serious, and hardworking.",
        "Rahu in 7th or with 7th lord: unconventional or foreign spouse; multiple relationships possible.",
        "For timing: marriage is most likely during the Mahadasha or Antardasha of 7th lord, Venus, or the planet in 7th.",
        "Navamsha (D9) must confirm the Rashi chart — a strong D9 7th house with benefic influences confirms happy marriage.",
        "2nd house (family) and 11th house (fulfillment) must also support marriage for it to be stable and prosperous.",
    ],
    "career": [
        "The 10th house, its lord, and the planets in 10th determine the nature of career and profession.",
        "Sun in 10th or aspecting 10th: government, authority, leadership roles; the native rises to prominence.",
        "Saturn in 10th (exalted in Libra): powerful slow rise; success in discipline, service, or large organisations.",
        "Jupiter in 10th: career in education, law, religion, or administration; respected and ethical profession.",
        "Mars in 10th: engineering, military, surgery, sports, law enforcement; ambitious and competitive career.",
        "Mercury in 10th: career in business, communication, accounting, teaching, writing.",
        "The 9th lord conjoining 10th lord (Dharma-Karma Yoga) gives a noble and successful career path.",
        "Planets in 2nd and 11th supporting the 10th lord ensure financial success through career.",
        "For timing: career breakthroughs come in the Mahadasha or Antardasha of 10th lord or planets in 10th.",
        "Dashamsha (D10) chart confirms career — assess lagna and 10th of D10 for professional specifics.",
    ],
    "wealth": [
        "The 2nd house (accumulated wealth), 11th house (income/gains), and their lords determine financial status.",
        "Jupiter as natural karaka of wealth must be strong — exalted, in own sign, or in a kendra for prosperity.",
        "Venus in 2nd or 11th gives wealth through beauty, arts, or partnerships.",
        "Mercury in 2nd or 11th: wealth through business, trade, intellect, and communication.",
        "Dhana Yoga forms when lords of 2nd and 11th associate — strength of this yoga determines the extent of wealth.",
        "Lagna lord in 2nd or 11th gives financial focus and earning ability.",
        "Saturn in 11th after sustained effort gives stable and lasting wealth in middle age.",
        "Rahu in 11th can give sudden, large, but unstable gains.",
        "Affliction of 2nd lord by 6th, 8th, or 12th lords causes financial losses or debt.",
        "For timing: major financial gains come during Mahadasha/Antardasha of 2nd lord, 11th lord, or Jupiter.",
    ],
    "health": [
        "The 1st house (body), 6th house (disease), and 8th house (chronic illness/longevity) determine health.",
        "Lagna lord's strength is the most critical factor — a strong Lagna lord protects health and vitality.",
        "Sun strong in chart gives good vitality, immunity, and recovery power.",
        "Moon afflicted (by Rahu, Saturn, or in 6th/8th/12th) causes mental health issues, anxiety, or depression.",
        "Mars in 1st or 8th (Manglik) increases accident and surgery risk — Kuja Dosha must be assessed.",
        "Saturn's aspect on Lagna or Moon causes chronic, slow-building conditions; delays recovery.",
        "Rahu in Lagna or 6th can cause mysterious or difficult-to-diagnose illnesses.",
        "6th house lord in Lagna causes the native to be prone to disease; health requires constant attention.",
        "8th lord in Lagna or Lagna lord in 8th creates an exchange that impacts longevity — assess with care.",
        "For timing: health challenges arise in Mahadasha of 6th lord, 8th lord, or planets placed in 6th or 8th.",
    ],
    "children": [
        "The 5th house, its lord, and Jupiter (natural karaka) together determine children.",
        "Jupiter in 5th or aspecting 5th gives intelligent, blessed children; multiple children possible.",
        "Saturn in 5th: delays in children, few children, or serious and hard-working children.",
        "Mars in 5th: possible abortion or miscarriage; energetic, athletic children.",
        "Rahu or Ketu in 5th: unconventional children; possible adoption; past-life karma with children.",
        "5th lord in 2nd: children contribute to family wealth; intelligent children.",
        "5th lord in 11th: gains through children; children fulfill the native's ambitions.",
        "For timing: conception and birth most likely during Mahadasha/Antardasha of 5th lord or Jupiter.",
    ],
    "spirituality": [
        "The 9th house (dharma), 12th house (moksha), and Jupiter determine spiritual life.",
        "Ketu in 12th or 9th gives strong spiritual inclinations and past-life spiritual merit.",
        "Jupiter in 9th (own house for Sagittarius): highest spiritual blessing; guru's grace; righteous life.",
        "Saturn in 12th: deep spiritual discipline; renunciation; monastic tendencies.",
        "Atmakaraka (planet with highest degree) in Navamsha D9 shows the soul's primary dharmic lesson.",
        "Moon and Jupiter both strong: the native is naturally devotional, wise, and spiritually protected.",
        "12th lord strong and beneficially placed: smooth transition to liberation; foreign spiritual journeys.",
        "For timing: spiritual breakthroughs come in Mahadasha of 9th lord, 12th lord, Jupiter, or Ketu.",
    ],
    "general": [
        "Assess the Lagna, Lagna lord, and Moon sign first — these three form the foundation of any reading.",
        "Benefics (Jupiter, Venus, waxing Moon, Mercury without malefic influence) in kendras (1,4,7,10) give protection and prosperity.",
        "Malefics (Saturn, Mars, Rahu, Ketu, Sun, waning Moon) in upachaya houses (3,6,10,11) give strength and achievement.",
        "Malefics in kendras or trikonas harm the significations of those houses unless they rule those houses.",
        "The planet ruling the current Mahadasha sets the primary theme of that life period.",
        "Always examine the Navamsha (D9) chart to confirm Rashi chart indications — D9 shows the soul's deeper nature.",
        "Vargottama planets (same sign in D1 and D9) are extremely powerful and give reliable results.",
        "The 64th Navamsha and 22nd Drekkana indicate potential health and danger periods.",
        "Mutual aspect between benefics gives a protective shield over the houses they aspect.",
        "A planet's results are modified by the planets that conjoin it, aspect it, and the lord of its sign.",
    ],
    "travel": [
        "The 3rd house governs short travel and journeys; 9th house governs long-distance and pilgrimage travel.",
        "12th house indicates foreign settlement and residence abroad — Rahu/Ketu axis on 1-7 or 12 increases this.",
        "Moon in 3rd or aspecting 3rd: frequent short travel; restless mind; journey-seeking nature.",
        "Rahu in 9th or 12th strongly indicates foreign travel or settlement.",
        "Saturn in 9th or 12th: delays in foreign travel but eventual long-term foreign settlement.",
        "3rd lord and 9th lord both strong: life involves significant travel, both domestic and international.",
        "For timing: foreign travel most likely in Mahadasha/Antardasha of 3rd lord, 9th lord, 12th lord, or Rahu.",
    ],
    "social_standing": [
        "The 1st house (reputation), 10th house (status), and Sun (authority) determine social standing.",
        "Sun strong in chart: natural authority, leadership recognition, public respect.",
        "Jupiter in kendra: wisdom confers natural social respect regardless of material status.",
        "Saturn well-placed: respect earned through hard work and discipline over time; late-life honour.",
        "Afflicted Sun (by Saturn or Rahu): ego conflicts, reputation challenges, authority issues.",
        "10th lord strong in own sign or exaltation: exceptional rise in social status and public recognition.",
        "For timing: recognition and social rise come during Mahadasha of 10th lord, Sun, or Jupiter.",
    ],
    "relationships": [
        "Venus, Moon, and the 7th house together determine all close relationships.",
        "Strong Venus in kendra or trikona: charismatic, attractive; naturally harmonious in relationships.",
        "Moon-Venus conjunction or mutual aspect: emotionally sensitive and artistic in relationships; loving.",
        "Mars-Venus conjunction: passionate relationships; can bring both intense attraction and conflict.",
        "Saturn aspecting Venus or 7th: serious, loyal but restrictive relationships; maturity in love.",
        "For timing: significant relationships begin in Mahadasha/Antardasha of 7th lord, Venus, or Moon.",
    ],
    "family": [
        "The 2nd house governs family of birth (Kutumba) and accumulated wealth; 4th governs mother and home.",
        "4th lord strong and well-placed: happy home life, devoted mother, property and vehicles.",
        "2nd lord in 11th or 11th lord in 2nd: the family accumulates wealth; gains through family.",
        "Jupiter in 2nd: large, prosperous, learned family; wealth through ancestral blessings.",
        "Saturn in 4th: difficulties with mother or home; property comes late; disciplined household.",
        "For timing: family events (marriage in family, property purchase, mother's events) occur in dashas of 2nd and 4th lords.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Aspect rules — BPHS Graha Drishti
# ─────────────────────────────────────────────────────────────────────────────

ASPECT_RULES: list[str] = [
    "All planets aspect the 7th house from their position (full aspect).",
    "Jupiter aspects the 5th and 9th from its position in addition to the 7th (full aspect on all three).",
    "Saturn aspects the 3rd and 10th from its position in addition to the 7th.",
    "Mars aspects the 4th and 8th from its position in addition to the 7th.",
    "Rahu and Ketu aspect the 5th, 7th, and 9th from their positions.",
    "A planet's aspect on a house activates that house's significations — benefic aspects bless, malefic aspects strain.",
    "Jupiter's aspect is the most protective — it can mitigate malefic influences on the houses it aspects.",
    "Saturn's 10th aspect on the 10th house from itself often harms profession unless Saturn is strong and well-placed.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Transit (Gochara) rules — BPHS Gochara Phala
# ─────────────────────────────────────────────────────────────────────────────

TRANSIT_RULES: list[str] = [
    "Transit results are judged primarily from the natal Moon sign (Janma Rashi) in Parashari tradition.",
    "Saturn transiting the 12th, 1st, and 2nd from natal Moon is Sade Sati (7.5 years) — a period of challenges, transformation, and karmic reckoning.",
    "Jupiter transiting the 5th, 7th, or 9th from natal Moon (Guru transit) is highly auspicious — called Gurubala.",
    "Jupiter transiting the 4th, 8th, or 12th from natal Moon is unfavorable — Guru is weak.",
    "Saturn transiting the 3rd, 6th, or 11th from natal Moon gives strength, victory over enemies, and gains.",
    "Saturn transiting the 1st, 2nd, 4th, 5th, 7th, 8th, 10th, or 12th from Moon is generally challenging for those areas.",
    "Mars transiting the 8th from natal Moon is Ashtama Mangala — risk of accidents or health issues for that period.",
    "Rahu transiting the 1st, 5th, or 9th from Moon is challenging for health, children, and fortune.",
    "All transit results must be confirmed against the running Vimshottari Dasha — dasha is more important than transit alone.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Planet in Sign results — BPHS Graha-Rashi Phala (all 9 planets × 12 signs)
# ─────────────────────────────────────────────────────────────────────────────

PLANET_IN_SIGN: dict[str, dict[str, str]] = {
    "Sun": {
        "Aries":       "Sun in Aries (exaltation, 10° highest): supreme vitality, pioneering spirit, natural leadership, bold and self-reliant; father figure is strong and authoritative.",
        "Taurus":      "Sun in Taurus: steady but stubborn; wealth focus; artistic side emerges; values security; father may be wealthy, landed, or connected to agriculture.",
        "Gemini":      "Sun in Gemini: intellectual, communicative, versatile; career in administration, writing, or government; split identity possible; clever father.",
        "Cancer":      "Sun in Cancer: sensitive ego, domestic focus; fluctuating vitality depending on Moon's strength; relationship with father may be emotional or complicated.",
        "Leo":         "Sun in Leo (own sign): powerful, regal, confident, generous; leadership and authority come naturally; father is prominent or noble.",
        "Virgo":       "Sun in Virgo: analytical, service-oriented, detail-focused; career in medicine, accounting, or analysis; father is methodical and critical.",
        "Libra":       "Sun in Libra (debilitation): weakened ego, indecisive, dependent on others for validation; partnership-oriented; father may be weak or absent; requires balancing.",
        "Scorpio":     "Sun in Scorpio: intense, secretive, transformative; powerful will beneath reserved exterior; research, occult, or investigative work; father is intense.",
        "Sagittarius": "Sun in Sagittarius: philosophical, dharmic, broad-minded; career in law, religion, or higher education; generous father figure; love of truth.",
        "Capricorn":   "Sun in Capricorn: ambitious, disciplined, career-driven; slow rise to power; father is hardworking and authoritative; achievements come through sustained effort.",
        "Aquarius":    "Sun in Aquarius: humanitarian, unconventional, community-oriented; career in social reform, technology, or large organisations; detached ego.",
        "Pisces":      "Sun in Pisces: spiritual, imaginative, compassionate; career in healing, spirituality, or arts; father may be spiritual or absent; identity dissolves into service.",
    },
    "Moon": {
        "Aries":       "Moon in Aries: impulsive emotions, quick reactions, pioneering instincts; restless mind; mother is courageous and independent; fond of action.",
        "Taurus":      "Moon in Taurus (exaltation, 3° highest): emotionally stable, sensual, comfort-loving; strong memory; devoted mother; wealth and beauty are central.",
        "Gemini":      "Moon in Gemini: intellectually restless, communicative emotions; dual feelings; witty and adaptable; mother is educated and communicative.",
        "Cancer":      "Moon in Cancer (own sign): deeply emotional, intuitive, nurturing; strong bond with mother; comfort in home and family; fluctuating but sensitive mind.",
        "Leo":         "Moon in Leo: proud, dramatic, warm-hearted; emotional need for recognition; mother is regal or influential; generous and creative mind.",
        "Virgo":       "Moon in Virgo: analytical emotions, critical mind; health-conscious; mother is practical and service-oriented; worried or overthinking tendencies.",
        "Libra":       "Moon in Libra: emotionally diplomatic, relationship-focused; need for harmony; mother is beautiful or artistic; balanced and fair-minded.",
        "Scorpio":     "Moon in Scorpio (debilitation): intense, secretive emotions; jealousy or obsession possible; mother relationship is complex; deep psychological insight.",
        "Sagittarius": "Moon in Sagittarius: optimistic, philosophical emotions; love of travel and freedom; mother is spiritual or broad-minded; generous instincts.",
        "Capricorn":   "Moon in Capricorn: emotionally reserved, disciplined; slow to trust; mother may be strict or absent emotionally; ambition drives the mind.",
        "Aquarius":    "Moon in Aquarius: detached, humanitarian emotions; unconventional feelings; mother is independent or unusual; community-minded instincts.",
        "Pisces":      "Moon in Pisces: deeply empathetic, imaginative, spiritual; prone to emotional confusion; mother is compassionate; psychic or artistic sensitivities.",
    },
    "Mars": {
        "Aries":       "Mars in Aries (own sign, Moolatrikona 0–12°): courageous, pioneering, energetic; excellent for leadership, sports, and independent ventures; Manglik active.",
        "Taurus":      "Mars in Taurus: stubborn energy directed toward wealth and possessions; persistence in financial matters; Manglik in 2nd house effects apply.",
        "Gemini":      "Mars in Gemini: energetic communication and writing; debates and arguments; sharp intellect applied to competition; scattered energy.",
        "Cancer":      "Mars in Cancer (debilitation): energy frustrated; emotional aggression; conflict in home life; Manglik in 4th; mother relationship tense.",
        "Leo":         "Mars in Leo: bold, dramatic, authoritative action; leadership and competition; sports, politics, or performance; courageous heart.",
        "Virgo":       "Mars in Virgo: precise, analytical action; excellence in surgery, engineering detail, or technical work; critical and exacting approach.",
        "Scorpio":     "Mars in Scorpio (own sign): intense, investigative, secretive drive; research, occult, military, or surgery; deep reserves of stamina.",
        "Sagittarius": "Mars in Sagittarius: energetic pursuit of dharma; sports, philosophy, or law combined with courage; opinionated and direct.",
        "Capricorn":   "Mars in Capricorn (exaltation, 28° highest): disciplined, organised, relentless; outstanding for career, military, and engineering; sustained achievement.",
        "Aquarius":    "Mars in Aquarius: energy directed toward social causes or technology; combative in group settings; unconventional warrior.",
        "Libra":       "Mars in Libra: energy in partnerships and negotiations; conflict in relationships; legal battles; Manglik in 7th house strongly active.",
        "Pisces":      "Mars in Pisces: spiritual warrior; energy dissipates in compassion or confusion; hidden strength; work in hospitals, missions, or retreats.",
    },
    "Mercury": {
        "Aries":       "Mercury in Aries: quick, assertive thinking; impulsive decisions; good for debate and rapid communication; starts many intellectual projects.",
        "Taurus":      "Mercury in Taurus: practical, methodical intellect; excellent for finance, agriculture, or design; slow but thorough thought process.",
        "Gemini":      "Mercury in Gemini (own sign, Moolatrikona): exceptionally quick intellect, eloquent, versatile; writing, teaching, and business flourish.",
        "Cancer":      "Mercury in Cancer: intuitive, emotionally-coloured intellect; good memory; writing on domestic or emotional topics; influenced by mood.",
        "Leo":         "Mercury in Leo: creative, dramatic intellect; authoritative speaker; good for performing arts administration, politics, or creative writing.",
        "Virgo":       "Mercury in Virgo (own sign and exaltation, 15° highest): most powerful placement — supreme analytical ability, precision, healing arts, accounting.",
        "Libra":       "Mercury in Libra: diplomatic, balanced intellect; legal reasoning; good for negotiation, arbitration, and partnership communication.",
        "Scorpio":     "Mercury in Scorpio: penetrating, investigative mind; research, psychology, occult writing; secretive communicator.",
        "Sagittarius": "Mercury in Sagittarius: philosophical intellect, broad-minded; good for religious writing, law, or teaching; can be dogmatic.",
        "Capricorn":   "Mercury in Capricorn: structured, disciplined intellect; organisational and administrative skills; methodical writer and planner.",
        "Aquarius":    "Mercury in Aquarius: innovative, scientific intellect; technology, astrology, or humanitarian causes; unconventional thinking.",
        "Pisces":      "Mercury in Pisces (debilitation): imagination over logic; poetic or spiritual mind; poor in analytical tasks; good for mystical or artistic writing.",
    },
    "Jupiter": {
        "Aries":       "Jupiter in Aries: enthusiastic, pioneering wisdom; teaching with energy; leadership in religion or law; wisdom through direct experience.",
        "Taurus":      "Jupiter in Taurus: wealth, comfort, and dharma align; generous and pleasure-loving; teaching on material and spiritual abundance.",
        "Gemini":      "Jupiter in Gemini: intellectual expansion; excellent teacher and writer; multiple philosophies; wisdom spread through communication.",
        "Cancer":      "Jupiter in Cancer (exaltation, 5° highest): supreme benevolence, emotional wisdom, abundant wealth, devotion; blessed mother relationship.",
        "Leo":         "Jupiter in Leo: noble, generous, regal wisdom; excellent for leadership in education, law, or religion; proud but just.",
        "Virgo":       "Jupiter in Virgo: wisdom in service; teaching through healing, medicine, or analysis; can be overly critical in philosophy.",
        "Libra":       "Jupiter in Libra: wisdom in relationships and justice; excellent for law, diplomacy, or counselling; generous in partnerships.",
        "Scorpio":     "Jupiter in Scorpio: depth wisdom, occult knowledge; teaching on transformation and hidden matters; expansion through crisis.",
        "Sagittarius": "Jupiter in Sagittarius (own sign, Moolatrikona): extremely fortunate, philosophical, generous; natural guru, teacher, or judge; dharma flows.",
        "Capricorn":   "Jupiter in Capricorn (debilitation): wisdom is restricted or materialised; charitable impulse blocked; spiritual knowledge delayed; practical teacher.",
        "Aquarius":    "Jupiter in Aquarius: humanitarian wisdom; teaching in social reform, technology, or community development; expansive in groups.",
        "Pisces":      "Jupiter in Pisces (own sign): deep spiritual wisdom; moksha-oriented; compassionate; excellent for spiritual teaching and healing arts.",
    },
    "Venus": {
        "Aries":       "Venus in Aries: passionate, impulsive love; quick attractions; artistic energy in action; competitive in relationships.",
        "Taurus":      "Venus in Taurus (own sign): luxurious, sensual, stable love; artistic talent, wealth, and beauty; devoted and comfort-seeking.",
        "Gemini":      "Venus in Gemini: charming, intellectual love; multiple relationships possible; arts through communication; beautiful voice.",
        "Cancer":      "Venus in Cancer: nurturing, emotional love; devotion to home; artistic sensitivity; beauty through compassion.",
        "Leo":         "Venus in Leo: dramatic, generous love; grand romantic gestures; artistic performance; pride in relationships.",
        "Virgo":       "Venus in Virgo (debilitation): love is critical or conditional; service-oriented relationships; artistic precision; difficulties with pleasure.",
        "Libra":       "Venus in Libra (own sign, Moolatrikona): harmonious, beautiful, diplomatic love; natural charm; wealth through partnership; artistic excellence.",
        "Scorpio":     "Venus in Scorpio: intense, transformative love; passionate and jealous; wealth through inheritance; hidden beauty.",
        "Sagittarius": "Venus in Sagittarius: philosophical love; attraction to foreign or spiritual partners; arts with dharmic themes.",
        "Capricorn":   "Venus in Capricorn: disciplined, dutiful love; mature relationships; wealth through sustained effort; classical arts.",
        "Aquarius":    "Venus in Aquarius: unconventional love; humanitarian relationships; beauty in community; arts for social causes.",
        "Pisces":      "Venus in Pisces (exaltation, 27° highest): the most beautiful, spiritual, and compassionate love; artistic genius; wealth and harmony flow naturally.",
    },
    "Saturn": {
        "Aries":       "Saturn in Aries (debilitation): energy is frustrated by restriction; impulsive action meets delay; challenges to authority and independence; lessons in patience.",
        "Taurus":      "Saturn in Taurus: slow but steady wealth accumulation; material discipline; persistent effort in finance; property gains after delays.",
        "Gemini":      "Saturn in Gemini: structured communication; serious writer or teacher; disciplined intellect; sibling relationships may be strained.",
        "Cancer":      "Saturn in Cancer: emotional restriction; difficult relationship with mother; property delays; domestic responsibilities are heavy.",
        "Leo":         "Saturn in Leo: ego is disciplined; authority earned through hard work; father-figure challenges; leadership through perseverance.",
        "Virgo":       "Saturn in Virgo: excellent for service, medicine, or analysis; disciplined health practices; methodical and detail-oriented.",
        "Libra":       "Saturn in Libra (exaltation, 20° highest): justice, discipline, and fairness combine; excellent for law, diplomacy, and sustained career success.",
        "Scorpio":     "Saturn in Scorpio: deep karmic transformation; discipline in occult or research; chronic health issues possible; endurance in crisis.",
        "Sagittarius": "Saturn in Sagittarius: disciplined dharma; serious philosophical study; slow fortune; father is strict or distant; long journeys for work.",
        "Capricorn":   "Saturn in Capricorn (own sign): structured ambition, authority through discipline; excellent career in management, government, or engineering.",
        "Aquarius":    "Saturn in Aquarius (own sign, Moolatrikona): humanitarian discipline; community service; technology-oriented; wisdom through detachment.",
        "Pisces":      "Saturn in Pisces: spiritual discipline; service in isolation; withdrawal from the world; work in hospitals, ashrams, or foreign lands.",
    },
    "Rahu": {
        "Aries":       "Rahu in Aries: intense ambition for self-assertion; obsession with identity and courage; pioneering but reckless; foreign ventures.",
        "Taurus":      "Rahu in Taurus (exaltation per some texts): powerful material desires; obsession with wealth, beauty, and comfort; gains through unconventional means.",
        "Gemini":      "Rahu in Gemini (exaltation per BPHS): excellent for communication, technology, and media; foreign languages; gains through information.",
        "Cancer":      "Rahu in Cancer: obsession with home, mother, or emotional security; foreigners in family; unusual domestic life.",
        "Leo":         "Rahu in Leo: craving recognition and authority; rise through unconventional means; fame or notoriety; political ambition.",
        "Virgo":       "Rahu in Virgo: obsession with health, analysis, or service; foreign medical or technical work; gains through details and systems.",
        "Libra":       "Rahu in Libra: obsessive partnerships; foreign or unconventional spouse; gains through negotiations and alliances.",
        "Scorpio":     "Rahu in Scorpio: intense occult desires; obsession with transformation; sudden gains and losses; interest in foreign mysteries.",
        "Sagittarius": "Rahu in Sagittarius (debilitation per some texts): challenges to dharma; unconventional religion; foreign guru; confused philosophy.",
        "Capricorn":   "Rahu in Capricorn: relentless career ambition through unusual means; rise through foreign connections; disciplined but manipulative.",
        "Aquarius":    "Rahu in Aquarius: obsession with social causes or technology; gains through groups and networks; unconventional humanitarianism.",
        "Pisces":      "Rahu in Pisces: spiritual confusion; obsession with liberation or foreign spiritual practices; gains through imagination or deception.",
    },
    "Ketu": {
        "Aries":       "Ketu in Aries: past-life warrior; detachment from self-assertion; sudden impulsive events; spiritual courage from previous lives.",
        "Taurus":      "Ketu in Taurus: past-life wealth karma; detachment from material possessions; spiritual values over comfort; unusual relationship with money.",
        "Gemini":      "Ketu in Gemini (debilitation per some texts): past-life communication skills; detachment from siblings; spiritual or cryptic speech.",
        "Cancer":      "Ketu in Cancer: past-life home and mother karma; detachment from emotional security; spiritual connection to ancestral roots.",
        "Leo":         "Ketu in Leo: past-life leadership karma; detachment from recognition; spiritual authority; hidden power behind the scenes.",
        "Virgo":       "Ketu in Virgo: past-life service or healing karma; detachment from health analysis; spiritual healing abilities.",
        "Libra":       "Ketu in Libra: past-life relationship karma; detachment from partnerships; spiritual seeking in relationships.",
        "Scorpio":     "Ketu in Scorpio: past-life occult mastery (own house for Ketu in some systems); deep spiritual transformation; moksha-oriented.",
        "Sagittarius": "Ketu in Sagittarius (exaltation per BPHS): highest spiritual wisdom from past lives; detachment from formal religion; true inner guru.",
        "Capricorn":   "Ketu in Capricorn: past-life career mastery; detachment from ambition; spiritual service in structured environments.",
        "Aquarius":    "Ketu in Aquarius: past-life humanitarian karma; detachment from groups and social causes; inner freedom from collective identity.",
        "Pisces":      "Ketu in Pisces: past-life spiritual liberation; deep moksha indicators; detachment from imagination; transcendence of illusion.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Lagna (Ascendant) results — BPHS Lagna Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

LAGNA_RESULTS: dict[str, str] = {
    "Aries": (
        "Aries Lagna (Mesha): ruled by Mars. The native has a muscular, medium-to-tall build with a reddish or ruddy complexion and a prominent forehead. "
        "Personality is bold, independent, pioneering, and self-reliant — natural leader with a competitive spirit. Prone to anger and impatience. "
        "Health is generally robust but prone to head injuries, fevers, and inflammatory conditions. Yogas: Mars strong in own sign or exaltation creates Ruchaka Mahapurusha Yoga; "
        "Sun as 5th lord in kendra with Mars creates powerful Raj Yoga. Benefics in kendras protect the native's direct and courageous nature."
    ),
    "Taurus": (
        "Taurus Lagna (Vrishabha): ruled by Venus. The native has a stocky, well-built body with a pleasant face and large eyes. "
        "Personality is patient, sensual, artistic, and comfort-loving; extremely loyal but stubborn. "
        "Health is stable but susceptible to throat, neck, and thyroid issues. Venus governs both the Lagna and 6th lord (as lord of Libra), creating a complex relationship with enemies and service. "
        "Yogas: Venus in own sign in kendra creates Malavya Yoga; Saturn as 9th and 10th lord creates a powerful Dharma-Karma Adhipati Yoga when strong."
    ),
    "Gemini": (
        "Gemini Lagna (Mithuna): ruled by Mercury. The native is tall, slim, with quick eyes and an expressive face. "
        "Personality is intellectual, curious, communicative, versatile, and often scattered. Wit and adaptability are the defining traits. "
        "Health: prone to nervous system issues, respiratory problems, and anxiety. "
        "Yogas: Mercury strong in Gemini or Virgo creates Bhadra Yoga; Venus as 5th and 12th lord in kendra creates a Raj Yoga with spiritual undertones; "
        "Saturn as 8th and 9th lord is a Yogakaraka when strong."
    ),
    "Cancer": (
        "Cancer Lagna (Karka): ruled by Moon. The native has a round face, pale or fair complexion, and a medium build that tends toward weight gain. "
        "Personality is deeply empathetic, intuitive, protective, and home-oriented; moods fluctuate with circumstances. "
        "Health: chest, digestion, and mental health are sensitive. "
        "Yogas: Mars as 5th and 10th lord is a supreme Yogakaraka — Mars in a kendra or trikona creates powerful Raj Yoga; Jupiter as 9th lord blesses with fortune. "
        "The strongest chart comes when Moon (Lagna lord) is waxing, in a kendra, and aspected by Jupiter."
    ),
    "Leo": (
        "Leo Lagna (Simha): ruled by Sun. The native has a broad, commanding presence with a large head, wide shoulders, and a regal bearing. "
        "Personality is proud, generous, ambitious, and naturally authoritative; the center of attention wherever they go. "
        "Health: heart and spine are sensitive; vitality is generally strong. "
        "Yogas: Mars as 4th and 9th lord is a Yogakaraka; Jupiter as 5th lord blesses intellect and children. "
        "Sun strong in Leo creates natural authority; Budha-Aditya Yoga (Sun-Mercury) is effective when Mercury is in Leo or nearby."
    ),
    "Virgo": (
        "Virgo Lagna (Kanya): ruled by Mercury. The native is typically slim, tall, and health-conscious with sharp, observant eyes. "
        "Personality is analytical, precise, service-oriented, and discriminating; an excellent planner and technician. "
        "Health: digestive system and intestines are sensitive; prone to anxiety and overthinking. "
        "Yogas: Venus as 2nd and 9th lord is a Yogakaraka — Venus strong creates wealth and fortune; Mercury's strength supports Bhadra Yoga. "
        "Saturn as 5th and 6th lord gives discipline; benefics in trikona support a giving, dharmic life."
    ),
    "Libra": (
        "Libra Lagna (Tula): ruled by Venus. The native has a symmetrical, attractive appearance with a refined demeanor and natural charm. "
        "Personality is diplomatic, relationship-focused, fair-minded, and artistic; may struggle with decision-making. "
        "Health: kidneys and lower back are sensitive; generally good health when balanced. "
        "Yogas: Saturn as 4th and 5th lord is a supreme Yogakaraka — Saturn exalted in Libra itself is exceptional; Venus in own sign creates Malavya Yoga. "
        "Mercury as 9th lord with Venus creates excellent Raj Yoga for career in law, arts, or diplomacy."
    ),
    "Scorpio": (
        "Scorpio Lagna (Vrishchika): ruled by Mars (and Ketu as co-ruler). The native has a penetrating gaze, medium build, and intense energy. "
        "Personality is secretive, transformative, research-oriented, and emotionally intense; resilient through crises. "
        "Health: reproductive system, elimination organs, and chronic hidden conditions are sensitive. "
        "Yogas: Moon as 9th lord in a kendra creates Raj Yoga; Jupiter as 2nd and 5th lord blesses wealth and children. "
        "Mars strong as Lagna lord gives protective energy; Ketu in Lagna bestows deep spiritual insight from past lives."
    ),
    "Sagittarius": (
        "Sagittarius Lagna (Dhanu): ruled by Jupiter. The native is tall, athletic, with an open, cheerful face and an optimistic bearing. "
        "Personality is philosophical, freedom-loving, dharmic, and generous; a natural teacher, guide, or traveler. "
        "Health: hips, thighs, and liver are sensitive; generally robust. "
        "Yogas: Mars as 5th and 12th lord creates a spiritual Raj Yoga; Sun as 9th lord in a trikona or kendra creates exceptional fortune. "
        "Jupiter's strength as Lagna lord is paramount — Jupiter exalted or in own sign confers Hamsa Yoga."
    ),
    "Capricorn": (
        "Capricorn Lagna (Makara): ruled by Saturn. The native has a lean, angular build with a serious, disciplined bearing; ages well. "
        "Personality is ambitious, practical, responsible, and methodical; success comes through sustained effort and patience. "
        "Health: knees, joints, skin, and teeth are sensitive. "
        "Yogas: Venus as 5th and 10th lord is a supreme Yogakaraka — Venus in kendra or trikona gives excellent career and children; "
        "Mercury as 6th and 9th lord is mixed. Saturn's exaltation in Libra 10th from own Lagna completes a powerful career combination."
    ),
    "Aquarius": (
        "Aquarius Lagna (Kumbha): ruled by Saturn (and Rahu as co-ruler). The native has a tall, lean, intellectual appearance with a detached, humanitarian manner. "
        "Personality is innovative, socially conscious, independent, and reform-minded; can be eccentric or aloof. "
        "Health: ankles, circulation, and nervous system are sensitive. "
        "Yogas: Venus as 4th and 9th lord is a Yogakaraka — Venus strong gives property and fortune; "
        "Mars as 3rd and 10th lord can give a powerful career through effort. "
        "Saturn as Lagna lord must be strong; Rahu's strength amplifies the native's unconventional path."
    ),
    "Pisces": (
        "Pisces Lagna (Meena): ruled by Jupiter. The native has a soft, compassionate appearance with large, dreamy eyes and a gentle bearing. "
        "Personality is empathetic, spiritual, imaginative, and selfless; deeply intuitive but can lack boundaries. "
        "Health: lymphatic system, feet, and immune system are sensitive; prone to addictions or escapism. "
        "Yogas: Mars as 2nd and 9th lord is a Yogakaraka — Mars strong gives wealth and fortune; "
        "Moon as 5th lord in a kendra creates Raj Yoga. Jupiter as Lagna lord must be strong for best results; "
        "exalted Venus in Pisces creates Malavya Yoga with spiritual dimensions."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Ashtakavarga rules — BPHS Ashtakavarga Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

ASHTAKAVARGA_RULES: list[str] = [
    "Ashtakavarga (SAV) measures the aggregate strength of all seven planets (Sun through Saturn) plus Lagna in each of the 12 signs; each sign receives bindus (benefic dots) from 0–8 contributors, giving a total of 0–56 bindus per sign.",
    "In any sign, 4 or more bindus is considered average or above-average strength; signs with 5+ bindus give good results during transits through that sign, while signs with 3 or fewer bindus indicate weak periods.",
    "When a sign in the SAV has 28 or more bindus, that sign is exceptionally strong — transits through it or events governed by that house yield very favorable results.",
    "When a sign has fewer than 28 bindus in the SAV, the transit of a planet through it tends to be unfavorable or weak — natives experience obstacles related to that house's significations.",
    "A Bhinna Ashtakavarga (BAV) score of 4 or more bindus for an individual planet in a sign indicates that planet transiting that sign gives good results; 3 or fewer is unfavorable.",
    "The BAV of Saturn in its own Ashtakavarga is especially important for timing challenges: Saturn in a sign with fewer than 3 of its own bindus causes maximum difficulty during that transit.",
    "Jupiter's BAV is critical for timing auspicious events — Jupiter transiting signs where it has 5+ of its own bindus in its Ashtakavarga brings the most benefit.",
    "The total SAV score for all 12 signs should ideally sum to 337 bindus; a total above 337 indicates a generally fortunate and active life; below 337 suggests a quieter, more restricted life overall.",
    "The house with the highest SAV score is the strongest area of life — the native thrives most in that house's domain throughout life.",
    "The house with the lowest SAV score is the weakest domain — persistent challenges arise in that house's significations regardless of transits.",
    "When both the Dasha lord and transiting planet are in signs with high BAV bindus, the period is doubly auspicious — Dasha, transit, and Ashtakavarga strength must all align for major events.",
    "Sodhya Pinda (reduction of bindus) is applied to refine Ashtakavarga for timing of events: the Trikona Shodhana removes bindus from signs in trine, and the Ekadhipatya Shodhana adjusts for shared rulership.",
    "The Prastara Ashtakavarga shows each planet's individual bindu contribution to every sign — studying this reveals which planets are contributing positively or negatively in each chart area.",
    "Transits of slow planets (Saturn, Jupiter, Rahu/Ketu) through signs with high SAV are the most significant timing indicators — combine with Dasha for precise event prediction.",
    "In timing longevity and difficult periods, count the bindus in the 8th house SAV: fewer than 25 bindus in the 8th can indicate vulnerability; more than 30 gives resilience.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Navamsha (D9) rules — BPHS Navamsha Phala Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

NAVAMSHA_RULES: list[str] = [
    "The Navamsha (D9) chart is the most important divisional chart in BPHS; it shows the soul's inner nature, the quality of marriage, and the deeper fruition of the Rashi (D1) promises.",
    "A planet in the same sign in both the D1 Rashi chart and the D9 Navamsha chart is called Vargottama — this greatly amplifies the planet's strength and reliability of its results.",
    "The D9 Lagna and its lord reveal the native's soul-level purpose and inner character; a strong D9 Lagna lord confers spiritual resilience even when the D1 Lagna is afflicted.",
    "Planets that are weak in D1 (debilitated, combust, or in enemy signs) but strong in D9 (exalted or in own sign) give results better than their D1 placement suggests — the promise is fulfilled at the soul level.",
    "Planets strong in D1 but weak in D9 give good appearances of results without full fruition — the external opportunity may arise but the inner experience or lasting benefit is diminished.",
    "Pushkara Navamsha: the Navamsha portions of specific degrees (such as Taurus 23–26°40', Cancer 10–13°20', and others) are called Pushkara Navamsha and are especially auspicious — a planet placed in its Pushkara Navamsha gives highly beneficial results.",
    "The 7th house and its lord in D9 determine the deeper nature of marriage and the spouse's inner character — even if D1 7th house is afflicted, a strong D9 7th can salvage marriage happiness.",
    "The D9 chart should confirm D1 indications for any prediction to be reliable — if D1 shows a Raja Yoga but D9 does not support it, the yoga gives only partial results.",
    "Atmakaraka (the planet with the highest degree in any sign) placed in the D9 Navamsha Lagna (Karakamsha) reveals the soul's core desire and dharmic focus for this lifetime.",
    "Malefic planets in the D9 Lagna or aspecting the D9 Lagna lord can indicate spiritual challenges or karmic burdens that the native must consciously address.",
    "Benefic planets in the D9 5th or 9th from the D9 Lagna indicate strong spiritual merit and good fortune that supports the native's evolution.",
    "The D9 chart becomes most relevant in the second half of life (after approximately age 35) — events triggered in later life reflect D9 more strongly than the D1.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Special Lagnas — BPHS Pada Adhyaya and Lagna Viveka
# ─────────────────────────────────────────────────────────────────────────────

SPECIAL_LAGNAS: dict[str, str] = {
    "Arudha Lagna (AL)": (
        "The Arudha Lagna (AL) is the image or maya of the native in the world — how others perceive and experience them, as opposed to their true inner nature shown by the Rashi Lagna. "
        "It is calculated by counting the number of signs from Lagna to its lord, then projecting the same count from the lord — the resulting sign is AL. "
        "If the lord falls in the Lagna itself or the 7th from it, use the 10th and 4th respectively. "
        "Benefic planets in or aspecting AL give a favorable public image; malefics cause a harsh or feared reputation. "
        "The 2nd and 12th from AL show what sustains and what destroys the native's image respectively. "
        "Planets in the 11th from AL bring fame and social rise; planets in the 6th from AL create visible enemies. "
        "The AL is essential for predicting social standing, reputation, and public life events."
    ),
    "Upapada Lagna (UL)": (
        "The Upapada Lagna (UL) is the Arudha of the 12th house — it shows the outer manifestation and image of marriage and the spouse. "
        "It is calculated by projecting the same method as AL but starting from the 12th house and its lord. "
        "Benefic planets in or aspecting UL indicate a favorable, respected, and beautiful spouse; malefics (especially Mars, Saturn, Rahu) can bring difficulties in marriage or a troublesome partner. "
        "The 2nd from UL shows the sustenance and longevity of the marriage — a strong benefic here supports a lasting union. "
        "The 7th from UL (counter-UL) shows the possibility of a second marriage or relationships that challenge the primary union. "
        "The UL sign and its lord's strength and dignity give specific qualities of the spouse and the style of the marriage bond."
    ),
    "Hora Lagna (HL)": (
        "The Hora Lagna (HL) is a special lagna used primarily to assess wealth and financial potential in the chart. "
        "It advances at the rate of one sign per hour from the time of birth (roughly 2.5° per minute of clock time). "
        "Planets in or aspecting HL indicate sources and quality of wealth; benefics in HL or the 2nd from HL bless finances. "
        "The lord of HL and its placement give the primary means through which wealth is acquired. "
        "HL must be assessed alongside the 2nd and 11th houses of the Rashi chart and the Dhana Yogas for a complete financial picture."
    ),
    "Ghati Lagna (GL)": (
        "The Ghati Lagna (GL) advances at one sign per Ghati (24 minutes) and is the fastest-moving special lagna. "
        "GL indicates power, authority, and the native's capacity to command and influence others. "
        "Benefics in GL or aspecting GL confer leadership ability, political power, and authority; malefics create a harsh or domineering exercise of power. "
        "The lord of GL and its placement reveal how and where the native's power is exercised. "
        "Strong GL with benefic influence supports political success and positions of governance or command."
    ),
    "Bhava Lagna (BL)": (
        "The Bhava Lagna (BL) advances at the rate of one sign per two hours and is used to assess the overall bhava (life experience) and longevity. "
        "BL represents the vitality of the life-force and can be used as an additional lagna for confirming house-based results. "
        "Planets in BL or aspecting it give life themes related to those planets; benefics in BL support vitality and positive life experiences. "
        "The conjunction or alignment of BL, HL, and GL in the same sign or house is considered very auspicious and indicates a powerful, multi-dimensional success in the native's life."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Muhurta rules as applied to natal timing predictions — BPHS Kala Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

MUHURTA_RULES: list[str] = [
    "For timing events in a natal chart, identify the house of the event (e.g., 7th for marriage, 5th for children) and watch for the Dasha/Antardasha of its lord, planets therein, and their dispositors.",
    "Events are most likely to manifest when both the Mahadasha and Antardasha lords have a connection (ownership, aspect, or placement) to the relevant house — single-planet activation is rarely sufficient for major life events.",
    "Saturn transiting the relevant event house or aspecting it during a supportive Dasha acts as a maturation trigger — Saturn forces crystallisation of pending karmas.",
    "Jupiter's annual transit activates the houses it passes through — when Jupiter transits the house of the expected event and the Dasha supports it, events precipitate.",
    "The Pratyantardasha (sub-sub period) of a planet connected to the natal house cusp lord often marks the exact window when an event occurs within an Antardasha.",
    "The Ashtakavarga transit strength of the Dasha lord in its current transit sign must be checked — 4+ bindus in its own BAV confirms a productive Dasha period; fewer bindus delays results.",
    "Eclipses (Grahan) that fall on natal planets or house cusps connected to the event house act as powerful activators within 6 months of the eclipse.",
    "For career events, watch for the Sun's annual transit (Gochara) through the 10th house from the natal Moon alongside a supportive 10th house Dasha.",
    "Marriage is typically triggered when the Jupiter Mahadasha or Antardasha activates the 7th lord, Venus, or the 7th house — simultaneously, Saturn should not be transiting the 7th unless it owns it.",
    "The Narayana Dasha of the relevant house (in Jaimini system, used alongside BPHS Vimshottari) crossing the house of the event is one of the most reliable timing tools for specific life events.",
]

# ─────────────────────────────────────────────────────────────────────────────
# Chara Karaka rules — BPHS Karaka Adhyaya (Jaimini Chara Karakas)
# ─────────────────────────────────────────────────────────────────────────────

KARAKA_RULES: dict[str, str] = {
    "AtmaKaraka (AK)": (
        "The AtmaKaraka is the planet with the highest degree in any sign in the natal chart (Rahu counted in reverse). "
        "It represents the soul's primary desire and lesson for this lifetime — the karmic theme the native cannot escape. "
        "The AK placed in the D9 Navamsha Lagna (Karakamsha Lagna) reveals the soul's core purpose and the divine area of focus. "
        "Malefics as AK indicate the soul must master the difficult significations of that planet; benefics as AK give a more graceful spiritual path. "
        "Sun as AK: soul's lesson involves ego, authority, and dharmic responsibility. Moon as AK: emotional nurturing and mind. "
        "Mars as AK: courage, desire, and overcoming conflict. Mercury as AK: intellect and communication. "
        "Jupiter as AK: wisdom, dharma, and expansion. Venus as AK: relationships and material beauty. Saturn as AK: discipline, karma, and service."
    ),
    "AmatyaKaraka (AmK)": (
        "The AmatyaKaraka is the planet with the second-highest degree — it represents the minister or advisor of the soul, indicating career, professional path, and the means through which the AK's purpose is fulfilled. "
        "The AmK and its sign, house placement, and dignity show the nature of the profession and career path. "
        "Jupiter as AmK: career in teaching, law, religion, or counselling. Venus as AmK: arts, beauty, finance, or diplomacy. "
        "Mercury as AmK: business, communication, writing, or accounting. Mars as AmK: engineering, military, surgery, or sports. "
        "Saturn as AmK: service industries, labour, administration, or research."
    ),
    "BhratrKaraka (BK)": (
        "The BhratrKaraka is the planet with the third-highest degree and represents siblings, courage, and co-workers. "
        "It shows the quality of relationships with brothers, sisters, and close collaborators in life. "
        "BK afflicted by malefics or in difficult signs indicates troubled sibling relationships or lack of support from them. "
        "BK strong and well-aspected indicates supportive, prosperous siblings who advance the native's goals."
    ),
    "MatruKaraka (MK)": (
        "The MatruKaraka is the planet with the fourth-highest degree and represents the mother, home, and emotional foundations. "
        "MK's strength and sign placement reveal the quality of the mother's influence and the native's home life. "
        "A strong MK with benefic connections gives a nurturing, supportive mother and stable home environment. "
        "An afflicted MK indicates the mother's health or relationship challenges, or difficulties in establishing a stable home."
    ),
    "PutraKaraka (PK)": (
        "The PutraKaraka is the planet with the fifth-highest degree and represents children, creativity, and past-life merit. "
        "PK indicates the blessings of children and the quality of the native's creative intelligence. "
        "A benefic as PK or PK well-placed in the chart gives good, intelligent children and strong past-life merit. "
        "Malefic PK or PK in difficult houses may indicate delays in children, karmic relationship with offspring, or challenges in creative expression."
    ),
    "GnatiKaraka (GK)": (
        "The GnatiKaraka is the planet with the sixth-highest degree and represents enemies, disease, competition, and obstacles — the obstructions the soul must overcome. "
        "GK shows the source of the native's primary challenges — through the significations of the GK planet and its placement. "
        "A strong GK in a powerful position (like exaltation) indicates powerful enemies or competition but also the strength to overcome them. "
        "Saturn as GK: chronic obstacles through karma and service. Mars as GK: enemies through aggression. Rahu as GK: hidden or foreign adversaries."
    ),
    "DaraKaraka (DK)": (
        "The DaraKaraka is the planet with the lowest degree among the seven and represents the spouse and all significant partnerships. "
        "The DK's sign, house, and dignity reveal the nature of the spouse — their character, appearance, and the quality of the marital bond. "
        "A benefic DK (Jupiter, Venus, or strong Moon) indicates a noble, supportive, and prosperous spouse. "
        "Malefic DK (Saturn, Mars, or Rahu/Ketu) indicates a complex, challenging, or karmic relationship with the spouse, but not necessarily an unhappy one. "
        "The DK placed in the D9 Navamsha chart further refines the spouse's qualities and the deeper nature of the marriage."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Vimshopaka Bala rules — BPHS Vimshopaka Bala Adhyaya
# ─────────────────────────────────────────────────────────────────────────────

VIMSHOPAKA_RULES: list[str] = [
    "Vimshopaka Bala is the strength of a planet derived from its placement across multiple divisional (Varga) charts — the maximum possible score is 20 points (Vimsha = 20), representing full dignity across all relevant Vargas.",
    "BPHS assigns different weights to different Varga charts in calculating Vimshopaka: the Shadvargas (6 divisions) use the D1, D2, D3, D9, D12, and D30; the Saptavargas (7 divisions) add D7; the Dashavargas (10 divisions) add D4, D10, and D16; the Shodashavargas (16 divisions) add all major Vargas.",
    "A planet scoring 15–20 in Vimshopaka Bala is extremely strong and gives consistently excellent results throughout its Dasha — it can fulfil its highest significations.",
    "A planet scoring 10–15 in Vimshopaka Bala gives moderate, generally positive results with occasional fluctuations depending on transit and Dasha support.",
    "A planet scoring below 5 in Vimshopaka Bala is very weak and will give consistently poor, delayed, or distorted results during its Dasha period, regardless of its Rashi position.",
    "Vimshopaka Bala is particularly useful for comparing the strength of two otherwise similar planets — when both seem strong in the D1 Rashi chart, the one with higher Vimshopaka Bala will give stronger results in practice.",
    "A Vargottama planet (same sign in D1 and D9) automatically gains significant Vimshopaka Bala points and should be treated as one of the strongest planets in the chart for event prediction.",
    "When assessing the strength of a Dasha lord, combine Vimshopaka Bala with Shadbala (six-fold strength from Rashi) for a complete picture: a planet strong in both Shadbala and Vimshopaka Bala can deliver outstanding Dasha results without obstruction.",
]
