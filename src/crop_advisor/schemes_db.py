"""Government Schemes Database and Query Module for Crop Advisor.

Provides structured, authentic Central and State government agricultural schemes,
subsidies, crop insurance, and farmer support programs for every Indian state
and recommended crop. Beginner-friendly and self-contained with SQLite.
"""

import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

# Define paths
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "government_schemes.db"

# Crop categories helper to cleanly map 22 dataset crops to agronomic categories
CROP_CATEGORIES = {
    # Cereals / Foodgrains
    "rice": "Cereals",
    "maize": "Cereals",
    # Pulses
    "chickpea": "Pulses",
    "kidneybeans": "Pulses",
    "pigeonpeas": "Pulses",
    "mothbeans": "Pulses",
    "mungbean": "Pulses",
    "blackgram": "Pulses",
    "lentil": "Pulses",
    # Fruits / Horticulture
    "pomegranate": "Fruits",
    "banana": "Fruits",
    "mango": "Fruits",
    "grapes": "Fruits",
    "watermelon": "Fruits",
    "muskmelon": "Fruits",
    "apple": "Fruits",
    "orange": "Fruits",
    "papaya": "Fruits",
    # Plantation Crops
    "coconut": "Plantation",
    "coffee": "Plantation",
    # Commercial / Cash Crops
    "cotton": "Commercial",
    "jute": "Commercial",
}

# Initial seed data for authentic Central and State agricultural schemes
SEED_SCHEMES = [
    # ==================== CENTRAL GOVERNMENT SCHEMES (ALL STATES) ====================
    {
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Insurance for notified crops against specified weather, pest, and disaster losses. Coverage, premium, and enrolment are available only where the State or UT has notified the crop, area, and season.",
        "eligibility": "Farmers growing a crop that is notified for their district or insurance unit in the current season, subject to the State or UT notification.",
        "how_to_apply": "First confirm that your crop, area, and season are notified by the State or UT. Then apply through PMFBY, a CSC, or bank before the seasonal cut-off date.",
        "portal_link": "https://pmfby.gov.in",
    },
    {
        "name": "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Direct annual financial support of Rs. 6,000 delivered in three equal installments of Rs. 2,000 directly into the farmer's Aadhaar-linked bank account.",
        "eligibility": "Eligible landholding farmer families, subject to the scheme's exclusion criteria and verification by the State or UT administration.",
        "how_to_apply": "Self-register on pmkisan.gov.in or visit a local Common Service Centre (CSC) with Aadhaar and land records; complete required eKYC.",
        "portal_link": "https://pmkisan.gov.in",
    },
    {
        "name": "Kisan Credit Card (KCC) Scheme",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Concessional short-term crop loans at an effective interest rate of 4% per annum (7% base minus 3% prompt repayment incentive) up to Rs. 3,00,000.",
        "eligibility": "Individual farmers, tenant farmers, oral lessees, and sharecroppers engaged in crop production.",
        "how_to_apply": "Submit a single-page KCC application form at your local commercial, cooperative, or rural bank branch.",
        "portal_link": "https://myscheme.gov.in/schemes/kcc",
    },
    {
        "name": "National Food Security Mission (NFSM) - Cereals",
        "level": "Central",
        "state": "ALL",
        "crop_category": "Cereals",
        "applicable_crops": "rice,maize",
        "benefits": "50% subsidy on high-yielding certified seeds, micro-nutrients (zinc, boron), bio-fertilizers, and farm machinery (paddy transplanters, cono weeders).",
        "eligibility": "Farmers cultivating rice or maize in identified NFSM districts.",
        "how_to_apply": "Contact the local Block Agriculture Office (BAO) or District Agriculture Officer.",
        "portal_link": "https://nfsm.gov.in",
    },
    {
        "name": "National Food Security Mission (NFSM) - Pulses",
        "level": "Central",
        "state": "ALL",
        "crop_category": "Pulses",
        "applicable_crops": "chickpea,kidneybeans,pigeonpeas,mothbeans,mungbean,blackgram,lentil",
        "benefits": "Free seed mini-kits of high-yielding pulse varieties, Rs. 2,500/ha demonstration assistance, subsidized bio-fertilizers (Rhizobium), and micro-irrigation systems.",
        "eligibility": "Farmers growing pulses across notified pulse-producing districts.",
        "how_to_apply": "Apply through the State Agriculture portal or local Krishi Vigyan Kendra (KVK).",
        "portal_link": "https://nfsm.gov.in",
    },
    {
        "name": "Mission for Integrated Development of Horticulture (MIDH)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "Fruits",
        "applicable_crops": "pomegranate,banana,mango,grapes,watermelon,muskmelon,apple,orange,papaya",
        "benefits": "40% to 50% capital subsidy for establishing new fruit orchards, protected cultivation (polyhouses/shade-nets), micro-irrigation, pack houses, and cold storage.",
        "eligibility": "Individual growers, farmer producer organizations (FPOs), and self-help groups cultivating horticultural crops.",
        "how_to_apply": "Submit proposal via the State Horticulture Department portal or District Horticulture Office.",
        "portal_link": "https://midh.gov.in",
    },
    {
        "name": "Sub-Mission on Agricultural Mechanization (SMAM)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "40% to 50% direct subsidy for purchasing tractors, power tillers, rotavators, seed drills, and harvesting equipment. Small, marginal, and women farmers receive higher subsidies.",
        "eligibility": "All landholding farmers. Priority given to small/marginal farmers and SC/ST categories.",
        "how_to_apply": "Register online at the Central DBT portal in Agricultural Mechanization (agrimachinery.nic.in).",
        "portal_link": "https://agrimachinery.nic.in",
    },
    {
        "name": "PM-KUSUM (Solar Agriculture Pumps)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Up to 60% subsidy (30% Central + 30% State) for installing standalone solar irrigation pump sets (3 HP to 10 HP) and solarizing existing grid pumps.",
        "eligibility": "Individual farmers and farmer groups with agricultural land requiring irrigation.",
        "how_to_apply": "Apply through your State Renewable Energy Agency or State DISCOM portal.",
        "portal_link": "https://pmkusum.mnre.gov.in",
    },
    {
        "name": "Paramparagat Krishi Vikas Yojana (PKVY - Organic Farming)",
        "level": "Central",
        "state": "ALL",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Financial assistance of Rs. 50,000 per hectare over 3 years for organic conversion, vermicompost inputs, botanical extracts, and PGS certification.",
        "eligibility": "Farmers willing to form 20-hectare clusters to practice certified chemical-free farming.",
        "how_to_apply": "Contact the local Block Agriculture Technology Management Agency (ATMA) office.",
        "portal_link": "https://pgsindia-ncof.gov.in",
    },
    {
        "name": "Commercial & Cash Crops Development Mission",
        "level": "Central",
        "state": "ALL",
        "crop_category": "Commercial",
        "applicable_crops": "cotton,jute,coffee,coconut",
        "benefits": "High-density planting system subsidies, distribution of pheromone traps for pest management, subsidized bio-pesticides, and moisture testing meters.",
        "eligibility": "Commercial crop growers in recognized agro-climatic zones.",
        "how_to_apply": "Contact the respective Commodity Board (Cotton Corporation / Jute Board / Coconut Development Board).",
        "portal_link": "https://cotcorp.org.in",
    },

    # ==================== TELANGANA STATE SCHEMES ====================
    {
        "name": "Rythu Bharosa / Rythu Bandhu Scheme",
        "level": "State",
        "state": "Telangana",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Direct investment support of Rs. 5,000 to Rs. 7,500 per acre per season to support purchase of seeds, fertilizers, pesticides, and field labor.",
        "eligibility": "Pattadar passbook holders and eligible tenant farmers cultivating land in Telangana.",
        "how_to_apply": "Enrolled through the Agriculture Extension Officer (AEO) or Rythu Bandhu portal using Pattadar passbook and Aadhaar.",
        "portal_link": "https://rythubandhu.telangana.gov.in",
    },
    {
        "name": "Rythu Bima (Telangana Farmer Group Life Insurance)",
        "level": "State",
        "state": "Telangana",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Rs. 5,00,000 completely free life insurance cover to the nominee in case of death of the enrolled farmer. 100% premium is borne by the Telangana government.",
        "eligibility": "All landholding farmers of Telangana aged 18 to 59 years holding a valid Pattadar passbook.",
        "how_to_apply": "Automatic enrollment through the local Agriculture Extension Officer (AEO).",
        "portal_link": "https://rythubima.telangana.gov.in",
    },
    {
        "name": "Telangana Micro Irrigation Project (T-MIP)",
        "level": "State",
        "state": "Telangana",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Subsidized drip and sprinkler irrigation: 100% subsidy for SC/ST farmers, 90% for small/marginal farmers, and 80% for other farmers (up to 5 acres).",
        "eligibility": "All resident farmers of Telangana with cultivable land and an available water source.",
        "how_to_apply": "Register online at the T-MIP portal or contact the District Horticulture Officer.",
        "portal_link": "https://horticulturedept.telangana.gov.in",
    },

    # ==================== ANDHRA PRADESH STATE SCHEMES ====================
    {
        "name": "YSR Rythu Bharosa",
        "level": "State",
        "state": "Andhra Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Financial assistance of Rs. 13,500 per year per farmer family (including PM-KISAN share) for crop input support in three seasonal installments.",
        "eligibility": "Land-owning farmers as well as eligible tenant farmers and RoFR forest cultivators in Andhra Pradesh.",
        "how_to_apply": "Register at the nearest Rythu Bharosa Kendra (RBK) or Grama Ward Sachivalayam.",
        "portal_link": "https://ysrrythubharosa.ap.gov.in",
    },
    {
        "name": "Dr. YSR Free Crop Insurance Scheme",
        "level": "State",
        "state": "Andhra Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Complete waiver of crop insurance premium. The Andhra Pradesh government pays 100% of the farmer's premium share for notified seasonal crops.",
        "eligibility": "Farmers registered on the e-Panta crop booking system for the current season.",
        "how_to_apply": "Ensure e-Panta crop booking verification is completed through the local Village Agriculture Assistant at your RBK.",
        "portal_link": "https://karshak.ap.gov.in",
    },
    {
        "name": "Andhra Pradesh Micro Irrigation Project (APMIP)",
        "level": "State",
        "state": "Andhra Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "90% subsidy for small and marginal farmers on drip and sprinkler irrigation installations; 70% for other farmers.",
        "eligibility": "All resident farmers in AP with assured water source and agricultural land.",
        "how_to_apply": "Apply through your local Rythu Bharosa Kendra (RBK) or APMIP portal.",
        "portal_link": "https://apmip.ap.gov.in",
    },

    # ==================== MAHARASHTRA STATE SCHEMES ====================
    {
        "name": "Namo Shetkari Mahasanman Nidhi Yojana",
        "level": "State",
        "state": "Maharashtra",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Additional financial assistance of Rs. 6,000 per year directly to PM-KISAN beneficiaries, ensuring total annual income support of Rs. 12,000.",
        "eligibility": "All farmers in Maharashtra who are approved beneficiaries of PM-KISAN.",
        "how_to_apply": "Automatic direct credit for verified PM-KISAN beneficiary bank accounts.",
        "portal_link": "https://mahadbt.maharashtra.gov.in",
    },
    {
        "name": "MahaDBT Farmer Micro-Irrigation & Farm Pond Scheme",
        "level": "State",
        "state": "Maharashtra",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "55% subsidy for small/marginal farmers and 45% for other farmers on drip/sprinkler sets, plus up to Rs. 75,000 grant for farm pond construction.",
        "eligibility": "Farmers holding 7/12 extract and 8-A land records in Maharashtra.",
        "how_to_apply": "Apply online at MahaDBT Farmer Portal (mahadbt.maharashtra.gov.in).",
        "portal_link": "https://mahadbt.maharashtra.gov.in",
    },
    {
        "name": "Gopinath Munde Shetkari Apghat Bima Yojana",
        "level": "State",
        "state": "Maharashtra",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Accidental death or permanent disability insurance cover of up to Rs. 2,00,000 for the farmer or family members.",
        "eligibility": "All registered farmers in Maharashtra aged 10 to 75 years holding a 7/12 land extract.",
        "how_to_apply": "Claims processed through the Taluka Agriculture Officer with hospital and police reports.",
        "portal_link": "https://krishi.maharashtra.gov.in",
    },

    # ==================== KARNATAKA STATE SCHEMES ====================
    {
        "name": "Krishi Bhagya Scheme",
        "level": "State",
        "state": "Karnataka",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "80% to 90% subsidy for rainfed farmers to construct farm ponds, install polythene lining, and set up diesel/solar pump sets and micro-irrigation.",
        "eligibility": "Farmers cultivating land in rainfed and drought-prone taluks of Karnataka.",
        "how_to_apply": "Apply online through the Raitha Siri / Seva Sindhu portal or contact the Raitha Samparka Kendra (RSK).",
        "portal_link": "https://raitamitra.karnataka.gov.in",
    },
    {
        "name": "Raitha Siri Scheme",
        "level": "State",
        "state": "Karnataka",
        "crop_category": "Cereals",
        "applicable_crops": "rice,maize",
        "benefits": "Direct cash incentive of Rs. 10,000 per hectare into the farmer's bank account for cultivating millets, maize, and indigenous foodgrains.",
        "eligibility": "All farmers growing notified cereals and millets registered on the FID / FRUITS portal.",
        "how_to_apply": "Register on the Karnataka FRUITS portal (Farmer Registration & Unified Beneficiary Information System).",
        "portal_link": "https://fruits.karnataka.gov.in",
    },

    # ==================== MADHYA PRADESH STATE SCHEMES ====================
    {
        "name": "Mukhyamantri Kisan Kalyan Yojana",
        "level": "State",
        "state": "Madhya Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Additional cash assistance of Rs. 6,000 per year delivered in two equal installments of Rs. 3,000 alongside PM-KISAN.",
        "eligibility": "All landholding farmers in Madhya Pradesh eligible under PM-KISAN.",
        "how_to_apply": "Verified through the local Patwari or online via the SAARA MP portal.",
        "portal_link": "https://saara.mp.gov.in",
    },
    {
        "name": "Bhavantar Bhugtan Yojana",
        "level": "State",
        "state": "Madhya Pradesh",
        "crop_category": "Pulses",
        "applicable_crops": "chickpea,mungbean,pigeonpeas,lentil,blackgram",
        "benefits": "Price deficiency payment: directly transfers the difference between the Minimum Support Price (MSP) and the lower mandi selling price into the farmer's account.",
        "eligibility": "Registered pulse and oilseed farmers selling their produce at notified APMC mandis.",
        "how_to_apply": "Register on the MP e-Uparjan portal before the harvesting season.",
        "portal_link": "https://mpeuparjan.nic.in",
    },

    # ==================== PUNJAB & HARYANA STATE SCHEMES ====================
    {
        "name": "Mera Pani Meri Virasat / Crop Diversification Scheme",
        "level": "State",
        "state": "Haryana",
        "crop_category": "ALL",
        "applicable_crops": "maize,cotton,chickpea,pigeonpeas,mungbean",
        "benefits": "Direct financial incentive of Rs. 7,000 per acre to farmers who replace water-intensive paddy with alternative crops like maize, cotton, or pulses.",
        "eligibility": "Farmers in designated over-exploited groundwater blocks switching away from paddy.",
        "how_to_apply": "Apply on the Meri Fasal Mera Byora portal (fasal.haryana.gov.in).",
        "portal_link": "https://fasal.haryana.gov.in",
    },
    {
        "name": "Bhavantar Bharpayee Yojana (BBY)",
        "level": "State",
        "state": "Haryana",
        "crop_category": "Fruits",
        "applicable_crops": "pomegranate,banana,mango,grapes,watermelon,muskmelon,apple,orange,papaya",
        "benefits": "Price protection for horticulture and fruit crops compensating the difference between the government protected base price and the actual mandi sale price.",
        "eligibility": "Horticulture farmers in Haryana registered on the Meri Fasal Mera Byora portal.",
        "how_to_apply": "Register crop acreage on fasal.haryana.gov.in during the sowing window.",
        "portal_link": "https://hortnet.gov.in",
    },
    {
        "name": "Punjab Crop Diversification & In-Situ Management Scheme",
        "level": "State",
        "state": "Punjab",
        "crop_category": "ALL",
        "applicable_crops": "maize,cotton,chickpea,mungbean",
        "benefits": "50% to 80% subsidy on mechanized seed drills, Happy Seeders, and crop diversification assistance for shifting to maize, cotton, and pulses.",
        "eligibility": "All landholding farmers and registered custom hiring centers in Punjab.",
        "how_to_apply": "Apply via the Department of Agriculture & Farmers Welfare, Punjab portal.",
        "portal_link": "https://agri.punjab.gov.in",
    },

    # ==================== UTTAR PRADESH STATE SCHEMES ====================
    {
        "name": "UP Kisan Karz Rahat & Subsidized Seed Distribution",
        "level": "State",
        "state": "Uttar Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Up to 50% direct subsidy on certified foundation seeds of foodgrains, pulses, and oilseeds, plus interest subvention on cooperative loans.",
        "eligibility": "Registered farmers of Uttar Pradesh holding a Kisan credit account and land records.",
        "how_to_apply": "Register on the UP Agriculture portal (upagriculture.com) with Kisan Aadhaar linkage.",
        "portal_link": "http://upagriculture.com",
    },
    {
        "name": "Mukhyamantri Khet Suraksha Yojana",
        "level": "State",
        "state": "Uttar Pradesh",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Subsidy of up to 60% (or Rs. 1,43,000 per hectare) for installing solar fencing to protect standing crops from stray cattle and wildlife.",
        "eligibility": "Small, marginal, and general farmers in notified districts of Uttar Pradesh.",
        "how_to_apply": "Apply on the UP Agriculture DBT portal or through the District Agriculture Officer.",
        "portal_link": "http://upagriculture.com",
    },

    # ==================== TAMIL NADU STATE SCHEMES ====================
    {
        "name": "Kalaignarin All Village Integrated Agriculture Development Programme",
        "level": "State",
        "state": "Tamil Nadu",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Free distribution of quality seed kits, 100% micro-irrigation subsidy for small/marginal farmers, solar pump assistance, and farm pond creation.",
        "eligibility": "All farmers resident in Tamil Nadu with active farmland.",
        "how_to_apply": "Apply via the Uzhavan Mobile App or visit the local Agricultural Extension Centre (AEC).",
        "portal_link": "https://tnhorticulture.tn.gov.in",
    },
    {
        "name": "Kuruvai / Samba Special Package Scheme",
        "level": "State",
        "state": "Tamil Nadu",
        "crop_category": "Cereals",
        "applicable_crops": "rice,maize",
        "benefits": "100% subsidized certified seeds, micronutrient fertilizers, bio-fertilizers, and mechanized paddy transplanting assistance in the Cauvery Delta.",
        "eligibility": "Paddy and cereal growers in notified Delta districts of Tamil Nadu.",
        "how_to_apply": "Distributed through local Primary Agricultural Cooperative Credit Societies (PACCS).",
        "portal_link": "https://agritech.tnau.ac.in",
    },

    # ==================== ODISHA STATE SCHEMES ====================
    {
        "name": "KALIA (Krushak Assistance for Livelihood & Income Augmentation)",
        "level": "State",
        "state": "Odisha",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Financial assistance of Rs. 10,000 per farm family (Rs. 5,000 for Kharif and Rs. 5,000 for Rabi) for purchasing seeds, fertilizer, and operational inputs.",
        "eligibility": "Small and marginal farmers as well as landless agricultural households in Odisha.",
        "how_to_apply": "Register online at kalia.odisha.gov.in or through the Mo Seva Kendra.",
        "portal_link": "https://kalia.odisha.gov.in",
    },

    # ==================== WEST BENGAL STATE SCHEMES ====================
    {
        "name": "Krishak Bandhu Scheme",
        "level": "State",
        "state": "West Bengal",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Assured financial support of up to Rs. 10,000 per acre per year delivered in two installments (Kharif and Rabi) + Rs. 2,00,000 death benefit for farmer families.",
        "eligibility": "All landholding farmers and recorded Bhagchasis (sharecroppers) in West Bengal.",
        "how_to_apply": "Register through the Krishak Bandhu portal or at your local Duare Sarkar camp.",
        "portal_link": "https://krishakbandhu.wb.gov.in",
    },
    {
        "name": "Bangla Shasya Bima (BSB)",
        "level": "State",
        "state": "West Bengal",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "100% free crop insurance coverage. The West Bengal government pays the entire premium amount for all notified food and commercial crops.",
        "eligibility": "All farmers growing notified crops in West Bengal.",
        "how_to_apply": "Apply through the BSB portal (banglashasyabima.net) or local Assistant Director of Agriculture (ADA) office.",
        "portal_link": "https://banglashasyabima.net",
    },

    # ==================== RAJASTHAN STATE SCHEMES ====================
    {
        "name": "Rajasthan Krishi Sathi & Micro-Irrigation Yojana",
        "level": "State",
        "state": "Rajasthan",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Up to 70% subsidy on drip and sprinkler systems, plus capital grants of up to Rs. 1,00,000 for constructing farm ponds and water storage diggies.",
        "eligibility": "Farmers possessing valid Jamabandi land records in Rajasthan.",
        "how_to_apply": "Apply online at RajKisan Sathi Portal (rajkisan.rajasthan.gov.in).",
        "portal_link": "https://rajkisan.rajasthan.gov.in",
    },

    # ==================== GUJARAT STATE SCHEMES ====================
    {
        "name": "i-Khedut Portal Agricultural Assistance Schemes",
        "level": "State",
        "state": "Gujarat",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Subsidies of 40% to 50% for farm equipment, solar pumps, underground PVC pipelines, shade nets, and fruit orchard saplings.",
        "eligibility": "All landholding farmers registered on the Gujarat 7/12 land portal.",
        "how_to_apply": "Apply directly on the i-Khedut portal (ikhedut.gujarat.gov.in) during the active application window.",
        "portal_link": "https://ikhedut.gujarat.gov.in",
    },

    # ==================== BIHAR STATE SCHEMES ====================
    {
        "name": "Bihar Rajya Fasal Sahayata Yojana (BRFSY)",
        "level": "State",
        "state": "Bihar",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Free crop loss assistance of Rs. 7,500/hectare (for loss up to 20%) and Rs. 10,000/hectare (for loss >20%) with zero farmer premium.",
        "eligibility": "Both raiyat (land-owning) and non-raiyat (tenant) farmers in Bihar.",
        "how_to_apply": "Register on the Bihar Cooperative Department portal (pacsonline.bih.nic.in).",
        "portal_link": "https://pacsonline.bih.nic.in",
    },

    # ==================== KERALA STATE SCHEMES ====================
    {
        "name": "Subhiksha Keralam & State Crop Insurance",
        "level": "State",
        "state": "Kerala",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Direct input subsidies and state insurance cover for 27 notified crops (including paddy, banana, coconut, and vegetables) against wild animal damage and natural calamities.",
        "eligibility": "All farmers cultivating crops in Kerala with Krishi Bhavan registration.",
        "how_to_apply": "Apply through the AIMS Kerala portal (aims.kerala.gov.in) or visit your local Krishi Bhavan.",
        "portal_link": "https://aims.kerala.gov.in",
    },
    # ==================== GOA STATE SCHEMES ====================
    {
        "name": "Goa Shetkari Adhar Yojana",
        "level": "State",
        "state": "Goa",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Compensation and financial relief up to ₹40,000/ha to farmers suffering crop loss due to unseasonal rain, floods, pests, or wildlife incursions.",
        "eligibility": "All bonafide farmers in North Goa and South Goa registered with a Krishi Card.",
        "how_to_apply": "Submit claim form at the nearest Zonal Agriculture Office (ZAO) within 15 days of damage.",
        "portal_link": "https://agri.goa.gov.in",
    },
    {
        "name": "Goa Assistance for Cultivation of Paddy and Cereals",
        "level": "State",
        "state": "Goa",
        "crop_category": "Cereals & Millets",
        "applicable_crops": "rice,maize",
        "benefits": "Input subsidy up to ₹40,000 per hectare for mechanical transplanting, certified seeds subsidy, and assured procurement support at remunerative prices.",
        "eligibility": "Paddy and cereal growers in Goa holding agricultural land title or tenant tenancy card.",
        "how_to_apply": "Apply through the Zonal Agricultural Office (ZAO) or online on Goa Online Portal (goaonline.gov.in).",
        "portal_link": "https://agri.goa.gov.in",
    },
    {
        "name": "Goa Coconut & Plantation Rejuvenation Scheme",
        "level": "State",
        "state": "Goa",
        "crop_category": "Plantation Crops",
        "applicable_crops": "coconut",
        "benefits": "Subsidy of ₹150 per high-yielding coconut seedling, 75% financial grant for cutting diseased palms, and 50% subsidy for micro-irrigation systems.",
        "eligibility": "Coconut plantation farmers and grove owners in Goa with active Krishi Card.",
        "how_to_apply": "Apply online at goaonline.gov.in or in person at the local ZAO.",
        "portal_link": "https://agri.goa.gov.in",
    },
    {
        "name": "Goa Commercial Horticulture & Fruit Crops Support",
        "level": "State",
        "state": "Goa",
        "crop_category": "Fruits & Horticulture",
        "applicable_crops": "banana,mango,papaya,watermelon,muskmelon",
        "benefits": "50% capital subsidy on quality grafted planting material, solar fencing subsidies, and micro-irrigation drip subsidies.",
        "eligibility": "Growers of fruit and commercial horticulture crops in Goa.",
        "how_to_apply": "Register with the Directorate of Agriculture, Krishi Bhavan, Tonca, Caranzalem, Goa.",
        "portal_link": "https://agri.goa.gov.in",
    },

    # ==================== ANDAMAN & NICOBAR ISLANDS UT PROGRAMMES ====================
    {
        "name": "A&N Agriculture Department and ATMA Farmer Support",
        "level": "Union Territory",
        "state": "Andaman and Nicobar Islands",
        "crop_category": "ALL",
        "applicable_crops": "ALL",
        "benefits": "Farmer training, demonstrations, exposure visits, farm schools, farmer-scientist interaction, and agricultural technology support through ATMA and the UT Agriculture Department.",
        "eligibility": "Farmers and farmer groups in Andaman and Nicobar Islands. Specific activities, locations, and enrolment conditions are decided by the UT Agriculture Department.",
        "how_to_apply": "Contact the local Agriculture Department or ATMA office to confirm the current activity, district coverage, documents, and enrolment process.",
        "portal_link": "https://agri.andamannicobar.gov.in/atma",
    },
]


def init_db() -> None:
    """Initialize SQLite database and create tables if not present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            level TEXT NOT NULL,
            state TEXT NOT NULL,
            crop_category TEXT NOT NULL,
            applicable_crops TEXT NOT NULL,
            benefits TEXT NOT NULL,
            eligibility TEXT NOT NULL,
            how_to_apply TEXT NOT NULL,
            portal_link TEXT NOT NULL
        )
    """)

    # Insert or update all seed schemes so corrections reach existing installations.
    for s in SEED_SCHEMES:
        values = (s["level"], s["state"], s["crop_category"], s["applicable_crops"],
                  s["benefits"], s["eligibility"], s["how_to_apply"], s["portal_link"])
        cursor.execute("SELECT id FROM schemes WHERE name = ?", (s["name"],))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE schemes SET level = ?, state = ?, crop_category = ?, applicable_crops = ?,
                    benefits = ?, eligibility = ?, how_to_apply = ?, portal_link = ?
                WHERE id = ?
            """, (*values, existing[0]))
        else:
            cursor.execute("""
                INSERT INTO schemes (name, level, state, crop_category, applicable_crops, benefits, eligibility, how_to_apply, portal_link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (s["name"], *values))
    conn.commit()
    conn.close()


def get_schemes_for_crop_and_state(crop: str, state: str) -> List[Dict[str, Any]]:
    """
    Query government schemes applicable specifically to the given recommended crop and state.
    
    A scheme matches if:
    1. State matches the user's state OR is nationwide ('ALL')
    2. AND the scheme covers all crops ('ALL'), or the specific crop, or the crop's category.
    """
    if not DB_PATH.exists():
        init_db()

    crop_clean = (crop or "").strip().lower()
    state_clean = (state or "").strip()
    category = CROP_CATEGORIES.get(crop_clean, "General")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Query schemes where state is ALL or matches the user's state
    cursor.execute("""
        SELECT id, name, level, state, crop_category, applicable_crops, benefits, eligibility, how_to_apply, portal_link
        FROM schemes
        ORDER BY CASE WHEN level = 'State' THEN 1 ELSE 2 END, id ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        (s_id, name, level, s_state, s_category, s_crops, benefits, eligibility, how_to_apply, portal_link) = row

        # 1. State matching check
        is_state_match = (
            s_state.upper() == "ALL"
            or s_state.lower() == state_clean.lower()
            or state_clean.lower() in s_state.lower()
            or s_state.lower() in state_clean.lower()
        )
        if not is_state_match:
            continue

        # 2. Crop matching check
        crops_list = [c.strip().lower() for c in s_crops.split(",") if c.strip()]
        is_crop_match = (
            "all" in crops_list
            or crop_clean in crops_list
            or s_category.lower() == category.lower()
            or s_category.upper() == "ALL"
        )
        if not is_crop_match:
            continue

        badge = f"{level} Scheme" if s_state.upper() == "ALL" else f"{level} Scheme ({state_clean})"

        results.append({
            "id": s_id,
            "name": name,
            "level": level,
            "state": s_state,
            "crop_category": s_category,
            "badge": badge,
            "benefits": benefits,
            "eligibility": eligibility,
            "how_to_apply": how_to_apply,
            "portal_link": portal_link,
        })

    return results


# Automatically ensure DB is created upon import
init_db()
