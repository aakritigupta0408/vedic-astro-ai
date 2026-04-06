"""
gradio_app.py — Vedic Astrology AI · 3-Phase Flow
Phase 1: Compute Chart  (engine only, no LLM)
Phase 2: Calibrate      (10 questions → calibrate weights)
Phase 3: Ask            (question + calibrated prediction)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

import gradio as gr
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# City database
# ─────────────────────────────────────────────────────────────────────────────

CITIES: list[str] = [
    # ── India — Mega cities ───────────────────────────────
    "Mumbai, India", "Delhi, India", "New Delhi, India", "Bengaluru, India",
    "Bangalore, India", "Chennai, India", "Kolkata, India", "Hyderabad, India",
    "Pune, India", "Ahmedabad, India",
    # ── Maharashtra ───────────────────────────────────────
    "Nagpur, India", "Thane, India", "Nashik, India", "Aurangabad, India",
    "Solapur, India", "Kolhapur, India", "Amravati, India", "Nanded, India",
    "Sangli, India", "Jalgaon, India", "Akola, India", "Latur, India",
    "Dhule, India", "Ahmednagar, India", "Chandrapur, India", "Parbhani, India",
    "Ichalkaranji, India", "Jalna, India", "Ambernath, India", "Bhiwandi, India",
    "Panvel, India", "Kalyan, India", "Dombivli, India", "Vasai-Virar, India",
    "Malegaon, India", "Navi Mumbai, India", "Ulhasnagar, India", "Satara, India",
    "Ratnagiri, India", "Sindhudurg, India", "Osmanabad, India", "Beed, India",
    "Hingoli, India", "Washim, India", "Buldhana, India", "Yavatmal, India",
    "Wardha, India", "Gondia, India", "Gadchiroli, India", "Bhandara, India",
    "Shirdi, India", "Pandharpur, India", "Alibag, India",
    # ── Uttar Pradesh ─────────────────────────────────────
    "Lucknow, India", "Kanpur, India", "Agra, India", "Varanasi, India",
    "Prayagraj, India", "Allahabad, India", "Meerut, India", "Ghaziabad, India",
    "Noida, India", "Greater Noida, India", "Bareilly, India", "Aligarh, India",
    "Moradabad, India", "Saharanpur, India", "Gorakhpur, India", "Firozabad, India",
    "Jhansi, India", "Muzaffarnagar, India", "Mathura, India", "Hapur, India",
    "Rampur, India", "Shahjahanpur, India", "Farrukhabad, India", "Mau, India",
    "Haridwar, India", "Etawah, India", "Mirzapur, India", "Bulandshahr, India",
    "Sambhal, India", "Amroha, India", "Hardoi, India", "Fatehpur, India",
    "Raebareli, India", "Orai, India", "Sitapur, India", "Bahraich, India",
    "Unnao, India", "Jaunpur, India", "Lakhimpur, India", "Hathras, India",
    "Banda, India", "Pilibhit, India", "Barabanki, India", "Khurja, India",
    "Gonda, India", "Mainpuri, India", "Lalitpur, India", "Etah, India",
    "Deoria, India", "Basti, India", "Azamgarh, India", "Sultanpur, India",
    "Faizabad, India", "Ayodhya, India", "Ballia, India", "Rishikesh, India",
    "Vrindavan, India", "Nandgaon, India",
    # ── Rajasthan ─────────────────────────────────────────
    "Jaipur, India", "Jodhpur, India", "Kota, India", "Bikaner, India",
    "Ajmer, India", "Udaipur, India", "Bhilwara, India", "Alwar, India",
    "Bharatpur, India", "Sikar, India", "Pali, India", "Sri Ganganagar, India",
    "Hanumangarh, India", "Jhunjhunu, India", "Tonk, India", "Dausa, India",
    "Chittorgarh, India", "Nagaur, India", "Jhalawar, India", "Barmer, India",
    "Jaisalmer, India", "Dungarpur, India", "Banswara, India",
    "Sawai Madhopur, India", "Churu, India", "Dholpur, India", "Karauli, India",
    "Rajsamand, India", "Baran, India", "Bundi, India", "Sirohi, India",
    "Pratapgarh, India", "Pushkar, India", "Nathdwara, India",
    # ── Madhya Pradesh ────────────────────────────────────
    "Indore, India", "Bhopal, India", "Jabalpur, India", "Gwalior, India",
    "Ujjain, India", "Sagar, India", "Dewas, India", "Satna, India",
    "Ratlam, India", "Rewa, India", "Murwara, India", "Singrauli, India",
    "Burhanpur, India", "Khandwa, India", "Bhind, India", "Chhindwara, India",
    "Guna, India", "Shivpuri, India", "Vidisha, India", "Chhatarpur, India",
    "Damoh, India", "Mandsaur, India", "Khargone, India", "Neemuch, India",
    "Pithampur, India", "Hoshangabad, India", "Itarsi, India", "Sehore, India",
    "Betul, India", "Seoni, India", "Datia, India", "Nagda, India",
    "Omkareshwar, India", "Pachmarhi, India", "Orchha, India",
    # ── Gujarat ───────────────────────────────────────────
    "Surat, India", "Vadodara, India", "Rajkot, India", "Bhavnagar, India",
    "Jamnagar, India", "Junagadh, India", "Gandhinagar, India", "Anand, India",
    "Navsari, India", "Morbi, India", "Nadiad, India", "Surendranagar, India",
    "Bharuch, India", "Mehsana, India", "Bhuj, India", "Botad, India",
    "Amreli, India", "Valsad, India", "Patan, India", "Dahod, India",
    "Porbandar, India", "Godhra, India", "Veraval, India", "Palanpur, India",
    "Ankleshwar, India", "Dwarka, India", "Somnath, India", "Vapi, India",
    "Silvassa, India", "Daman, India", "Diu, India",
    # ── Tamil Nadu ────────────────────────────────────────
    "Coimbatore, India", "Madurai, India", "Tiruchirappalli, India",
    "Salem, India", "Tirunelveli, India", "Tiruppur, India", "Vellore, India",
    "Erode, India", "Thoothukudi, India", "Dindigul, India", "Thanjavur, India",
    "Ranipet, India", "Sivakasi, India", "Karur, India", "Ooty, India",
    "Hosur, India", "Nagercoil, India", "Kanchipuram, India",
    "Kumbakonam, India", "Tambaram, India", "Avadi, India",
    "Tiruvannamalai, India", "Pollachi, India", "Rajapalayam, India",
    "Pudukkottai, India", "Nagapattinam, India", "Villupuram, India",
    "Cuddalore, India", "Chidambaram, India", "Mayiladuthurai, India",
    "Namakkal, India", "Dharmapuri, India", "Krishnagiri, India",
    "Tiruvallur, India", "Mahabalipuram, India", "Rameswaram, India",
    # ── Karnataka ─────────────────────────────────────────
    "Mysuru, India", "Mysore, India", "Hubli, India", "Mangaluru, India",
    "Mangalore, India", "Belagavi, India", "Belgaum, India",
    "Kalaburagi, India", "Gulbarga, India", "Davangere, India",
    "Ballari, India", "Bellary, India", "Vijayapura, India", "Bijapur, India",
    "Shivamogga, India", "Tumkur, India", "Raichur, India", "Bidar, India",
    "Hospet, India", "Hassan, India", "Gadag, India", "Udupi, India",
    "Dharwad, India", "Chitradurga, India", "Bagalkot, India", "Mandya, India",
    "Kolar, India", "Chikballapur, India", "Chikkamagaluru, India",
    "Koppal, India", "Yadgir, India", "Haveri, India", "Karwar, India",
    "Sirsi, India", "Hampi, India", "Badami, India", "Pattadakal, India",
    # ── Andhra Pradesh ────────────────────────────────────
    "Visakhapatnam, India", "Vijayawada, India", "Guntur, India",
    "Tirupati, India", "Nellore, India", "Kurnool, India",
    "Rajahmundry, India", "Kakinada, India", "Kadapa, India",
    "Anantapur, India", "Vizianagaram, India", "Eluru, India",
    "Ongole, India", "Nandyal, India", "Machilipatnam, India", "Adoni, India",
    "Tenali, India", "Proddatur, India", "Chittoor, India", "Hindupur, India",
    "Bhimavaram, India", "Amaravati, India", "Srikakulam, India",
    # ── Telangana ─────────────────────────────────────────
    "Warangal, India", "Nizamabad, India", "Khammam, India",
    "Karimnagar, India", "Ramagundam, India", "Mahabubnagar, India",
    "Nalgonda, India", "Adilabad, India", "Suryapet, India",
    "Miryalaguda, India", "Jagtial, India", "Mancherial, India",
    "Kothagudem, India", "Secunderabad, India",
    # ── Kerala ────────────────────────────────────────────
    "Thiruvananthapuram, India", "Kochi, India", "Kozhikode, India",
    "Thrissur, India", "Kollam, India", "Palakkad, India", "Alappuzha, India",
    "Malappuram, India", "Kannur, India", "Kasaragod, India", "Kottayam, India",
    "Pathanamthitta, India", "Ernakulam, India", "Vatakara, India",
    "Thalassery, India", "Ponnani, India", "Chalakudy, India",
    "Changanassery, India", "Guruvayur, India", "Munnar, India",
    "Thekkady, India", "Varkala, India", "Kovalam, India",
    # ── Punjab ────────────────────────────────────────────
    "Ludhiana, India", "Amritsar, India", "Jalandhar, India", "Patiala, India",
    "Bathinda, India", "Mohali, India", "Hoshiarpur, India", "Gurdaspur, India",
    "Pathankot, India", "Moga, India", "Abohar, India", "Malerkotla, India",
    "Khanna, India", "Phagwara, India", "Muktsar, India", "Barnala, India",
    "Rajpura, India", "Firozpur, India", "Kapurthala, India", "Sangrur, India",
    "Fatehgarh Sahib, India", "Ropar, India", "Nawanshahr, India",
    "Tarn Taran, India", "Anandpur Sahib, India",
    # ── Haryana ───────────────────────────────────────────
    "Faridabad, India", "Gurugram, India", "Gurgaon, India", "Panipat, India",
    "Ambala, India", "Yamunanagar, India", "Rohtak, India", "Hisar, India",
    "Karnal, India", "Sonipat, India", "Panchkula, India", "Bhiwani, India",
    "Sirsa, India", "Bahadurgarh, India", "Jind, India", "Thanesar, India",
    "Kaithal, India", "Rewari, India", "Palwal, India", "Hansi, India",
    "Narnaul, India", "Fatehabad, India", "Kurukshetra, India",
    # ── West Bengal ───────────────────────────────────────
    "Kolkata, India", "Howrah, India", "Asansol, India", "Siliguri, India",
    "Durgapur, India", "Bardhaman, India", "Burdwan, India", "Malda, India",
    "Baharampur, India", "Habra, India", "Kharagpur, India", "Shantipur, India",
    "Dankuni, India", "Ranaghat, India", "Haldia, India", "Raiganj, India",
    "Krishnanagar, India", "Nabadwip, India", "Medinipur, India",
    "Jalpaiguri, India", "Cooch Behar, India", "Darjeeling, India",
    "Alipurduar, India", "Bankura, India", "Purulia, India",
    "Bishnupur, India", "Murshidabad, India", "Balurghat, India",
    "Barasat, India",
    # ── Bihar ─────────────────────────────────────────────
    "Patna, India", "Gaya, India", "Bhagalpur, India", "Muzaffarpur, India",
    "Purnia, India", "Darbhanga, India", "Bihar Sharif, India", "Arrah, India",
    "Begusarai, India", "Katihar, India", "Munger, India", "Chhapra, India",
    "Danapur, India", "Bettiah, India", "Saharsa, India", "Sasaram, India",
    "Hajipur, India", "Dehri, India", "Siwan, India", "Motihari, India",
    "Nawada, India", "Bagaha, India", "Buxar, India", "Kishanganj, India",
    "Sitamarhi, India", "Supaul, India", "Madhubani, India",
    "Bodh Gaya, India", "Nalanda, India", "Rajgir, India",
    # ── Odisha ────────────────────────────────────────────
    "Bhubaneswar, India", "Cuttack, India", "Rourkela, India",
    "Berhampur, India", "Sambalpur, India", "Puri, India", "Balasore, India",
    "Bhadrak, India", "Baripada, India", "Jharsuguda, India", "Bargarh, India",
    "Jeypore, India", "Rayagada, India", "Koraput, India", "Kendujhar, India",
    "Angul, India", "Dhenkanal, India", "Konark, India",
    # ── Assam & North East ────────────────────────────────
    "Guwahati, India", "Dispur, India", "Silchar, India", "Dibrugarh, India",
    "Jorhat, India", "Nagaon, India", "Tinsukia, India", "Tezpur, India",
    "Goalpara, India", "Bongaigaon, India", "Dhubri, India",
    "Karimganj, India", "Imphal, India", "Shillong, India", "Aizawl, India",
    "Kohima, India", "Itanagar, India", "Agartala, India", "Gangtok, India",
    # ── Jharkhand ─────────────────────────────────────────
    "Ranchi, India", "Jamshedpur, India", "Dhanbad, India", "Bokaro, India",
    "Deoghar, India", "Hazaribagh, India", "Giridih, India", "Ramgarh, India",
    "Dumka, India", "Chaibasa, India",
    # ── Chhattisgarh ──────────────────────────────────────
    "Raipur, India", "Bhilai, India", "Korba, India", "Bilaspur, India",
    "Durg, India", "Rajnandgaon, India", "Jagdalpur, India",
    "Ambikapur, India", "Raigarh, India",
    # ── Uttarakhand ───────────────────────────────────────
    "Dehradun, India", "Haridwar, India", "Roorkee, India", "Haldwani, India",
    "Rudrapur, India", "Kashipur, India", "Rishikesh, India", "Kotdwar, India",
    "Ramnagar, India", "Mussoorie, India", "Nainital, India", "Almora, India",
    "Pithoragarh, India", "Kedarnath, India", "Badrinath, India",
    # ── Himachal Pradesh ──────────────────────────────────
    "Shimla, India", "Dharamshala, India", "Solan, India", "Mandi, India",
    "Palampur, India", "Baddi, India", "Nahan, India", "Kullu, India",
    "Manali, India", "Chamba, India", "Una, India", "Hamirpur, India",
    "Kangra, India", "Kasauli, India", "Dalhousie, India",
    # ── J&K & Ladakh ──────────────────────────────────────
    "Srinagar, India", "Jammu, India", "Anantnag, India", "Sopore, India",
    "Baramulla, India", "Leh, India", "Kargil, India", "Kathua, India",
    "Udhampur, India", "Rajouri, India", "Pahalgam, India", "Gulmarg, India",
    # ── Goa ───────────────────────────────────────────────
    "Panaji, India", "Margao, India", "Vasco da Gama, India", "Mapusa, India",
    "Ponda, India", "Calangute, India", "Baga, India",
    # ── Union Territories ─────────────────────────────────
    "Chandigarh, India", "Puducherry, India", "Pondicherry, India",
    "Port Blair, India",
    # ── International ─────────────────────────────────────
    "London, UK", "Manchester, UK", "Birmingham, UK", "Glasgow, UK",
    "Liverpool, UK", "Leeds, UK", "Sheffield, UK", "Bristol, UK",
    "Edinburgh, UK", "Leicester, UK", "Coventry, UK", "Bradford, UK",
    "Nottingham, UK", "Cardiff, UK", "Belfast, UK", "Southampton, UK",
    "Oxford, UK", "Cambridge, UK",
    "New York, USA", "Los Angeles, USA", "Chicago, USA", "Houston, USA",
    "Phoenix, USA", "Philadelphia, USA", "San Antonio, USA", "San Diego, USA",
    "Dallas, USA", "San Jose, USA", "Austin, USA", "San Francisco, USA",
    "Seattle, USA", "Denver, USA", "Nashville, USA", "Washington DC, USA",
    "Boston, USA", "Las Vegas, USA", "Portland, USA", "Atlanta, USA",
    "Miami, USA", "Minneapolis, USA",
    "Toronto, Canada", "Vancouver, Canada", "Montreal, Canada",
    "Calgary, Canada", "Edmonton, Canada", "Ottawa, Canada",
    "Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia",
    "Perth, Australia", "Adelaide, Australia", "Auckland, New Zealand",
    "Paris, France", "Berlin, Germany", "Madrid, Spain", "Rome, Italy",
    "Amsterdam, Netherlands", "Brussels, Belgium", "Vienna, Austria",
    "Zurich, Switzerland", "Geneva, Switzerland", "Stockholm, Sweden",
    "Oslo, Norway", "Copenhagen, Denmark", "Helsinki, Finland",
    "Lisbon, Portugal", "Athens, Greece", "Warsaw, Poland",
    "Prague, Czech Republic", "Budapest, Hungary", "Munich, Germany",
    "Hamburg, Germany", "Frankfurt, Germany", "Barcelona, Spain",
    "Milan, Italy", "Naples, Italy",
    "Dubai, UAE", "Abu Dhabi, UAE", "Riyadh, Saudi Arabia",
    "Jeddah, Saudi Arabia", "Mecca, Saudi Arabia", "Medina, Saudi Arabia",
    "Kuwait City, Kuwait", "Doha, Qatar", "Manama, Bahrain", "Muscat, Oman",
    "Beirut, Lebanon", "Amman, Jordan", "Baghdad, Iraq", "Tehran, Iran",
    "Istanbul, Turkey", "Ankara, Turkey", "Tel Aviv, Israel",
    "Jerusalem, Israel",
    "Tokyo, Japan", "Osaka, Japan", "Kyoto, Japan", "Yokohama, Japan",
    "Beijing, China", "Shanghai, China", "Shenzhen, China", "Guangzhou, China",
    "Hong Kong", "Seoul, South Korea", "Singapore", "Kuala Lumpur, Malaysia",
    "Bangkok, Thailand", "Jakarta, Indonesia", "Manila, Philippines",
    "Hanoi, Vietnam", "Ho Chi Minh City, Vietnam", "Colombo, Sri Lanka",
    "Dhaka, Bangladesh", "Karachi, Pakistan", "Lahore, Pakistan",
    "Islamabad, Pakistan", "Kathmandu, Nepal", "Kabul, Afghanistan",
    "Cairo, Egypt", "Lagos, Nigeria", "Nairobi, Kenya",
    "Johannesburg, South Africa", "Cape Town, South Africa",
    "Casablanca, Morocco", "Accra, Ghana", "Addis Ababa, Ethiopia",
    "São Paulo, Brazil", "Rio de Janeiro, Brazil", "Buenos Aires, Argentina",
    "Lima, Peru", "Bogotá, Colombia", "Santiago, Chile",
    "Mexico City, Mexico", "Guadalajara, Mexico",
    "Moscow, Russia", "Saint Petersburg, Russia",
    "Kyiv, Ukraine", "Minsk, Belarus", "Tbilisi, Georgia",
]

CITIES_SORTED = sorted(set(CITIES))

# ─────────────────────────────────────────────────────────────────────────────
# City → (lat, lon) lookup  — fills UI fields instantly on city select
# Falls through to pipeline geocoder for anything not listed here
# ─────────────────────────────────────────────────────────────────────────────
CITY_COORDS: dict[str, tuple[float, float]] = {
    # India — major
    "Mumbai, India": (19.0760, 72.8777), "Delhi, India": (28.6139, 77.2090),
    "New Delhi, India": (28.6139, 77.2090), "Bengaluru, India": (12.9716, 77.5946),
    "Bangalore, India": (12.9716, 77.5946), "Chennai, India": (13.0827, 80.2707),
    "Kolkata, India": (22.5726, 88.3639), "Hyderabad, India": (17.3850, 78.4867),
    "Pune, India": (18.5204, 73.8567), "Ahmedabad, India": (23.0225, 72.5714),
    "Surat, India": (21.1702, 72.8311), "Jaipur, India": (26.9124, 75.7873),
    "Lucknow, India": (26.8467, 80.9462), "Kanpur, India": (26.4499, 80.3319),
    "Nagpur, India": (21.1458, 79.0882), "Indore, India": (22.7196, 75.8577),
    "Bhopal, India": (23.2599, 77.4126), "Patna, India": (25.5941, 85.1376),
    "Varanasi, India": (25.3176, 82.9739), "Agra, India": (27.1767, 78.0081),
    "Srinagar, India": (34.0837, 74.7973), "Amritsar, India": (31.6340, 74.8723),
    "Chandigarh, India": (30.7333, 76.7794), "Coimbatore, India": (11.0168, 76.9558),
    "Kochi, India": (9.9312, 76.2673), "Mysuru, India": (12.2958, 76.6394),
    "Mysore, India": (12.2958, 76.6394), "Visakhapatnam, India": (17.6868, 83.2185),
    "Thiruvananthapuram, India": (8.5241, 76.9366), "Guwahati, India": (26.1445, 91.7362),
    "Bhubaneswar, India": (20.2961, 85.8245), "Raipur, India": (21.2514, 81.6296),
    "Vadodara, India": (22.3072, 73.1812), "Rajkot, India": (22.3039, 70.8022),
    "Tirupati, India": (13.6288, 79.4192), "Madurai, India": (9.9252, 78.1198),
    "Ludhiana, India": (30.9010, 75.8573), "Faridabad, India": (28.4089, 77.3178),
    "Gurugram, India": (28.4595, 77.0266), "Gurgaon, India": (28.4595, 77.0266),
    "Noida, India": (28.5355, 77.3910), "Navi Mumbai, India": (19.0368, 73.0158),
    "Meerut, India": (28.9845, 77.7064), "Prayagraj, India": (25.4358, 81.8463),
    "Allahabad, India": (25.4358, 81.8463), "Gorakhpur, India": (26.7606, 83.3732),
    "Jodhpur, India": (26.2389, 73.0243), "Kota, India": (25.2138, 75.8648),
    "Udaipur, India": (24.5854, 73.7125), "Jabalpur, India": (23.1815, 79.9864),
    "Gwalior, India": (26.2183, 78.1828), "Ujjain, India": (23.1765, 75.7885),
    # Global
    "London, UK": (51.5074, -0.1278), "New York, USA": (40.7128, -74.0060),
    "Los Angeles, USA": (34.0522, -118.2437), "Chicago, USA": (41.8781, -87.6298),
    "Toronto, Canada": (43.6532, -79.3832), "Vancouver, Canada": (49.2827, -123.1207),
    "Sydney, Australia": (-33.8688, 151.2093), "Melbourne, Australia": (-37.8136, 144.9631),
    "Singapore": (1.3521, 103.8198), "Dubai, UAE": (25.2048, 55.2708),
    "Abu Dhabi, UAE": (24.4539, 54.3773), "Kuala Lumpur, Malaysia": (3.1390, 101.6869),
    "Bangkok, Thailand": (13.7563, 100.5018), "Tokyo, Japan": (35.6762, 139.6503),
    "Beijing, China": (39.9042, 116.4074), "Shanghai, China": (31.2304, 121.4737),
    "Hong Kong": (22.3193, 114.1694), "Seoul, South Korea": (37.5665, 126.9780),
    "Jakarta, Indonesia": (-6.2088, 106.8456), "Manila, Philippines": (14.5995, 120.9842),
    "Karachi, Pakistan": (24.8607, 67.0011), "Lahore, Pakistan": (31.5204, 74.3587),
    "Dhaka, Bangladesh": (23.8103, 90.4125), "Colombo, Sri Lanka": (6.9271, 79.8612),
    "Kathmandu, Nepal": (27.7172, 85.3240), "Kabul, Afghanistan": (34.5553, 69.2075),
    "Berlin, Germany": (52.5200, 13.4050), "Paris, France": (48.8566, 2.3522),
    "Amsterdam, Netherlands": (52.3676, 4.9041), "Brussels, Belgium": (50.8503, 4.3517),
    "Madrid, Spain": (40.4168, -3.7038), "Barcelona, Spain": (41.3851, 2.1734),
    "Rome, Italy": (41.9028, 12.4964), "Milan, Italy": (45.4642, 9.1900),
    "Zurich, Switzerland": (47.3769, 8.5417), "Vienna, Austria": (48.2082, 16.3738),
    "Stockholm, Sweden": (59.3293, 18.0686), "Oslo, Norway": (59.9139, 10.7522),
    "Copenhagen, Denmark": (55.6761, 12.5683), "Helsinki, Finland": (60.1699, 24.9384),
    "Moscow, Russia": (55.7558, 37.6176), "Istanbul, Turkey": (41.0082, 28.9784),
    "Cairo, Egypt": (30.0444, 31.2357), "Lagos, Nigeria": (6.5244, 3.3792),
    "Nairobi, Kenya": (-1.2921, 36.8219), "Johannesburg, South Africa": (-26.2041, 28.0473),
    "Cape Town, South Africa": (-33.9249, 18.4241),
    "São Paulo, Brazil": (-23.5505, -46.6333), "Rio de Janeiro, Brazil": (-22.9068, -43.1729),
    "Buenos Aires, Argentina": (-34.6037, -58.3816), "Lima, Peru": (-12.0464, -77.0428),
    "Mexico City, Mexico": (19.4326, -99.1332), "San Francisco, USA": (37.7749, -122.4194),
    "Seattle, USA": (47.6062, -122.3321), "Boston, USA": (42.3601, -71.0589),
    "Miami, USA": (25.7617, -80.1918), "Dallas, USA": (32.7767, -96.7970),
    "Houston, USA": (29.7604, -95.3698), "Atlanta, USA": (33.7490, -84.3880),
}


def fill_coords(place_str: str) -> tuple[str, str]:
    """Return (lat_str, lon_str) for a recognised city, or ('', '') otherwise."""
    if not place_str:
        return "", ""
    key = place_str.strip()
    coords = CITY_COORDS.get(key)
    if coords is None:
        # case-insensitive fallback
        kl = key.lower()
        coords = next((v for k, v in CITY_COORDS.items() if k.lower() == kl), None)
    if coords:
        return f"{coords[0]:.4f}", f"{coords[1]:.4f}"
    return "", ""   # pipeline will geocode during computation


def search_places(query: str) -> list[str]:
    if not query or len(query.strip()) < 2:
        return CITIES_SORTED[:20]
    q = query.strip().lower()
    prefix = [c for c in CITIES_SORTED if c.lower().startswith(q)]
    substr = [c for c in CITIES_SORTED if q in c.lower() and c not in prefix]
    return (prefix + substr)[:12]


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
/* ═══════════════════════════════════════════════════════════════
   Vedic Astrology AI — Apple iOS-inspired mobile-first UI v0.2.0
   Design language: iOS 17 / visionOS human interface guidelines
   ═══════════════════════════════════════════════════════════════ */

/* ── Keyframe animations ──────────────────────────────────────── */
@keyframes twinkle {
    0%, 100% { opacity: 0.15; transform: scale(0.7); }
    50%       { opacity: 0.9;  transform: scale(1.2); }
}
@keyframes twinkle-slow {
    0%, 100% { opacity: 0.08; transform: scale(0.8); }
    60%       { opacity: 0.6;  transform: scale(1.1); }
}
@keyframes zodiac-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}
@keyframes zodiac-spin-rev {
    from { transform: rotate(0deg); }
    to   { transform: rotate(-360deg); }
}
@keyframes orbit-dot {
    from { transform: rotate(0deg) translateX(22px) rotate(0deg); }
    to   { transform: rotate(360deg) translateX(22px) rotate(-360deg); }
}
@keyframes orbit-dot-fast {
    from { transform: rotate(0deg) translateX(14px) rotate(0deg); }
    to   { transform: rotate(360deg) translateX(14px) rotate(-360deg); }
}
@keyframes shimmer-bar {
    0%   { background-position: -300% center; }
    100% { background-position: 300% center; }
}
@keyframes glow-pulse {
    0%, 100% { box-shadow: 0 2px 12px rgba(0,122,255,0.30); }
    50%       { box-shadow: 0 2px 22px rgba(0,122,255,0.55), 0 0 0 3px rgba(0,122,255,0.12); }
}
@keyframes card-appear {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes hdr-gradient {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes float-symbol {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-4px); }
}

/* ── Reset & base ─────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

body, .gradio-container {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                 "SF Pro Text", "Helvetica Neue", Arial, sans-serif !important;
    background: #F2F2F7 !important;          /* iOS grouped bg */
    color: #1C1C1E !important;               /* iOS label */
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
}

.gradio-container {
    max-width: 520px !important;             /* Phone-width first */
    margin: 0 auto !important;
    padding: 0 0 env(safe-area-inset-bottom, 1.5rem) !important;
}

/* Wider on tablet/desktop */
@media (min-width: 768px) {
    .gradio-container { max-width: 820px !important; padding: 0 1rem 3rem !important; }
}
@media (min-width: 1100px) {
    .gradio-container { max-width: 1200px !important; }
}

/* ── Sticky iOS-style navigation header ───────────────────────── */
.ios-nav {
    position: sticky; top: 0; z-index: 100;
    background: rgba(242,242,247,0.85) !important;
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    backdrop-filter: blur(20px) saturate(180%);
    border-bottom: 0.5px solid rgba(60,60,67,0.18);
    padding: env(safe-area-inset-top, 0) 0 0;
}

/* ── Header ───────────────────────────────────────────────────── */
.hdr {
    text-align: center;
    padding: 2.2rem 1.2rem 1rem;
    position: relative; overflow: hidden;
    background: linear-gradient(135deg, #0f0c29, #302b63, #1a1a2e, #16213e, #0f3460);
    background-size: 400% 400%;
    animation: hdr-gradient 18s ease infinite;
    border-bottom: none;
}
.hdr h1 {
    font-size: 1.9rem; font-weight: 700;
    letter-spacing: -0.035em;
    margin: 0 0 0.35rem; line-height: 1.1;
    background: linear-gradient(135deg, #e8d5b7 0%, #f9f3e3 40%, #c9a96e 70%, #e8d5b7 100%);
    background-size: 200% auto;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    animation: shimmer-bar 6s linear infinite;
}
.hdr p {
    font-size: 0.82rem; color: rgba(255,255,255,0.55);
    margin: 0; letter-spacing: 0.01em;
    line-height: 1.5;
}
@media (min-width: 768px) {
    .hdr h1 { font-size: 2.6rem; }
    .hdr p  { font-size: 0.95rem; }
}

/* Star field inside header */
.hdr-star {
    position: absolute; border-radius: 50%;
    background: #fff; pointer-events: none;
}
.hdr-star.s1  { width:2px; height:2px; top:15%; left:8%;  animation: twinkle 2.1s 0.0s infinite; }
.hdr-star.s2  { width:3px; height:3px; top:25%; left:18%; animation: twinkle 3.3s 0.4s infinite; }
.hdr-star.s3  { width:2px; height:2px; top:10%; left:32%; animation: twinkle 2.7s 1.1s infinite; }
.hdr-star.s4  { width:2px; height:2px; top:40%; left:55%; animation: twinkle-slow 4.1s 0.8s infinite; }
.hdr-star.s5  { width:3px; height:3px; top:20%; left:70%; animation: twinkle 2.4s 0.2s infinite; }
.hdr-star.s6  { width:2px; height:2px; top:35%; left:82%; animation: twinkle 3.8s 1.5s infinite; }
.hdr-star.s7  { width:2px; height:2px; top:50%; left:91%; animation: twinkle-slow 5.0s 0.6s infinite; }
.hdr-star.s8  { width:3px; height:3px; top:60%; left:6%;  animation: twinkle 2.9s 1.9s infinite; }
.hdr-star.s9  { width:2px; height:2px; top:70%; left:42%; animation: twinkle 3.5s 0.3s infinite; }
.hdr-star.s10 { width:2px; height:2px; top:75%; left:65%; animation: twinkle-slow 4.6s 1.2s infinite; }
.hdr-star.s11 { width:3px; height:3px; top:12%; left:48%; animation: twinkle 2.2s 0.7s infinite; }
.hdr-star.s12 { width:2px; height:2px; top:55%; left:28%; animation: twinkle 3.1s 2.0s infinite; }

/* Zodiac ring wrapper */
.zodiac-ring-wrap {
    position: relative; display: inline-flex;
    align-items: center; justify-content: center;
    width: 72px; height: 72px; margin: 0 auto 0.6rem;
}
.zodiac-ring {
    position: absolute; width: 100%; height: 100%;
    animation: zodiac-spin 60s linear infinite;
}
.zodiac-ring span {
    position: absolute; top: 50%; left: 50%;
    font-size: 0.7rem; opacity: 0.7;
    transform-origin: 0 0;
    color: rgba(232,213,183,0.85);
}
/* Place each symbol around a 34px radius circle */
.zodiac-ring .z0  { transform: rotate(  0deg) translate(34px,-50%); }
.zodiac-ring .z1  { transform: rotate( 30deg) translate(34px,-50%); }
.zodiac-ring .z2  { transform: rotate( 60deg) translate(34px,-50%); }
.zodiac-ring .z3  { transform: rotate( 90deg) translate(34px,-50%); }
.zodiac-ring .z4  { transform: rotate(120deg) translate(34px,-50%); }
.zodiac-ring .z5  { transform: rotate(150deg) translate(34px,-50%); }
.zodiac-ring .z6  { transform: rotate(180deg) translate(34px,-50%); }
.zodiac-ring .z7  { transform: rotate(210deg) translate(34px,-50%); }
.zodiac-ring .z8  { transform: rotate(240deg) translate(34px,-50%); }
.zodiac-ring .z9  { transform: rotate(270deg) translate(34px,-50%); }
.zodiac-ring .z10 { transform: rotate(300deg) translate(34px,-50%); }
.zodiac-ring .z11 { transform: rotate(330deg) translate(34px,-50%); }
/* Central glyph */
.zodiac-center {
    font-size: 1.6rem; z-index: 1;
    animation: float-symbol 4s ease-in-out infinite;
    color: rgba(232,213,183,0.95);
    text-shadow: 0 0 12px rgba(232,213,183,0.6);
}

/* Orbiting planet dots near compute button */
.orbit-wrap {
    position: relative; display: inline-block;
    width: 100%; text-align: center;
}
.orbit-dot {
    position: absolute; top: 50%; left: 50%;
    width: 6px; height: 6px; border-radius: 50%;
    margin: -3px; background: #007AFF;
    animation: orbit-dot 3s linear infinite;
}
.orbit-dot.d2 {
    background: #FF9F0A;
    animation: orbit-dot 5s linear infinite reverse;
    width: 5px; height: 5px;
}

/* Card entrance animation */
.card, .p3-card {
    animation: card-appear 0.4s ease both;
}

/* Phase stepper planet symbols */
.planet-glyph {
    font-size: 1rem; display: inline-block;
    animation: float-symbol 3.5s ease-in-out infinite;
}
.step.active .planet-glyph { color: #007AFF; }
.step.done   .planet-glyph { color: #30D158; }

/* ── Phase stepper — iOS segmented control style ─────────────── */
.stepper {
    display: flex; justify-content: center;
    gap: 0; margin: 0; padding: 0.9rem 1.2rem 0;
    overflow-x: auto; -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
}
.stepper::-webkit-scrollbar { display: none; }
.step {
    display: flex; align-items: center; gap: 0.4rem;
    padding: 0.55rem 1rem;
    font-size: 0.75rem; font-weight: 600;
    color: #8E8E93; border-bottom: 2.5px solid transparent;
    cursor: default; letter-spacing: -0.01em;
    white-space: nowrap; transition: all 0.2s ease;
    min-height: 44px;                        /* iOS touch target */
}
.step.active { color: #007AFF; border-bottom-color: #007AFF; }
.step.done   { color: #30D158; border-bottom-color: #30D158; }
.step-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.25rem; height: 1.25rem; border-radius: 50%;
    background: #E5E5EA; color: #8E8E93;
    font-size: 0.65rem; font-weight: 700;
    transition: all 0.2s ease; flex-shrink: 0;
}
.step.active .step-num { background: #007AFF; color: #fff; }
.step.done   .step-num { background: #30D158; color: #fff; }

/* ── iOS-style grouped cards ──────────────────────────────────── */
.card {
    background: #fff !important;
    border-radius: 16px !important;
    padding: 1.2rem 1rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 20px rgba(0,0,0,0.04) !important;
    margin-bottom: 0 !important;
}
@media (min-width: 768px) {
    .card { padding: 1.5rem 1.4rem !important; border-radius: 18px !important; }
}

/* ── Section labels — iOS grouped section header style ───────── */
.sec-label {
    font-size: 0.62rem !important; font-weight: 600 !important;
    letter-spacing: 0.075em !important; text-transform: uppercase !important;
    color: #8E8E93 !important; margin: 1.2rem 0 0.5rem !important;
    display: block !important; line-height: 1 !important;
    padding-left: 0.1rem !important;
}
.sec-label:first-child { margin-top: 0 !important; }

.sec-heading {
    font-size: 0.62rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.075em; color: #8E8E93;
    margin: 0 0 0.75rem; padding-left: 0.1rem;
}

/* ── Inputs — iOS text field style ───────────────────────────── */
label > span {
    font-size: 0.82rem !important; font-weight: 500 !important;
    color: #3A3A3C !important; letter-spacing: -0.005em !important;
}
input[type=number], input[type=text], textarea, select {
    background: #F2F2F7 !important;
    border: 1px solid rgba(60,60,67,0.13) !important;
    border-radius: 10px !important;
    font-size: 0.92rem !important;
    color: #1C1C1E !important;
    font-family: inherit !important;
    padding: 0.7rem 0.8rem !important;
    min-height: 44px !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease !important;
}
input[type=number]:focus, input[type=text]:focus, textarea:focus, select:focus {
    background: #fff !important;
    border-color: #007AFF !important;
    box-shadow: 0 0 0 3.5px rgba(0,122,255,0.15) !important;
    outline: none !important;
}

/* ── Buttons — iOS pill style ─────────────────────────────────── */
.btn-primary {
    background: #007AFF !important; color: #fff !important;
    border: none !important; border-radius: 980px !important;
    font-weight: 600 !important; font-size: 0.95rem !important;
    min-height: 50px !important; padding: 0 1.8rem !important;
    font-family: inherit !important; width: 100% !important;
    letter-spacing: -0.01em !important;
    transition: background 0.15s ease, transform 0.12s ease,
                box-shadow 0.15s ease !important;
    box-shadow: 0 2px 12px rgba(0,122,255,0.30) !important;
}
.btn-primary:hover {
    background: #0A84FF !important;
    box-shadow: 0 4px 16px rgba(0,122,255,0.38) !important;
}
.btn-primary:active { transform: scale(0.97) !important; background: #0071E3 !important; }

.btn-secondary {
    background: #E5E5EA !important; color: #3A3A3C !important;
    border: none !important; border-radius: 980px !important;
    font-weight: 500 !important; font-size: 0.86rem !important;
    min-height: 40px !important; padding: 0 1.2rem !important;
    font-family: inherit !important;
    transition: background 0.15s ease !important;
}
.btn-secondary:hover { background: #D1D1D6 !important; }
.btn-secondary:active { transform: scale(0.97) !important; }

/* ── Chat — iMessage bubble style ────────────────────────────── */
.chatbot {
    border: 1px solid rgba(60,60,67,0.12) !important;
    border-radius: 16px !important;
    background: #F2F2F7 !important;
    overflow: hidden !important;
}
.chatbot .message {
    font-size: 0.92rem !important; line-height: 1.72 !important;
    letter-spacing: -0.005em !important;
}
/* User bubble */
.chatbot .message.user {
    background: #007AFF !important;
    color: #fff !important;
    border-radius: 18px 18px 4px 18px !important;
    margin-left: auto !important;
    max-width: 85% !important;
}
/* Assistant bubble */
.chatbot .message.bot, .chatbot .message.assistant {
    background: #fff !important;
    border-radius: 18px 18px 18px 4px !important;
    max-width: 95% !important;
    border: 1px solid rgba(60,60,67,0.08) !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}

.query-box textarea {
    border-radius: 12px !important;
    border: 1px solid rgba(60,60,67,0.13) !important;
    background: #fff !important;
    font-size: 0.95rem !important;
    resize: none !important;
    min-height: 52px !important;
    line-height: 1.55 !important;
    padding: 0.7rem 1rem !important;
}
.query-box textarea:focus {
    border-color: #007AFF !important;
    box-shadow: 0 0 0 3.5px rgba(0,122,255,0.15) !important;
}

/* ── Send button — circular iOS style ────────────────────────── */
.ask-btn {
    min-height: 52px !important; min-width: 52px !important;
    width: 52px !important; border-radius: 50% !important;
    padding: 0 !important; font-size: 1.2rem !important;
    box-shadow: 0 2px 10px rgba(0,122,255,0.30) !important;
}

/* ── Status line ──────────────────────────────────────────────── */
.status-line { font-size: 0.78rem !important; color: #8E8E93 !important; text-align: center; }
.status-line p { margin: 0.25rem 0 !important; }

/* ── Tabs — iOS style ─────────────────────────────────────────── */
.tab-nav, [data-testid="tab-nav"] {
    border-bottom: 0.5px solid rgba(60,60,67,0.18) !important;
    overflow-x: auto !important; -webkit-overflow-scrolling: touch !important;
    scrollbar-width: none !important;
    background: #fff !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 0 0.5rem !important;
}
.tab-nav::-webkit-scrollbar { display: none !important; }
.tab-nav button {
    font-size: 0.78rem !important; font-weight: 500 !important;
    color: #8E8E93 !important; border: none !important;
    border-bottom: 2.5px solid transparent !important;
    border-radius: 0 !important; padding: 0.6rem 0.9rem !important;
    background: transparent !important; font-family: inherit !important;
    white-space: nowrap !important; min-height: 44px !important;
    transition: color 0.15s, border-color 0.15s !important;
}
.tab-nav button.selected {
    color: #007AFF !important;
    border-bottom-color: #007AFF !important;
    font-weight: 600 !important;
}

/* ── Markdown panels ──────────────────────────────────────────── */
.panel-md { font-size: 0.88rem !important; line-height: 1.75 !important; letter-spacing: -0.005em !important; }
.panel-md h1, .panel-md h2 { font-size: 1rem !important; font-weight: 700 !important; margin: 1rem 0 0.3rem !important; }
.panel-md h3 { font-size: 0.9rem !important; font-weight: 600 !important; margin: 0.9rem 0 0.25rem !important; }
.panel-md p  { margin: 0.35rem 0 !important; }
.panel-md table { font-size: 0.82rem !important; border-collapse: collapse !important; width: 100% !important; }
.panel-md td, .panel-md th { padding: 0.4rem 0.6rem !important; border-bottom: 0.5px solid #E5E5EA !important; }
.panel-md th { font-weight: 600 !important; color: #8E8E93 !important; font-size: 0.72rem !important; text-transform: uppercase !important; letter-spacing: 0.05em !important; }
.panel-md blockquote {
    border-left: 3px solid #007AFF; margin: 0.5rem 0;
    padding: 0.3rem 0.75rem; color: #8E8E93; font-size: 0.84rem;
    background: rgba(0,122,255,0.04); border-radius: 0 8px 8px 0;
}
.panel-md code {
    background: #F2F2F7; padding: 2px 6px;
    border-radius: 5px; font-size: 0.83rem;
    color: #FF3B30; font-family: "SF Mono", "Fira Code", monospace;
}

/* ── Calibration section ──────────────────────────────────────── */
.cal-question {
    background: #F2F2F7; border-radius: 12px;
    padding: 1rem 1.1rem; margin-bottom: 0.75rem;
    border-left: 3px solid #007AFF;
}
.cal-question label { font-size: 0.9rem !important; font-weight: 500 !important; color: #1C1C1E !important; }
.cal-prediction { font-size: 0.76rem; color: #8E8E93; margin-top: 0.35rem; font-style: italic; }
/* MCQ radio buttons */
.cal-radio { margin-top: 0.5rem !important; }
.cal-radio .wrap { gap: 0.4rem !important; flex-direction: column !important; }
.cal-radio label span {
    font-size: 0.85rem !important; padding: 0.45rem 0.85rem !important;
    border-radius: 20px !important; border: 1.5px solid #C7C7CC !important;
    cursor: pointer !important; transition: background 0.15s, border-color 0.15s !important;
    display: inline-block !important;
}
.cal-radio label:has(input:checked) span {
    background: #007AFF !important; color: #fff !important;
    border-color: #007AFF !important;
}
.cal-radio label span:hover { border-color: #007AFF !important; }
.cal-score {
    background: rgba(48,209,88,0.08); border: 1px solid rgba(48,209,88,0.30);
    border-radius: 12px; padding: 1rem; margin-top: 0.5rem;
    font-size: 0.86rem; color: #1C1C1E;
}

/* ── BPHS rule pills ──────────────────────────────────────────── */
.rule-pill {
    background: #F2F2F7; border-radius: 10px;
    padding: 0.6rem 0.9rem; margin: 0.3rem 0;
    font-size: 0.81rem; line-height: 1.55; color: #3A3A3C;
    display: block; border: 0.5px solid rgba(60,60,67,0.10);
}
.rule-pill-label {
    font-size: 0.6rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: #8E8E93; display: block; margin-bottom: 0.18rem;
}

/* ── Score table ──────────────────────────────────────────────── */
.score-tbl { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }
.score-tbl table { font-size: 0.83rem !important; min-width: 360px !important; }
.score-tbl th {
    font-size: 0.68rem !important; font-weight: 700 !important;
    text-transform: uppercase !important; letter-spacing: 0.06em !important;
    color: #8E8E93 !important; padding: 0.4rem 0.5rem !important;
}
.score-tbl td { padding: 0.45rem 0.5rem !important; font-size: 0.83rem !important; }

/* ── Accordion — iOS grouped list style ──────────────────────── */
.accordion, details {
    background: #fff !important; border-radius: 16px !important;
    border: none !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 20px rgba(0,0,0,0.04) !important;
    overflow: hidden !important;
}
.accordion > .label-wrap, details > summary {
    font-size: 0.95rem !important; font-weight: 600 !important;
    padding: 1rem 1.2rem !important; min-height: 52px !important;
    color: #1C1C1E !important; letter-spacing: -0.01em !important;
    border-bottom: 0.5px solid rgba(60,60,67,0.10) !important;
    display: flex !important; align-items: center !important;
}
/* Phase 2 accordion open label */
.accordion .icon { color: #007AFF !important; }

/* ── Dropdown / select ────────────────────────────────────────── */
.gr-dropdown > div, [data-testid="dropdown"] > div {
    border-radius: 10px !important;
    border: 1px solid rgba(60,60,67,0.13) !important;
    background: #F2F2F7 !important;
}

/* ── Spacing helpers ──────────────────────────────────────────── */
.gap-sm { height: 0.75rem; }
.gap-md { height: 1.25rem; }
.gap-lg { height: 2rem; }

/* ── Examples section ─────────────────────────────────────────── */
.examples-table { font-size: 0.82rem !important; border-radius: 12px !important; overflow: hidden !important; }
.examples-table td, .examples-table th { padding: 0.5rem 0.7rem !important; font-size: 0.8rem !important; }

/* ── Mobile-specific overrides ────────────────────────────────── */
@media (max-width: 520px) {
    .hdr { padding: 1.5rem 1rem 0.7rem; }
    .hdr h1 { font-size: 1.6rem; }
    .card { border-radius: 14px !important; }
    .p3-card { border-radius: 16px !important; }
    .btn-primary { font-size: 0.9rem !important; min-height: 48px !important; }

    /* Stack rows vertically on small screens */
    .gr-row { flex-direction: column !important; }
    .gr-row > * { min-width: 100% !important; width: 100% !important; }

    /* Full-width chat, shorter on mobile */
    .chatbot { height: 300px !important; }
    .panel-md table { font-size: 0.76rem !important; }

    /* Bigger touch targets for number inputs */
    input[type=number] { min-height: 48px !important; font-size: 1rem !important; text-align: center !important; }

    /* Domain chips smaller on mobile */
    .domain-chips label { font-size: 0.75rem !important; padding: 0.25rem 0.7rem !important; }

    /* Meta row stack */
    .p3-meta { flex-direction: row; flex-wrap: wrap; gap: 0.35rem; }
}

/* ── Phase 3 wrapper card (pure HTML div, not Gradio column) ─── */
.p3-card {
    background: #fff;
    border-radius: 20px;
    padding: 1.1rem 1rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 20px rgba(0,0,0,0.04);
    margin-bottom: 0;
}
@media (min-width: 768px) {
    .p3-card { padding: 1.4rem 1.4rem 1.2rem; }
}

/* Phase 3 top header row */
.p3-header {
    display: flex; align-items: center;
    justify-content: space-between;
    margin-bottom: 0.85rem;
}
.p3-title {
    font-size: 1.05rem; font-weight: 700;
    color: #1C1C1E; letter-spacing: -0.025em;
}
.p3-subtitle {
    font-size: 0.72rem; color: #8E8E93;
    font-weight: 400; letter-spacing: -0.005em;
    margin-top: 0.1rem;
}

/* Domain chips — horizontal scrolling pill row */
.domain-chips > .wrap, .domain-chips .gradio-radio > div {
    display: flex !important; flex-direction: row !important;
    flex-wrap: nowrap !important; overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
    scrollbar-width: none !important;
    gap: 0.35rem !important; padding: 0 0 0.15rem !important;
    align-items: center !important;
}
.domain-chips > .wrap::-webkit-scrollbar,
.domain-chips .gradio-radio > div::-webkit-scrollbar { display: none !important; }
/* Each chip label */
.domain-chips label {
    background: #F2F2F7 !important; border-radius: 980px !important;
    padding: 0.28rem 0.85rem !important; font-size: 0.79rem !important;
    font-weight: 500 !important; cursor: pointer !important;
    border: 1.5px solid transparent !important;
    transition: background 0.15s, color 0.15s, border-color 0.15s !important;
    color: #3A3A3C !important; white-space: nowrap !important;
    flex-shrink: 0 !important; min-height: 30px !important;
    display: inline-flex !important; align-items: center !important;
    letter-spacing: -0.005em !important;
}
.domain-chips label:has(input:checked) {
    background: #007AFF !important; color: #fff !important;
    border-color: #007AFF !important;
}
.domain-chips input[type=radio] {
    position: absolute !important; opacity: 0 !important;
    pointer-events: none !important; width: 0 !important; height: 0 !important;
}
/* Hide Gradio label above chips */
.domain-chips > .block > label,
.domain-chips > label { display: none !important; }

/* Input bar */
.input-bar {
    margin-top: 0.7rem;
    border-top: 0.5px solid rgba(60,60,67,0.10);
    padding-top: 0.7rem;
}
.input-row {
    display: flex !important; align-items: flex-end !important;
    gap: 0.45rem !important; flex-wrap: nowrap !important;
}
.input-row > div { margin: 0 !important; }

/* Query textbox — iOS Messages pill style */
.query-box textarea {
    border-radius: 22px !important;
    border: 1.5px solid #E5E5EA !important;
    background: #F2F2F7 !important;
    font-size: 0.95rem !important;
    resize: none !important;
    min-height: 44px !important;
    max-height: 110px !important;
    padding: 0.6rem 1rem !important;
    line-height: 1.5 !important;
    transition: border-color 0.18s, box-shadow 0.18s, background 0.18s !important;
}
.query-box textarea:focus {
    background: #fff !important;
    border-color: #007AFF !important;
    box-shadow: 0 0 0 3px rgba(0,122,255,0.14) !important;
}

/* Circular send button */
.send-btn {
    width: 44px !important; height: 44px !important;
    min-width: 44px !important; min-height: 44px !important;
    border-radius: 50% !important;
    padding: 0 !important; margin: 0 !important;
    font-size: 1.25rem !important; line-height: 1 !important;
    background: #007AFF !important; color: #fff !important;
    border: none !important; flex-shrink: 0 !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 10px rgba(0,122,255,0.30) !important;
    transition: background 0.15s, transform 0.12s, box-shadow 0.15s !important;
}
.send-btn:hover { background: #0A84FF !important; box-shadow: 0 4px 14px rgba(0,122,255,0.38) !important; }
.send-btn:active { transform: scale(0.92) !important; }

/* Status row — inline, below input bar */
.p3-meta {
    display: flex; align-items: center; justify-content: space-between;
    margin-top: 0.45rem; min-height: 28px;
}

/* Clear button — small ghost pill, right side of meta row */
.clear-btn {
    min-height: 30px !important; height: 30px !important;
    font-size: 0.77rem !important;
    padding: 0 0.85rem !important;
    background: transparent !important;
    color: #8E8E93 !important;
    border: 1px solid rgba(60,60,67,0.15) !important;
    border-radius: 980px !important;
    transition: all 0.15s !important;
}
.clear-btn:hover {
    background: #F2F2F7 !important; color: #3A3A3C !important;
    border-color: rgba(60,60,67,0.25) !important;
}

/* Rules section */
.rules-header {
    display: flex; align-items: center; gap: 0.4rem;
    margin: 1rem 0 0.5rem;
}
.rules-header-text {
    font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.075em; color: #8E8E93;
}
.rules-dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: #007AFF; flex-shrink: 0;
}

/* Rules placeholder */
.rules-placeholder {
    color: #C7C7CC; font-size: 0.82rem; margin: 0;
    font-style: italic; text-align: center;
    padding: 0.5rem 0;
}

/* ── Animated send button pulse ──────────────────────────────── */
.send-btn { animation: glow-pulse 2.8s ease-in-out infinite; }

/* ── Score bar shimmer ────────────────────────────────────────── */
.score-tbl tr:last-child td {
    background: linear-gradient(90deg, #f0f4ff 0%, #d6e4ff 50%, #f0f4ff 100%);
    background-size: 200% auto;
    animation: shimmer-bar 3s linear infinite;
}

/* ── Planet symbol in sec labels ─────────────────────────────── */
.planet-sec {
    font-size: 0.7rem; color: #007AFF;
    margin-right: 0.3rem; vertical-align: middle;
    animation: float-symbol 4s ease-in-out infinite;
    display: inline-block;
}

/* ── Hide Gradio chrome ───────────────────────────────────────── */
footer, .built-with, #footer, .svelte-1ipelgc { display: none !important; }
.gr-prose p:last-child { margin-bottom: 0; }
"""

# ─────────────────────────────────────────────────────────────────────────────
# Async helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=180)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


_solver = None

def get_solver():
    global _solver
    if _solver is None:
        from vedic_astro.agents.solver_agent import SolverAgent
        _solver = SolverAgent()
    return _solver


# ─────────────────────────────────────────────────────────────────────────────
# Domain detection
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_KW = {
    "career":       ["career", "job", "work", "profession", "business", "promotion"],
    "marriage":     ["marriage", "spouse", "partner", "relationship", "wedding", "love", "husband", "wife"],
    "wealth":       ["wealth", "money", "finance", "rich", "income", "property"],
    "health":       ["health", "disease", "illness", "surgery", "longevity", "body"],
    "spirituality": ["spiritual", "meditation", "dharma", "moksha", "karma"],
    "children":     ["child", "children", "baby", "son", "daughter", "pregnancy"],
    "travel":       ["travel", "foreign", "abroad", "relocate", "journey"],
    "family":       ["family", "mother", "father", "sibling", "home"],
}

def auto_domain(query: str, explicit: str) -> str:
    if explicit and explicit != "auto":
        return explicit
    ql = query.lower()
    for domain, kws in _DOMAIN_KW.items():
        if any(k in ql for k in kws):
            return domain
    return "general"


_EMPTY_DF = pd.DataFrame(columns=["Layer", "Weight %", "Score", "Contribution", "Rating"])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Compute Chart
# ─────────────────────────────────────────────────────────────────────────────

def handle_compute_chart(year, month, day, hour, minute, place, lat_str, lon_str, query_date_str):
    """Phase 1 — compute all chart data, no LLM."""
    from vedic_astro.agents.pipeline import BirthData, ReadingRequest

    lat = float(lat_str) if str(lat_str).strip() else None
    lon = float(lon_str) if str(lon_str).strip() else None
    birth = BirthData(
        year=int(year), month=int(month), day=int(day),
        hour=int(hour), minute=int(minute),
        place=str(place).strip(), lat=lat, lon=lon,
    )
    try:
        qdate = date.fromisoformat(str(query_date_str).strip()) if str(query_date_str).strip() else None
    except ValueError:
        qdate = None

    try:
        request = ReadingRequest(birth=birth, query="", domain="general", query_date=qdate)
        chart_state = _run_async(get_solver()._runner.compute_chart(request))
    except Exception as exc:
        logger.exception("Phase 1 error")
        return (
            None,                                    # chart_state
            f"❌ Error computing chart: {exc}",      # status
            _render_chart_md(None),                  # chart panel
            _render_dasha_md(None),                  # dasha panel
            _render_transit_md(None),                # transit panel
            _render_yogas_md(None),                  # yoga panel
            _render_shadbala_md(None),               # shadbala panel
            _render_vargas_md(None),                 # vargas panel
            _EMPTY_DF.copy(),                        # score df
        )

    status = (
        f"✓ Chart computed · "
        f"Lagna: **{_get_lagna(chart_state)}** · "
        f"Dasha: **{_get_dasha(chart_state)}** · "
        f"Proceed to Calibrate →"
    )
    return (
        chart_state,
        status,
        _render_chart_md(chart_state),
        _render_dasha_md(chart_state),
        _render_transit_md(chart_state),
        _render_yogas_md(chart_state),
        _render_shadbala_md(chart_state),
        _render_vargas_md(chart_state),
        _render_score_df(chart_state),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Calibration
# ─────────────────────────────────────────────────────────────────────────────

def handle_generate_calibration(chart_state):
    """Generate 10 calibration questions from the computed chart."""
    if chart_state is None:
        empty_radio = [gr.update(choices=["Not applicable / Skip"], value=None)] * 10
        return (
            None,
            "⚠ Please compute your chart first (Phase 1).",
            *[""] * 10,
            *[""] * 10,
            *empty_radio,
        )

    from vedic_astro.agents.calibration import generate_questions
    questions = generate_questions(chart_state, n=10)

    q_texts     = [q.text            for q in questions]
    q_predicted = [q.predicted_timing for q in questions]
    q_options   = [q.options          for q in questions]

    # Pad to exactly 10
    while len(q_texts) < 10:
        q_texts.append("")
        q_predicted.append("")
        q_options.append(["Not applicable / Skip"])

    radio_updates = [
        gr.update(choices=opts, value=None)
        for opts in q_options[:10]
    ]

    return (
        questions,
        "Questions generated — select the option that best matches your experience.",
        *q_texts[:10],
        *q_predicted[:10],
        *radio_updates,
    )


def handle_score_calibration(chart_state, questions, *answers):
    """Score calibration answers and return adjusted weights."""
    if not questions:
        return (None, "⚠ Generate questions first.")

    from vedic_astro.agents.calibration import score_answers
    answer_list = []
    for q, ans in zip(questions, answers):
        answer_list.append({
            "id": q.id,
            "answer": ans if ans and str(ans).strip() else None,
            "skipped": not (ans and str(ans).strip()),
        })

    result = score_answers(questions, answer_list, state=chart_state)
    return (result, result.summary_markdown())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Predict
# ─────────────────────────────────────────────────────────────────────────────

def handle_predict(
    chart_state, calibration_result,
    query, domain_sel,
    chat_history, session_state,
):
    if chart_state is None:
        return (chat_history, session_state, "⚠ Compute your chart first (Phase 1).", "", "")
    if not str(query).strip():
        return (chat_history, session_state, "", "", "")

    domain = auto_domain(str(query), domain_sel)
    cal_weights = calibration_result.weights if calibration_result else None

    try:
        result = _run_async(
            get_solver().predict(chart_state, str(query), domain, cal_weights)
        )
        reading = result.reading
    except Exception as exc:
        logger.exception("Phase 3 error")
        err = f"Error: {exc}"
        return (
            chat_history + [{"role": "user", "content": str(query)}, {"role": "assistant", "content": err}],
            session_state, err, "", "",
        )

    response_md = reading.to_markdown() if hasattr(reading, "to_markdown") else str(reading.final_reading)
    new_history = chat_history + [
        {"role": "user",      "content": str(query)},
        {"role": "assistant", "content": response_md},
    ]
    score_val = reading.score.final_score if reading.score else 0
    interp    = reading.score.interpretation.replace("_", " ").title() if reading.score else ""
    cal_note  = f" · Calibrated weights" if cal_weights else ""
    status    = f"Domain · **{domain}** &nbsp;·&nbsp; Score · **{score_val:.2f}** · {interp}{cal_note}"
    bphs_html = _bphs_rule_html(reading)

    return (new_history, session_state, status, bphs_html, _bphs_rules_md(reading))


# ─────────────────────────────────────────────────────────────────────────────
# Chart renderers
# ─────────────────────────────────────────────────────────────────────────────

def _get_lagna(state) -> str:
    try:
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        return RASHI_NAMES[state.chart.lagna_sign - 1]
    except Exception:
        return "—"

def _get_dasha(state) -> str:
    try:
        w = state.dasha_window
        maha  = w.mahadasha.lord.value
        antar = w.antardasha.lord.value if w.antardasha else ""
        return f"{maha}/{antar}" if antar else maha
    except Exception:
        return "—"

def _render_chart_md(state) -> str:
    if state is None or state.chart is None:
        return "*Compute chart to see natal analysis.*"
    try:
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        chart = state.chart
        lagna = RASHI_NAMES[chart.lagna_sign - 1]
        lines = [f"**Lagna:** {lagna}\n", "| Planet | Sign | House | Dignity | Retro |",
                 "|--------|------|-------|---------|-------|"]
        for p, pos in chart.planets.items():
            sign = RASHI_NAMES[pos.sign_number - 1]
            dig  = pos.dignity.value if hasattr(pos.dignity, "value") else str(pos.dignity)
            retro = "R" if pos.is_retrograde else "—"
            lines.append(f"| {p.value.title()} | {sign} | {pos.house} | {dig} | {retro} |")
        return "\n".join(lines)
    except Exception as exc:
        return f"*Chart render error: {exc}*"

def _render_dasha_md(state) -> str:
    if state is None or state.dasha_window is None:
        return "*Compute chart to see dasha timing.*"
    try:
        w = state.dasha_window
        m = w.mahadasha
        a = w.antardasha
        lines = [
            f"**Mahadasha:** {m.lord.value.title()} · {m.start} → {m.end}",
            f"**Elapsed:** {m.elapsed_fraction(w.query_date)*100:.1f}%",
        ]
        if a:
            lines += [
                f"\n**Antardasha:** {a.lord.value.title()} · {a.start} → {a.end}",
                f"**Elapsed:** {a.elapsed_fraction(w.query_date)*100:.1f}%",
            ]
        return "\n\n".join(lines)
    except Exception as exc:
        return f"*Dasha render error: {exc}*"

def _render_transit_md(state) -> str:
    if state is None or state.transit_overlay is None:
        return "*Compute chart to see transit overlay.*"
    try:
        ov = state.transit_overlay
        lines = [f"**Sade Sati:** {'Active — ' + ov.sadesati_phase if ov.sadesati_active else 'Not active'}\n",
                 "| Planet | House from Moon | Strength | Favourable |",
                 "|--------|----------------|----------|------------|"]
        for planet, g in ov.gochara.items():
            fav = "✓" if g.is_favorable else "✗"
            lines.append(f"| {planet.value.title()} | {g.house_from_moon} | {g.composite_strength:.2f} | {fav} |")
        return "\n".join(lines)
    except Exception as exc:
        return f"*Transit render error: {exc}*"

def _render_yogas_md(state) -> str:
    if state is None or state.yoga_bundle is None:
        return "*Compute chart to see yogas.*"
    try:
        bundle = state.yoga_bundle
        lines = []
        if bundle.active_yogas:
            lines.append("**Active Yogas:**")
            for y in bundle.active_yogas:
                lines.append(f"- **{y.name}** (strength {y.strength:.2f})")
        if bundle.active_doshas:
            lines.append("\n**Active Doshas:**")
            for d in bundle.active_doshas:
                lines.append(f"- **{d.name}** (severity {d.severity:.2f})")
        return "\n".join(lines) or "*No yogas/doshas detected.*"
    except Exception as exc:
        return f"*Yoga render error: {exc}*"

def _render_shadbala_md(state) -> str:
    if state is None or not getattr(state, "shadbala", None):
        return "*Compute chart to see Shadbala.*"
    try:
        from vedic_astro.learning.shadbala import shadbala_summary
        return "**Shadbala — Six-fold Planetary Strength**\n\n" + shadbala_summary(state.shadbala)
    except Exception as exc:
        return f"*Shadbala render error: {exc}*"

def _render_vargas_md(state) -> str:
    if state is None or not state.varga_charts:
        return "*Compute chart to see divisional charts.*"
    try:
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        lines = ["**Divisional Charts (Vargas)**\n"]
        for div, vc in sorted(state.varga_charts.items()):
            lagna = RASHI_NAMES[vc.lagna_sign - 1]
            planets_str = ", ".join(
                f"{p.value.title()}:{RASHI_NAMES[pos.sign_number-1][:3]}"
                for p, pos in list(vc.planets.items())[:5]
            )
            lines.append(f"**D{div}** — Lagna: {lagna} · {planets_str}…")
        return "\n\n".join(lines)
    except Exception as exc:
        return f"*Vargas render error: {exc}*"

def _render_score_df(state) -> pd.DataFrame:
    if state is None or state.score is None:
        return _EMPTY_DF.copy()
    try:
        s = state.score
        w = getattr(s, "weights_used", None) or {"natal": 0.35, "dasha": 0.30, "transit": 0.25, "yoga": 0.10}
        wn = w.get("natal",   0.35)
        wd = w.get("dasha",   0.30)
        wt = w.get("transit", 0.25)
        wy = w.get("yoga",    0.10)
        rows = [
            {"Layer": "Natal (D1+D9 blend)",
             "Weight %": f"{wn*100:.0f}%",
             "Score": f"{s.natal_strength:.3f}",
             "Contribution": f"{wn*s.natal_strength:+.3f}",
             "Rating": _score_label(s.natal_strength)},
        ]
        # Sub-rows for D1 and D9 if available
        if getattr(s, "d1_strength", 0) or getattr(s, "navamsha_strength", 0):
            rows.append({
                "Layer": "  └ D1 Natal chart (70%)",
                "Weight %": "—",
                "Score": f"{getattr(s, 'd1_strength', s.natal_strength):.3f}",
                "Contribution": "—",
                "Rating": _score_label(getattr(s, "d1_strength", s.natal_strength)),
            })
            rows.append({
                "Layer": "  └ D9 Navamsha (30%)",
                "Weight %": "—",
                "Score": f"{getattr(s, 'navamsha_strength', 0):.3f}",
                "Contribution": "—",
                "Rating": _score_label(getattr(s, "navamsha_strength", 0)),
            })
        rows += [
            {"Layer": "Dasha Activation",
             "Weight %": f"{wd*100:.0f}%",
             "Score": f"{s.dasha_activation:.3f}",
             "Contribution": f"{wd*s.dasha_activation:+.3f}",
             "Rating": _score_label(s.dasha_activation)},
            {"Layer": "Transit Trigger",
             "Weight %": f"{wt*100:.0f}%",
             "Score": f"{s.transit_trigger:.3f}",
             "Contribution": f"{wt*s.transit_trigger:+.3f}",
             "Rating": _score_label(s.transit_trigger)},
            {"Layer": "Yoga Support",
             "Weight %": f"{wy*100:.0f}%",
             "Score": f"{s.yoga_support:.3f}",
             "Contribution": f"{wy*s.yoga_support:+.3f}",
             "Rating": _score_label(s.yoga_support)},
            {"Layer": "Dosha Penalty",
             "Weight %": "−20% of penalty",
             "Score": f"{s.dosha_penalty:.3f}",
             "Contribution": f"{-0.20*s.dosha_penalty:+.3f}",
             "Rating": ""},
            {"Layer": "── COMPOSITE ──",
             "Weight %": "",
             "Score": f"{s.final_score:.3f}",
             "Contribution": "",
             "Rating": s.interpretation.replace("_", " ").title()},
        ]
        return pd.DataFrame(rows)
    except Exception:
        return _EMPTY_DF.copy()

def _score_label(v: float) -> str:
    if v >= 0.75: return "Strong"
    if v >= 0.50: return "Moderate"
    return "Weak"

def _bphs_rule_html(reading) -> str:
    rules = getattr(reading, "retrieved_rules", {})
    flat = [(agent, rule) for agent, rl in rules.items() for rule in rl[:2]]
    if not flat:
        return '<p style="color:#aeaeb2;font-size:0.82rem;margin:0">No rules retrieved.</p>'
    html = ""
    for agent, rule in flat[:8]:
        html += (f'<span class="rule-pill"><span class="rule-pill-label">{agent.title()}</span>{rule}</span>')
    return html

def _bphs_rules_md(reading) -> str:
    rules = getattr(reading, "retrieved_rules", {})
    if not rules: return "*—*"
    lines = []
    for agent, rule_list in rules.items():
        if rule_list:
            lines.append(f"**{agent.title()}**")
            for r in rule_list[:4]: lines.append(f"> {r}\n")
    return "\n".join(lines) or "*—*"

def handle_clear(session_state):
    return ([], session_state, "", "", "")


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:

    with gr.Blocks(title="Vedic Astrology AI", css=CSS) as demo:

        # State
        session_state      = gr.State({})
        chart_state        = gr.State(None)   # PipelineState after Phase 1
        cal_questions      = gr.State(None)   # list[CalibrationQuestion]
        calibration_result = gr.State(None)   # CalibrationResult

        # ── Header ────────────────────────────────────────────────────────
        gr.HTML("""
        <div class="hdr">
          <!-- star field -->
          <span class="hdr-star s1"></span><span class="hdr-star s2"></span>
          <span class="hdr-star s3"></span><span class="hdr-star s4"></span>
          <span class="hdr-star s5"></span><span class="hdr-star s6"></span>
          <span class="hdr-star s7"></span><span class="hdr-star s8"></span>
          <span class="hdr-star s9"></span><span class="hdr-star s10"></span>
          <span class="hdr-star s11"></span><span class="hdr-star s12"></span>

          <!-- rotating zodiac ring -->
          <div class="zodiac-ring-wrap">
            <div class="zodiac-ring">
              <span class="z0">♈</span><span class="z1">♉</span>
              <span class="z2">♊</span><span class="z3">♋</span>
              <span class="z4">♌</span><span class="z5">♍</span>
              <span class="z6">♎</span><span class="z7">♏</span>
              <span class="z8">♐</span><span class="z9">♑</span>
              <span class="z10">♒</span><span class="z11">♓</span>
            </div>
            <span class="zodiac-center">☉</span>
          </div>

          <h1>Vedic Astrology AI</h1>
          <p>Classical Parashari · Swiss Ephemeris · D1–D60 · Shadbala · BPHS rules · Multi-agent AI</p>
        </div>
        <div class="stepper">
          <div class="step active" id="step1"><span class="planet-glyph">☉</span> Chart</div>
          <div class="step" id="step2"><span class="planet-glyph">♎</span> Calibrate</div>
          <div class="step" id="step3"><span class="planet-glyph">☿</span> Ask</div>
        </div>
        """)

        # ══════════════════════════════════════════════════════════════════
        # PHASE 1 — Birth Form + Chart Display
        # ══════════════════════════════════════════════════════════════════
        with gr.Row(equal_height=False):

            # Left: birth form
            with gr.Column(scale=1, min_width=240, elem_classes="card"):
                gr.HTML('<span class="sec-label"><span class="planet-sec">♋</span>Date of birth</span>')
                with gr.Row():
                    day   = gr.Number(label="Day",   value=15,   precision=0, minimum=1,   maximum=31,   scale=1)
                    month = gr.Number(label="Month", value=6,    precision=0, minimum=1,   maximum=12,   scale=1)
                    year  = gr.Number(label="Year",  value=1990, precision=0, minimum=1800, maximum=2100, scale=2)

                gr.HTML('<span class="sec-label"><span class="planet-sec">☽</span>Time of birth</span>')
                with gr.Row():
                    hour   = gr.Number(label="Hour (0–23)", value=14, precision=0, minimum=0, maximum=23, scale=1)
                    minute = gr.Number(label="Minute",      value=30, precision=0, minimum=0, maximum=59, scale=1)

                gr.HTML('<span class="sec-label"><span class="planet-sec">♁</span>Place of birth</span>')
                place = gr.Dropdown(
                    choices=CITIES_SORTED[:20], value=None,
                    allow_custom_value=True, label="City, Country",
                    info="Type to search — any city worldwide",
                )
                with gr.Row():
                    lat_str = gr.Textbox(label="Latitude",  placeholder="19.076", scale=1)
                    lon_str = gr.Textbox(label="Longitude", placeholder="72.877", scale=1)

                gr.HTML('<span class="sec-label" style="margin-top:1.2rem"><span class="planet-sec">♄</span>Transit date</span>')
                query_date_str = gr.Textbox(label="Date", placeholder="YYYY-MM-DD  (blank = today)", show_label=False)

                gr.HTML('<div style="margin-top:1.2rem"></div>')
                compute_btn = gr.Button("Compute Chart", variant="primary", elem_classes="btn-primary")
                p1_status   = gr.Markdown("", elem_classes="status-line")

            # Right: chart data tabs
            with gr.Column(scale=3, elem_classes="card"):
                gr.HTML('<p class="sec-heading">Chart Data — populated after Phase 1</p>')
                with gr.Tabs():
                    with gr.TabItem("Natal D1"):
                        chart_panel = gr.Markdown("*Compute chart to see natal analysis.*", elem_classes="panel-md")
                    with gr.TabItem("Dasha"):
                        dasha_panel = gr.Markdown("*Compute chart to see dasha timing.*", elem_classes="panel-md")
                    with gr.TabItem("Transits"):
                        transit_panel = gr.Markdown("*Compute chart to see transit overlay.*", elem_classes="panel-md")
                    with gr.TabItem("Yogas"):
                        yoga_panel = gr.Markdown("*Compute chart to see yogas.*", elem_classes="panel-md")
                    with gr.TabItem("Shadbala"):
                        shadbala_panel = gr.Markdown("*Compute chart to see Shadbala.*", elem_classes="panel-md")
                    with gr.TabItem("D1–D60"):
                        vargas_panel = gr.Markdown("*Compute chart to see divisional charts.*", elem_classes="panel-md")
                    with gr.TabItem("Score"):
                        score_df = gr.DataFrame(value=_EMPTY_DF.copy(), interactive=False, elem_classes="score-tbl")

        gr.HTML('<div class="gap-md"></div>')

        # ══════════════════════════════════════════════════════════════════
        # PHASE 2 — Calibration
        # ══════════════════════════════════════════════════════════════════
        with gr.Accordion("♎  Phase 2 — Calibrate Weights (optional)", open=False):
            gr.Markdown(
                "Answer questions about past life events. "
                "Your answers calibrate how much weight each astrological factor gets.\n\n"
                "*Skip questions that don't apply — they default to neutral weight.*"
            )
            gen_cal_btn = gr.Button("Generate Calibration Questions", elem_classes="btn-secondary")
            cal_status  = gr.Markdown("")

            cal_q_labels  = []
            cal_answers   = []
            cal_predicted = []

            for i in range(10):
                with gr.Group(visible=True, elem_classes="cal-question"):
                    q_label = gr.Markdown(f"*Q{i+1} — tap Generate above.*")
                    ans     = gr.Radio(
                        choices=["Not applicable / Skip"],
                        value=None,
                        label="Select your answer",
                        elem_classes="cal-radio",
                    )
                    pred    = gr.Markdown("", elem_classes="cal-prediction")
                    cal_q_labels.append(q_label)
                    cal_answers.append(ans)
                    cal_predicted.append(pred)

            score_cal_btn = gr.Button("Score & Calibrate Weights", elem_classes="btn-primary")
            cal_result_md = gr.Markdown("", elem_classes="cal-score")

        gr.HTML('<div class="gap-md"></div>')

        # ══════════════════════════════════════════════════════════════════
        # PHASE 3 — Ask  (single‑column card, mobile‑first)
        # ══════════════════════════════════════════════════════════════════
        gr.HTML('<div class="p3-card">')   # ← open wrapper card

        # Header: title + tagline
        gr.HTML('''
        <div class="p3-header">
          <div>
            <div class="p3-title"><span style="color:#007AFF">☿</span> Ask your chart</div>
            <div class="p3-subtitle">Powered by multi-agent Vedic AI</div>
          </div>
        </div>
        ''')

        # Domain chips — horizontal scrolling iOS pill selector
        domain_sel = gr.Radio(
            choices=["auto", "career", "marriage", "wealth",
                     "health", "spirituality", "children", "travel", "family"],
            value="auto", label="", show_label=False,
            elem_classes="domain-chips",
        )

        chatbot = gr.Chatbot(
            label="", height=340, type="messages",
            show_copy_button=True, show_label=False,
            elem_classes="chatbot",
            placeholder=(
                "Complete Phase 1 (Compute Chart) first, then ask here.\n\n"
                "e.g. *What does my chart say about career?*"
            ),
        )

        # Input bar — separated by top border, Messages-style
        gr.HTML('<div class="input-bar">')
        with gr.Row(equal_height=True, elem_classes="input-row"):
            query_input = gr.Textbox(
                label="", placeholder="Ask about career, marriage, health…",
                lines=1, scale=5, show_label=False, elem_classes="query-box",
            )
            ask_btn = gr.Button("↑", variant="primary", scale=0,
                                min_width=44, elem_classes="send-btn")
        gr.HTML('</div>')

        # Meta row: status left, clear right
        gr.HTML('<div class="p3-meta">')
        p3_status = gr.Markdown("", elem_classes="status-line")
        clear_btn = gr.Button("Clear", elem_classes="clear-btn", size="sm")
        gr.HTML('</div>')

        # Classical rules
        gr.HTML('''
        <div class="rules-header">
          <span style="font-size:0.78rem;color:#8E8E93;opacity:0.7">☊</span>
          <span class="rules-header-text">Classical rules applied</span>
        </div>
        ''')
        bphs_highlights = gr.HTML(
            '<p class="rules-placeholder">Rules appear after each reading.</p>'
        )

        gr.HTML('</div>')   # ← close wrapper card

        # BPHS full list — collapsible below
        with gr.Accordion("☊  Full BPHS Classical Rules", open=False):
            bphs_panel = gr.Markdown("*—*", elem_classes="panel-md")

        gr.HTML('<div class="gap-md"></div>')

        # ── Examples ──────────────────────────────────────────────────────
        gr.Examples(
            examples=[
                [15, 6,  1990, 14, 30, "Mumbai, India",    "", "", ""],
                [21, 3,  1985,  8,  0, "New Delhi, India", "", "", ""],
                [4,  8,  1994,  1, 50, "Delhi, India",     "", "", ""],
                [5,  11, 1975, 22, 15, "London, UK",       "", "", ""],
                [12, 1,  1988, 10, 20, "Chennai, India",   "", "", ""],
                [7,  4,  1995, 18, 45, "Singapore",        "", "", ""],
            ],
            inputs=[day, month, year, hour, minute, place, lat_str, lon_str, query_date_str],
            label="Example birth details",
            examples_per_page=3,
        )

        # ── Wire events ───────────────────────────────────────────────────

        # Place autocomplete (typing)
        place.input(
            fn=lambda q: gr.Dropdown(choices=search_places(q) if q else CITIES_SORTED[:20]),
            inputs=[place], outputs=[place],
        )
        # Auto-fill lat/lon when a city is selected or changed
        place.change(
            fn=fill_coords,
            inputs=[place], outputs=[lat_str, lon_str],
        )

        # Phase 1
        compute_btn.click(
            fn=handle_compute_chart,
            inputs=[year, month, day, hour, minute, place, lat_str, lon_str, query_date_str],
            outputs=[chart_state, p1_status, chart_panel, dasha_panel, transit_panel,
                     yoga_panel, shadbala_panel, vargas_panel, score_df],
        )

        # Phase 2 — generate questions (also updates Radio choices)
        gen_cal_outputs = [cal_questions, cal_status] + cal_q_labels + cal_predicted + cal_answers
        gen_cal_btn.click(
            fn=handle_generate_calibration,
            inputs=[chart_state],
            outputs=gen_cal_outputs,
        )

        # Phase 2 — score answers (chart_state needed for historical dasha lookup)
        score_cal_btn.click(
            fn=handle_score_calibration,
            inputs=[chart_state, cal_questions] + cal_answers,
            outputs=[calibration_result, cal_result_md],
        )

        # Phase 3
        p3_outputs = [chatbot, session_state, p3_status, bphs_highlights, bphs_panel]
        p3_inputs  = [chart_state, calibration_result, query_input, domain_sel, chatbot, session_state]
        ask_btn.click(fn=handle_predict, inputs=p3_inputs, outputs=p3_outputs)
        query_input.submit(fn=handle_predict, inputs=p3_inputs, outputs=p3_outputs, api_name="ask")
        clear_btn.click(fn=handle_clear, inputs=[session_state], outputs=[chatbot, session_state, p3_status, bphs_highlights, bphs_panel])

    return demo


def create_app() -> gr.Blocks:
    return build_demo()


if __name__ == "__main__":
    demo = build_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
    )
