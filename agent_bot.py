import nest_asyncio
import pandas as pd
import base64
import uvicorn
import io
import speech_recognition as sr
from pydub import AudioSegment
from PIL import Image
import requests
import re
import os
import glob
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition
from tavily import TavilyClient
from dotenv import load_dotenv 
from langchain_core.messages import SystemMessage, HumanMessage
import imageio_ffmpeg as ffmpeg

# 1. CRITICAL: Initialize nest_asyncio and FastAPI at the TOP
nest_asyncio.apply()
app = FastAPI()

# Point pydub to the ffmpeg binary provided by imageio-ffmpeg
AudioSegment.converter = ffmpeg.get_ffmpeg_exe()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama # For the local Llama fallback

import os
import asyncio
import time
from langchain_google_genai import ChatGoogleGenerativeAI

#==================================================================================

# 1. Setup your keys (Ensure these are in your .env)
primary_key = os.getenv("GAI_KEY_DEFAULT_PROJECT")#    os.getenv("GAI_KEY_DEFAULT_PROJECT"), 
                                            #    os.getenv("GAI_KEY_OWN_PROJECT")
secondary_key = os.getenv("GAI_KEY_OWN_PROJECT")

# 2. Initialize both models
model_1 = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=primary_key)
model_2 = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=secondary_key)

# 3. Create the "Smart" model with fallback logic
# This replaces your manual rotation function
llm = model_1.with_fallbacks(
    [model_2], 
    exceptions_to_handle=(Exception,) # This forces fallback on ANY error
)

# 1. This object contains the "Brain" (Model 1) and the "Backup" (Model 2)
#llm = model_1.with_fallbacks([model_2])

def get_llm_response(prompt):
    try:
        # ✅ Call 'llm' so LangChain knows to try Model 1, 
        # then automatically try Model 2 if Model 1 fails.
        response = llm.invoke(prompt)
        return response
    except Exception as e:
        # This only runs if BOTH models fail (e.g., both API keys are blocked)
        print(f"CRITICAL ERROR: Both models failed! {e}")
        return "System overloaded. Please try again in a few minutes."

# 5. Keep your Async execution logic
async def run_agent(user_input, image_data=None):
    # Your existing async logic to process inputs
    inputs = {"messages": [("user", user_input)]}
    # ... logic to include image_data if present ...
    
    async for event in app.astream(inputs):
        for value in event.values():
            print("Assistant:", value["messages"][-1].content)

#==============================================================================


#local_llm = ChatOllama(model="llama3.2:1b")


from langchain_core.messages import SystemMessage, HumanMessage

# --- 2. BINDING TOOLS TO LLM ---
#@tool
#def get_weather_by_location(location_name: str):
    #"""
    #Fetches a full weather report (Temp, Humidity, Rain, Wind) 
    #using only the name of the city or region.
    #"""

#===================================================================
import requests
from datetime import datetime

def get_crop_calendar():
    """Returns sowing and reaping info based on the current month."""
    month = datetime.now().month
    
    # Define agricultural seasons for the region (e.g., D.I. Khan/Pakistan context)
    calendar = {
        1:  {"sow": "Late Wheat", "reap": "Sugarcane, Guava"},
        2:  {"sow": "Spring Sugarcane, Sunflower", "reap": "Sugarcane, Mustard"},
        3:  {"sow": "Spring Maize, Sugarcane", "reap": "Wheat (Early), Gram"},
        4:  {"sow": "Cotton, Rice (Nurseries)", "reap": "Wheat (Peak), Mustard"},
        5:  {"sow": "Cotton, Kharif Maize", "reap": "Wheat (Final), Berries"},
        6:  {"sow": "Rice (Transplanting), Cotton", "reap": "Melons, Mangoes"},
        7:  {"sow": "Rice, Maize", "reap": "Mangoes, Dates (Early)"},
        8:  {"sow": "Late Rice, Vegetables", "reap": "Dates (Peak), Mangoes"},
        9:  {"sow": "Autumn Maize, Mustard", "reap": "Dates (Final), Rice (Early)"},
        10: {"sow": "Wheat (Early), Gram", "reap": "Rice, Cotton"},
        11: {"sow": "Wheat (Peak), Oilseeds", "reap": "Rice, Cotton, Sugarcane"},
        12: {"sow": "Wheat (Final)", "reap": "Sugarcane, Citrus"}
    }
    return calendar.get(month, {"sow": "N/A", "reap": "N/A"})
#===================================================================

@tool
def get_weather_by_location(location: str):
    """
    Fetches a comprehensive real-time weather report and associated crop calendar.
    
    REQUIRED: A specific city or area name must be provided. The function will 
    not attempt to guess the user's location.

    Optimized for 350px UI cards.Output must be concise: 'Short answer, full data'—meaning all metrics are 
    included but with minimal text.
    Returns a full report including Temperature, Humidity, Rain, and Wind speed. 
    Additionally, integrates with `get_crop_calendar()` to provide a list of 
    crops to sow or reap based on the current weather conditions.
    
    Args:
        location (str): The name of the city or region for the weather lookup.
    """
    
   
    
   
    location = location.strip()
    print(f"DEBUG: Weather tool searching for: {location}")
    try:
        # Step 1: Geocoding (Convert Name to Lat/Lon)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
        geo_res = requests.get(geo_url).json()
        
        if not geo_res.get("results"):
            return f"Could not find coordinates for '{location}'. Please check the spelling."

        location_data = geo_res["results"][0]
        lat = location_data["latitude"]
        lon = location_data["longitude"]

        # Step 2: Fetch Weather using the coordinates found
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,rain,wind_speed_10m"
        weather_res = requests.get(weather_url).json()
        current = weather_res.get('current', {})
        
        # Step 3: Get Crop Context 
        crops = get_crop_calendar()

        return (
            f"🌤️ **Weather Report for {location}**:\n"
            f"- Temperature: {current.get('temperature_2m')}°C\n"
            f"- Humidity: {current.get('relative_humidity_2m')}%\n"
            f"- Rain: {current.get('rain')} mm\n"
            f"- Wind Speed: {current.get('wind_speed_10m')} km/h\n\n"
            f"🌾 **Agricultural Context for {datetime.now().strftime('%B')}:**\n"
            f"- **Crops to Sow:** {crops['sow']}\n"
            f"- **Crops to Reap:** {crops['reap']}\n"
            f"Source: Open-Meteo & Regional Crop Calendar"
           
        )
    except Exception as e:
        return f"Error connecting to weather services: {str(e)}"
import os
import pandas as pd
from langchain.tools import tool

import os

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED LOOKUP TABLE
# Structure: DB[plant_lower][fertility_band][irrigation_band]
#   fertility_band : "low" (0-30) | "medium" (31-70) | "high" (71-100)
#   irrigation_band: "low" (0-50) | "high" (51-100)
#
# Each entry is a dict with four keys:
#   BOOST_STRATEGY | GROWTH_HACK | IDEAL_PH | RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────

DB1 = {

    # ── KACHNAR ──────────────────────────────────────────────────────────────
    "kachnar": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC (Cation Exchange Capacity) for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Kachnar.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Kachnar is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other — without soil organic matter, water infiltration is poor, and without water, applied fertilizers cannot dissolve and reach roots. Priority action: incorporate 5 kg compost per tree before next irrigation to simultaneously improve fertility and water retention capacity. Scout for aphids and mites weekly — nutrient and moisture-stressed Kachnar is the primary target for sucking pests; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC (Cation Exchange Capacity) for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Kachnar depleted soils.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good, which is an advantage — water is reliably reaching Kachnar roots, but the soil lacks the nutrients needed to convert that water into flowering and biomass. Apply the recommended fertilizer in split doses to maximise uptake. Monitor leaf color closely: yellowing indicates nitrogen shortage, purple tints indicate phosphorus deficiency, and leaf-edge scorch indicates potassium lockout.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Kachnar roots compared to flood irrigation.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Kachnar out to the drip line — this retains up to 35% more soil moisture between irrigation sessions and reduces the impact of low irrigation efficiency.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Kachnar growth, but poor irrigation efficiency is the single bottleneck — water is being lost to evaporation and runoff before it reaches the root zone. Fixing the irrigation system will immediately unlock the existing soil fertility without any additional fertilizer input; estimate at least 25–35% yield improvement from irrigation repair alone. Once water delivery is restored, apply a light potassium top-dressing and mulch the base to hold soil moisture between sessions.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree or 15 kg/acre for field crops) to enhance flowering and biomass without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Kachnar every 6 months to open the canopy, improve light penetration into inner branches, and reduce pest harborage — this directly improves both growth rate and flowering and biomass.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Kachnar a stable foundation — shift focus from survival management to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target flowering and biomass more precisely. Introduce a monthly pest scouting routine — early detection prevents yield loss without heavy pesticide use.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Kachnar.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Kachnar to deliver water directly to the root zone; this unlocks the high soil fertility that is currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency — nutrients in dry soil are immobile and cannot be absorbed by Kachnar roots without adequate soil moisture. Every rupee invested in repairing irrigation infrastructure will yield a disproportionate return here. Avoid adding more fertilizer in this state — unapplied nutrients accumulate to toxic levels when irrigation finally normalises; fix water delivery first.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Kachnar — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency at the root zone.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Kachnar once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption in already fertile soil.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Optimal conditions: Kachnar has access to both rich soil nutrients and efficient water delivery — management focus should now shift entirely to maximising flowering and biomass and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme — combine pheromone traps, beneficial insects, and targeted biological sprays to protect the high-value output.",
            },
        },
    },

    # ── THUJA ─────────────────────────────────────────────────────────────────
    "thuja": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Thuja.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Thuja is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively to protect the already weakened plant.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Thuja depleted soils.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Thuja roots, but the soil lacks the nutrients needed to convert that water into dense foliage and height. Apply the recommended fertilizer in split doses to maximise uptake. Monitor leaf color closely as the first indicator of nutrient response.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Thuja roots compared to flood irrigation.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Thuja out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Thuja growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility; estimate at least 25–35% yield improvement from irrigation repair alone. Once water delivery is restored, apply a light potassium top-dressing to support dense foliage and height.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance dense foliage and height without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Thuja every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves growth rate and dense foliage.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Thuja a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine; early detection prevents yield loss without heavy pesticide use.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Thuja.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Thuja to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency — nutrients in dry soil are immobile and cannot be absorbed by Thuja roots without adequate soil moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Thuja — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Thuja once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "5.0–6.5",
                "RECOMMENDATION":   "Optimal conditions: Thuja has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising dense foliage and height and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── ROSE ──────────────────────────────────────────────────────────────────
    "rose": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 10-30-20 at 100g per plant to prioritize phosphorus for root development and potassium for bloom quality; repeat every 6 weeks during the active growing season.",
                "GROWTH_HACK":      "Mix banana peel powder (dried + ground) into the root soil at 100g per plant to provide slow-release potassium, which directly boosts bloom size and petal count in Roses.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Rose is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively to protect the already weakened plant.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 10-30-20 at 100g per plant to prioritize phosphorus for root development and potassium for bloom quality; repeat every 6 weeks during the active growing season.",
                "GROWTH_HACK":      "Apply diluted epsom salt solution (magnesium sulfate, 1 tbsp per liter) as monthly foliar spray to correct magnesium deficiency, which causes yellowing between leaf veins and weak flowering.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Rose roots, but the soil lacks the nutrients needed to convert that water into bloom quantity and quality. Apply the recommended fertilizer in split doses to maximise uptake. Monitor leaf color closely as the first indicator of nutrient response.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Rose roots compared to flood irrigation.",
                "GROWTH_HACK":      "Apply a thick 7 cm mulch ring of wood chips around the base to reduce water loss by 40% and keep roots cool — this directly improves bloom continuity through summer heat.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Rose growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support bloom quantity and quality.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree or 15 kg/acre) to enhance bloom quantity and quality without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Deadhead all spent blooms immediately after flowering using clean, sharp shears — this redirects the plant's energy from seed production to generating 2–3 new flower buds per cut stem.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Rose a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Rose.",
                "GROWTH_HACK":      "Install a simple drip ring emitter at the base to deliver water precisely at the root zone — overhead watering on Rose foliage promotes black spot (Diplocarpon rosae) fungal infection.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Fix water delivery first, then re-evaluate fertility needs. Avoid adding more fertilizer until irrigation is restored.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Rose — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply neem oil spray (5 ml/liter water) every 2 weeks as a preventive measure against black spot, powdery mildew, and aphids — do this at dusk to avoid leaf burn from oil + sunlight.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Optimal conditions: Rose has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising bloom quantity and quality and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── EUPHORBIA ─────────────────────────────────────────────────────────────
    "euphorbia": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply slow-release granular fertilizer (NPK 5-10-10) at 50g per plant once every 3 months; avoid nitrogen-heavy fertilizers as these cause soft, rot-prone growth in Euphorbia.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Euphorbia.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Euphorbia is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply slow-release granular fertilizer (NPK 5-10-10) at 50g per plant once every 3 months; avoid nitrogen-heavy fertilizers as these cause soft, rot-prone growth in Euphorbia.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Euphorbia depleted soils.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Euphorbia roots, but the soil lacks the nutrients needed to convert that water into structural growth and ornamental value. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Euphorbia roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Euphorbia out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Euphorbia growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support structural growth and ornamental value.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance structural growth and ornamental value without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Euphorbia every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and structural growth.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Euphorbia a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Euphorbia.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Euphorbia to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Euphorbia roots without adequate soil moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Euphorbia — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Euphorbia once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Optimal conditions: Euphorbia has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising structural growth and ornamental value and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── GUAVA ─────────────────────────────────────────────────────────────────
    "guava": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support fruit size and yield.",
                "GROWTH_HACK":      "Apply a ring of 5 kg well-rotted FYM per tree in the root basin, then irrigate deeply — organic matter improves moisture retention and releases micronutrients slowly, directly supporting fruit set.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Guava is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support fruit size and yield.",
                "GROWTH_HACK":      "Spray zinc sulfate (ZnSO4 at 3g/liter) and boric acid (1g/liter) as a combined foliar spray during flowering — zinc and boron deficiency are the top causes of small, seedy fruit in Guava.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Guava roots, but the soil lacks the nutrients needed to convert that water into fruit size and yield. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Guava roots.",
                "GROWTH_HACK":      "Thin the irrigation schedule to deep, infrequent sessions (once every 4–5 days) rather than light daily watering — this forces roots to grow deeper, increasing drought resistance and fruit quality.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Guava growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support fruit size and yield.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree or 15 kg/acre) to enhance fruit size and yield without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Thin out 30–40% of immature fruitlets when fruit reach marble size — this concentrates nutrients into remaining fruit, producing fewer but significantly larger, sweeter Guavas.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Guava a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus). Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Guava.",
                "GROWTH_HACK":      "Mulch the entire root zone with dry sugarcane trash or straw at 10 cm depth to conserve the soil's high fertility from evaporation losses during dry spells.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Guava roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "With optimal fertility and irrigation, focus on yield quality — apply calcium nitrate at 2g/liter as a foliar spray during fruit development to improve cell strength, prevent blossom-end rot, and maximize fruit size and yield.",
                "GROWTH_HACK":      "Set pheromone traps for fruit fly (Bactrocera dorsalis) monitoring — this pest alone can destroy 40–60% of the Guava crop; 1 trap per 25 trees is recommended from flowering onwards.",
                "IDEAL_PH":         "5.0–7.0",
                "RECOMMENDATION":   "Optimal conditions: Guava has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising fruit size and yield and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── NEEM ──────────────────────────────────────────────────────────────────
    "neem": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Neem.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Neem is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Neem depleted soils.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Neem roots, but the soil lacks the nutrients needed to convert that water into canopy spread and pest resilience. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Neem roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Neem out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Neem growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support canopy spread and pest resilience.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance canopy spread and pest resilience without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Neem every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and canopy spread.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Neem a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Neem.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Neem to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Neem roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Neem — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Neem once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Optimal conditions: Neem has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising canopy spread and pest resilience and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── SHEESHAM ──────────────────────────────────────────────────────────────
    "sheesham": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Sheesham.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Sheesham is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Sheesham depleted soils.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Sheesham roots, but the soil lacks the nutrients needed to convert that water into trunk girth and wood density. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Sheesham roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Sheesham out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Sheesham growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support trunk girth and wood density.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance trunk girth and wood density without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Sheesham every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and trunk girth.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Sheesham a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Sheesham.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Sheesham to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Sheesham roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Sheesham — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Sheesham once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Optimal conditions: Sheesham has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising trunk girth and wood density and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── RUBBER TREE ───────────────────────────────────────────────────────────
    "rubber tree": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Rubber Tree.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rubber Tree is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Rubber Tree depleted soils.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Rubber Tree roots, but the soil lacks the nutrients needed to convert that water into leaf glossiness and vertical growth. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Rubber Tree roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Rubber Tree out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Rubber Tree growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support leaf glossiness and vertical growth.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance leaf glossiness and vertical growth without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Rubber Tree every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and leaf glossiness.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Rubber Tree a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Rubber Tree.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Rubber Tree to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Rubber Tree roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Rubber Tree — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Rubber Tree once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Optimal conditions: Rubber Tree has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising leaf glossiness and vertical growth and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── SUFAIDA ───────────────────────────────────────────────────────────────
    "sufaida": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Sufaida.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Sufaida is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-20 at 200–300g per tree mixed into the root zone soil; supplement with 3 kg compost per tree to restore depleted organic matter and improve CEC for better nutrient retention.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Sufaida depleted soils.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Sufaida roots, but the soil lacks the nutrients needed to convert that water into fast biomass and height. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Sufaida roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Sufaida out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Sufaida growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support fast biomass and height.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance fast biomass and height without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Sufaida every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and fast biomass.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Sufaida a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Sufaida.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Sufaida to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Sufaida roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Sufaida — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Sufaida once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Optimal conditions: Sufaida has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising fast biomass and height and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── ALOE VERA ─────────────────────────────────────────────────────────────
    "aloe vera": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply slow-release granular fertilizer (NPK 5-10-10) at 50g per plant once every 3 months; avoid nitrogen-heavy fertilizers as these cause soft, rot-prone growth in Aloe Vera.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Aloe Vera.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Aloe Vera is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply slow-release granular fertilizer (NPK 5-10-10) at 50g per plant once every 3 months; avoid nitrogen-heavy fertilizers as these cause soft, rot-prone growth in Aloe Vera.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Aloe Vera depleted soils.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Aloe Vera roots, but the soil lacks the nutrients needed to convert that water into gel-leaf size and pup production. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Aloe Vera roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Aloe Vera out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Aloe Vera growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support gel-leaf size and pup production.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance gel-leaf size and pup production without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Aloe Vera every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and gel-leaf size.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Aloe Vera a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Aloe Vera.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Aloe Vera to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Aloe Vera roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Aloe Vera — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Aloe Vera once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.0–8.5",
                "RECOMMENDATION":   "Optimal conditions: Aloe Vera has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising gel-leaf size and pup production and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── RABAIL / JASMINE ──────────────────────────────────────────────────────
    "rabail/jasmine": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 10-30-20 at 100g per plant to prioritize phosphorus for root development and potassium for bloom quality; repeat every 6 weeks during the active growing season.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Rabail/Jasmine.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rabail/Jasmine is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 10-30-20 at 100g per plant to prioritize phosphorus for root development and potassium for bloom quality; repeat every 6 weeks during the active growing season.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Rabail/Jasmine depleted soils.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Rabail/Jasmine roots, but the soil lacks the nutrients needed to convert that water into flower density and fragrance. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Rabail/Jasmine roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Rabail/Jasmine out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Rabail/Jasmine growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support flower density and fragrance.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance flower density and fragrance without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Rabail/Jasmine every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and flower density.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Rabail/Jasmine a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Rabail/Jasmine.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Rabail/Jasmine to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Rabail/Jasmine roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Conditions are optimal for Rabail/Jasmine — apply a light organic mulch layer (5 cm compost) annually to maintain high fertility; introduce beneficial mycorrhizal fungi inoculant to further enhance nutrient uptake efficiency.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Rabail/Jasmine once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Optimal conditions: Rabail/Jasmine has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising flower density and fragrance and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── TOOT ──────────────────────────────────────────────────────────────────
    "toot": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support berry yield and sweetness.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Toot.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Toot is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support berry yield and sweetness.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Toot depleted soils.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Toot roots, but the soil lacks the nutrients needed to convert that water into berry yield and sweetness. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Toot roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Toot out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Toot growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support berry yield and sweetness.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance berry yield and sweetness without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Toot every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and berry yield.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Toot a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Toot.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Toot to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Toot roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "With optimal fertility and irrigation, focus on yield quality — apply calcium nitrate at 2g/liter as a foliar spray during fruit development to improve cell strength, prevent blossom-end rot, and maximize berry yield and sweetness.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Toot once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "6.0–7.0",
                "RECOMMENDATION":   "Optimal conditions: Toot has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising berry yield and sweetness and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── JAVA PLUM ─────────────────────────────────────────────────────────────
    "java plum": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support fruit set and size.",
                "GROWTH_HACK":      "Apply a 3 cm layer of compost mixed with bone meal (100g per tree) into the root basin and water in thoroughly — bone meal provides slow-release phosphorus that rebuilds root architecture in nutrient-depleted soil around Java Plum.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Java Plum is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 5 kg compost per tree before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply a complete NPK 15-15-15 fertilizer at 500g per tree mixed into the root basin; supplement with 5 kg farmyard manure (FYM) per tree to rebuild soil organic matter and support fruit set and size.",
                "GROWTH_HACK":      "Apply liquid seaweed extract (diluted 1:50 with water) as a monthly root drench — seaweed provides natural plant growth hormones (cytokinins, auxins) that boost cell division and root development in Java Plum depleted soils.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Java Plum roots, but the soil lacks the nutrients needed to convert that water into fruit set and size. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Fix irrigation infrastructure immediately — switch to drip emitters or soaker hoses at the root zone; this will cut water use by 30–40% while doubling moisture availability to Java Plum roots.",
                "GROWTH_HACK":      "Lay a 7 cm mulch ring of dried leaves or wood chips around the base of Java Plum out to the drip line — this retains up to 35% more soil moisture between irrigation sessions.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Java Plum growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support fruit set and size.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 100g/tree) to enhance fruit set and size without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Prune dead, crossing, and inward-facing branches from Java Plum every 6 months to open the canopy, improve light penetration, and reduce pest harborage — this directly improves both growth rate and fruit set.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Java Plum a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Java Plum.",
                "GROWTH_HACK":      "Install drip emitters at 30 cm from the base of Java Plum to deliver water directly to the root zone; this unlocks the high soil fertility currently being wasted due to poor surface irrigation coverage.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Java Plum roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "With optimal fertility and irrigation, focus on yield quality — apply calcium nitrate at 2g/liter as a foliar spray during fruit development to improve cell strength, prevent blossom-end rot, and maximize fruit set and size.",
                "GROWTH_HACK":      "Apply mycorrhizal fungi inoculant (Glomus species) to the root zone of Java Plum once a year — these beneficial fungi extend the root network up to 10x, dramatically improving both water and nutrient absorption.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Optimal conditions: Java Plum has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising fruit set and size and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── WHEAT ─────────────────────────────────────────────────────────────────
    "wheat": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply DAP (18-46-0) at 50 kg/acre as basal dose at sowing, followed by urea top-dressing at 25 kg/acre at tillering stage to build tiller density.",
                "GROWTH_HACK":      "Apply seed treatment with Thiram + Bavistin fungicide before sowing to protect germinating seeds from smut (Ustilago tritici) and loose smut, which are especially destructive in nutrient-poor, stressed plants.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Wheat is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 2 tonnes/acre of compost before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply DAP (18-46-0) at 50 kg/acre as basal dose at sowing, followed by urea top-dressing at 25 kg/acre at tillering stage to build tiller density.",
                "GROWTH_HACK":      "Apply urea in split doses rather than all at once: half at sowing, remaining half at first irrigation (CRI stage) — this prevents nitrogen loss through leaching and improves uptake by 25–30%.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Wheat roots, but the soil lacks the nutrients needed to convert that water into grain yield and tiller count. Apply the recommended fertilizer in split doses to maximise uptake. Monitor leaf color closely as the first indicator of nutrient response.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Repair all irrigation leaks and switch to furrow or ridge-furrow system to reduce water waste by 25–35%; until repaired, prioritize watering at early morning to cut evaporation losses and protect grain yield and tiller count.",
                "GROWTH_HACK":      "Ensure proper field levelling before sowing and use border irrigation; wasteful flood irrigation in unlevelled fields causes waterlogging patches and dry zones simultaneously, reducing uniform germination.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Wheat growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility; estimate at least 25–35% yield improvement from irrigation repair alone. Once water delivery is restored, apply a light potassium top-dressing to support grain yield and tiller count.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 15 kg/acre) to enhance grain yield and tiller count without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Apply gypsum (calcium sulfate) at 100 kg/acre before sowing if soils are medium-pH — gypsum improves soil structure, provides sulfur for protein synthesis, and enhances Wheat grain quality.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Wheat a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target grain yield and tiller count more precisely. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Wheat.",
                "GROWTH_HACK":      "Install a simple channel system to distribute irrigation water evenly across all furrows — in high-fertility soil, uneven water delivery is the single biggest yield limiter.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Wheat roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Soil and irrigation are both at peak — apply a targeted foliar spray of potassium nitrate (KNO3 at 2% solution) at grain-fill stage to maximize final yield and grain yield and tiller count.",
                "GROWTH_HACK":      "Spray potassium nitrate (KNO3 at 2% solution) as a foliar feed at flag-leaf stage — this significantly increases grain weight (1000-kernel weight) in an already high-performing Wheat crop.",
                "IDEAL_PH":         "6.0–7.5",
                "RECOMMENDATION":   "Optimal conditions: Wheat has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising grain yield and tiller count and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── SUGARCANE ─────────────────────────────────────────────────────────────
    "sugarcane": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 15-15-15 at 2 bags/acre as basal fertilizer; follow with split urea applications (40 kg/acre each) at 30, 60, and 90 days after planting for sustained cane elongation.",
                "GROWTH_HACK":      "Intercrop Sugarcane with moong bean (mung) in the early 60 days — the legume fixes nitrogen naturally, suppresses weeds, and the farmer earns an extra pulse crop with no competition to cane.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Sugarcane is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 2 tonnes/acre of compost before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 15-15-15 at 2 bags/acre as basal fertilizer; follow with split urea applications (40 kg/acre each) at 30, 60, and 90 days after planting for sustained cane elongation.",
                "GROWTH_HACK":      "Apply trash mulching (the dry leaves left after harvest) back onto the field at 5 tonnes/acre — this recycles nutrients, suppresses weeds, and improves poor soils significantly over 2–3 seasons.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Sugarcane roots, but the soil lacks the nutrients needed to convert that water into cane length and sugar content. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Repair all irrigation leaks and switch to furrow or ridge-furrow system to reduce water waste by 25–35%; until repaired, prioritize watering at early morning to cut evaporation losses and protect cane length and sugar content.",
                "GROWTH_HACK":      "Practice earthing-up (mounding soil around cane base) at 90 days — this prevents lodging (cane falling over), improves root anchorage, and conserves irrigation water in the furrow channel.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Sugarcane growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support cane length and sugar content.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 15 kg/acre) to enhance cane length and sugar content without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Apply a foliar spray of potassium nitrate (2%) during the grand-growth phase — potassium is the key driver of sugarcane sucrose accumulation and significantly improves juice quality in cane.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Sugarcane a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target cane length and sugar content more precisely. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Sugarcane.",
                "GROWTH_HACK":      "Install underground drainage tiles or pipe laterals if the field has poor drainage — waterlogging in high-fertility Sugarcane fields causes root rot and complete lodging, wiping out yield in low-lying areas.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Sugarcane roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "With optimal fertility and irrigation, focus on yield quality — apply calcium nitrate at 2g/liter as a foliar spray during fruit development to improve cell strength, prevent blossom-end rot, and maximize cane length and sugar content.",
                "GROWTH_HACK":      "Monitor for Top Borer (Scirpophaga nivella) from April onwards using light traps — this pest bores into the growing point and causes dead hearts, which is the most yield-destructive pest in mature Sugarcane.",
                "IDEAL_PH":         "6.5–8.0",
                "RECOMMENDATION":   "Optimal conditions: Sugarcane has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising cane length and sugar content and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── RICE ──────────────────────────────────────────────────────────────────
    "rice": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 16-16-8 at 40 kg/acre as basal fertilizer; supplement with zinc sulfate (ZnSO4) at 5 kg/acre to prevent Khaira disease and improve grain fill.",
                "GROWTH_HACK":      "Practice green manuring by incorporating Sesbania (dhaincha) biomass into the field before transplanting — this adds 40–60 kg/acre of biological nitrogen and significantly improves low-fertility soil.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Rice is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 2 tonnes/acre of compost before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 16-16-8 at 40 kg/acre as basal fertilizer; supplement with zinc sulfate (ZnSO4) at 5 kg/acre to prevent Khaira disease and improve grain fill.",
                "GROWTH_HACK":      "Apply split nitrogen doses: 1/3 basal + 1/3 at active tillering + 1/3 at panicle initiation — split application increases nitrogen use efficiency by 30% compared to single basal application.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Rice roots, but the soil lacks the nutrients needed to convert that water into grain fill and tiller density. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Repair all irrigation leaks and switch to furrow or ridge-furrow system to reduce water waste by 25–35%; until repaired, prioritize watering at early morning to cut evaporation losses and protect grain fill and tiller density.",
                "GROWTH_HACK":      "Adopt the Alternate Wetting and Drying (AWD) technique — allow soil to dry to 15 cm below field surface before re-flooding; saves 25–30% irrigation water with no yield penalty.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Rice growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support grain fill and tiller density.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 15 kg/acre) to enhance grain fill and tiller density without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Apply zinc sulfate (ZnSO4) at 5 kg/acre before transplanting to prevent Khaira disease (zinc deficiency), which causes brown spots and severely stunts tiller production in Punjab soils.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Rice a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target grain fill and tiller density more precisely. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Rice.",
                "GROWTH_HACK":      "Laser land levelling of the field ensures uniform water distribution — uneven fields waste 20–25% more water on high spots while low spots get waterlogged, both reducing yield.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Rice roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Soil and irrigation are both at peak — apply a targeted foliar spray of potassium nitrate (KNO3 at 2% solution) at grain-fill stage to maximize final yield and grain fill and tiller density.",
                "GROWTH_HACK":      "Monitor for Stem Borer and Brown Plant Hopper weekly using light traps; at this high-fertility level the crop produces lush growth that is particularly attractive to sucking and boring insects.",
                "IDEAL_PH":         "5.5–7.0",
                "RECOMMENDATION":   "Optimal conditions: Rice has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising grain fill and tiller density and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── COTTON ────────────────────────────────────────────────────────────────
    "cotton": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-10-10 at 30 kg/acre at planting; avoid excess nitrogen at boll-formation stage — switch to potassium sulfate (SOP) at 15 kg/acre to improve fiber strength.",
                "GROWTH_HACK":      "Apply poultry manure at 500 kg/acre before sowing — it provides balanced N-P-K plus micronutrients and improves soil water-holding capacity, critical for Cotton establishment in poor soil.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Cotton is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 2 tonnes/acre of compost before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-10-10 at 30 kg/acre at planting; avoid excess nitrogen at boll-formation stage — switch to potassium sulfate (SOP) at 15 kg/acre to improve fiber strength.",
                "GROWTH_HACK":      "Use seed treatment with imidacloprid to protect seedlings from early-season sucking pests (thrips, jassids) — these insects are most destructive in nutrient-stressed plants and can cause 20–30% stand loss.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Cotton roots, but the soil lacks the nutrients needed to convert that water into boll count and fiber quality. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Repair all irrigation leaks and switch to furrow or ridge-furrow system to reduce water waste by 25–35%; until repaired, prioritize watering at early morning to cut evaporation losses and protect boll count and fiber quality.",
                "GROWTH_HACK":      "Install pheromone traps for Pink Bollworm and American Bollworm monitoring at 5 traps/acre — early detection allows timely spray decisions and reduces pesticide use by targeting only threshold-level infestations.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Cotton growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support boll count and fiber quality.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 15 kg/acre) to enhance boll count and fiber quality without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Apply a growth regulator (mepiquat chloride, 50 ml/acre) at first-squaring stage to control excessive vegetative growth and direct more energy into boll production — a standard practice for maximising lint yield.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Cotton a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target boll count and fiber quality more precisely. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Cotton.",
                "GROWTH_HACK":      "Drip irrigation system for Cotton in high-fertility soil delivers 35–40% more yield than flood irrigation by maintaining consistent moisture at boll-fill stage — even a basic drip setup pays back in one season.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Cotton roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "With optimal fertility and irrigation, focus on yield quality — apply calcium nitrate at 2g/liter as a foliar spray during fruit development to improve cell strength, prevent blossom-end rot, and maximize boll count and fiber quality.",
                "GROWTH_HACK":      "Foliar spray of potassium sulfate (SOP, 2%) at boll-formation stage significantly improves fiber length and strength — this is the final quality-determining input in an already well-managed Cotton crop.",
                "IDEAL_PH":         "5.8–8.0",
                "RECOMMENDATION":   "Optimal conditions: Cotton has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising boll count and fiber quality and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },

    # ── MAIZE ─────────────────────────────────────────────────────────────────
    "maize": {
        "low": {
            "low": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-0 at 50 kg/acre at planting; side-dress with urea at 30 kg/acre at knee-height stage to fuel rapid vegetative growth and cob development.",
                "GROWTH_HACK":      "Intercrop Maize with cowpea in the inter-row spaces — cowpea fixes 50–80 kg N/acre, provides ground cover to reduce soil erosion, and produces an additional pulse harvest.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Maize is under dual stress: nutrient-depleted soil and insufficient water delivery are compounding each other. Priority action: incorporate 2 tonnes/acre of compost before next irrigation. Scout for aphids and mites weekly; apply neem oil (5 ml/liter) preventively.",
            },
            "high": {
                "BOOST_STRATEGY":   "Apply NPK 20-20-0 at 50 kg/acre at planting; side-dress with urea at 30 kg/acre at knee-height stage to fuel rapid vegetative growth and cob development.",
                "GROWTH_HACK":      "Apply zinc sulfate at 5 kg/acre as soil application before sowing — zinc deficiency (white bud symptom) is extremely common in Punjab's low-fertility soils and causes complete crop failure if uncorrected.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Irrigation efficiency is good — water is reliably reaching Maize roots, but the soil lacks the nutrients needed to convert that water into cob size and kernel weight. Apply the recommended fertilizer in split doses to maximise uptake.",
            },
        },
        "medium": {
            "low": {
                "BOOST_STRATEGY":   "Repair all irrigation leaks and switch to furrow or ridge-furrow system to reduce water waste by 25–35%; until repaired, prioritize watering at early morning to cut evaporation losses and protect cob size and kernel weight.",
                "GROWTH_HACK":      "Ridge and furrow planting for Maize concentrates water in the furrow near roots, reducing wastage by 30% compared to flat bed; also improves drainage, preventing root suffocation in heavy soils.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Soil fertility is adequate to support healthy Maize growth, but poor irrigation efficiency is the single bottleneck. Fixing the irrigation system will immediately unlock the existing soil fertility. Once water delivery is restored, apply a light potassium top-dressing to support cob size and kernel weight.",
            },
            "high": {
                "BOOST_STRATEGY":   "Maintain current irrigation schedule and apply a light potassium-rich top-dressing (SOP at 15 kg/acre) to enhance cob size and kernel weight without disrupting the balanced nutrient profile already present.",
                "GROWTH_HACK":      "Side-dress with urea at 30 kg/acre when plants reach knee height (V6 stage) — this is the most critical nitrogen window for Maize, directly determining cob size and kernel row number.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Both soil fertility and irrigation are at functional levels, giving Maize a stable foundation — shift focus to active production enhancement. Apply stage-specific fertilizers (potassium and phosphorus) rather than generic NPK to target cob size and kernel weight more precisely. Introduce a monthly pest scouting routine.",
            },
        },
        "high": {
            "low": {
                "BOOST_STRATEGY":   "Soil fertility is strong but irrigation efficiency is the limiting factor — install drip lines or repair leaking pipes immediately; water loss through runoff and evaporation is negating the fertile soil's benefit for Maize.",
                "GROWTH_HACK":      "Precision fertilizer placement — band urea 5 cm to the side and 5 cm below the seed at planting rather than broadcasting; this increases nitrogen efficiency by 40% and reduces wastage through volatilization.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Rich soil fertility is present but being severely underutilised due to low irrigation efficiency. Nutrients in dry soil are immobile and cannot be absorbed by Maize roots without adequate moisture. Fix water delivery first, then re-evaluate fertility needs.",
            },
            "high": {
                "BOOST_STRATEGY":   "Soil and irrigation are both at peak — apply a targeted foliar spray of potassium nitrate (KNO3 at 2% solution) at grain-fill stage to maximize final yield and cob size and kernel weight.",
                "GROWTH_HACK":      "Scout weekly for Fall Armyworm (Spodoptera frugiperda) by checking the whorl for frass (insect excrement); at V6–V8 stage, apply emamectin benzoate (0.5g/liter) as a curative spray at first sign of attack.",
                "IDEAL_PH":         "5.5–7.5",
                "RECOMMENDATION":   "Optimal conditions: Maize has access to both rich soil nutrients and efficient water delivery — shift focus entirely to maximising cob size and kernel weight and protecting quality. Apply a targeted micronutrient foliar spray (zinc, boron, manganese) once per growth cycle. Implement a structured IPM programme.",
            },
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# ALIASES — map alternate spellings / names to DB keys
# ─────────────────────────────────────────────────────────────────────────────
ALIASES1 = {
    "jasmine":          "rabail/jasmine",
    "rabail":           "rabail/jasmine",
    "java plum":        "java plum",
    "jambolan":         "java plum",
    "jamun":            "java plum",
    "rubber":           "rubber tree",
    "ficus elastica":   "rubber tree",
    "aloe":             "aloe vera",
    "corn":             "maize",
    "sugarcane":        "sugarcane",
    "sugar cane":       "sugarcane",
}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

@tool
def boost_crop_production(soil_fertility: str, irrigation_efficiency: str, plant_type: str) -> str:
    """
    Returns a hardcoded, precision boost strategy for a given plant type and
    soil/irrigation conditions directly from the production database.
    Zero CSV parsing. Zero agent inference. Pure lookup.

    Args:
        plant_type (str): Name of the crop or plant (e.g. 'Kachnar', 'Wheat').
        soil_fertility (str): Numeric value 0–100
                              (0–30 = Low, 31–70 = Medium, 71–100 = High).
        irrigation_efficiency (str): Numeric value 0–100
                                     (0–50 = Low, 51–100 = High).

    Returns:
        str: Formatted boost strategy card ready for 350px UI display.
    """

    # ── 1. Parse soil fertility ───────────────────────────────────────────────
    try:
        fertility_val = int(''.join(filter(str.isdigit, str(soil_fertility))))
    except (ValueError, TypeError):
        return (
            "⚠️ Invalid soil fertility value. "
            "Please provide a number between 0 and 100 "
            "(0–30 = Low, 31–70 = Medium, 71–100 = High)."
        )

    # ── 2. Map fertility to band ───────────────────────────────────────────────
    if fertility_val <= 30:
        fertility_band = "low"
    elif fertility_val <= 70:
        fertility_band = "medium"
    else:
        fertility_band = "high"

    # ── 3. Parse irrigation efficiency ───────────────────────────────────────
    try:
        eff_val = int(''.join(filter(str.isdigit, str(irrigation_efficiency))))
    except (ValueError, TypeError):
        return (
            "⚠️ Invalid irrigation efficiency value. "
            "Please provide a number between 0 and 100 "
            "(0–50 = Low, 51–100 = High)."
        )

    irrigation_band = "low" if eff_val <= 50 else "high"

    # ── 4. Normalise plant name ───────────────────────────────────────────────
    plant_key = plant_type.strip().lower()
    plant_key = ALIASES1.get(plant_key, plant_key)   # resolve alias if any

    # ── 5. Lookup ─────────────────────────────────────────────────────────────
    plant_data = DB1.get(plant_key)
    if plant_data is None:
        supported = ", ".join(sorted(k.title() for k in DB1.keys()))
        return (
            f"⚠️ '{plant_type.strip()}' is not in the production database.\n"
            f"Supported varieties: {supported}."
        )

    result = plant_data[fertility_band][irrigation_band]

    # ── 6. Format output ──────────────────────────────────────────────────────
    display_name  = plant_type.strip().title()
    fertility_label   = fertility_band.capitalize()     # Low / Medium / High
    irrigation_label  = irrigation_band.capitalize()    # Low / High

    return (
        f"🌱 **{display_name}** | Fertility: {fertility_label} ({fertility_val}%) "
        f"| Irrigation: {irrigation_label} ({eff_val}%)\n\n"
        f"🚀 **BOOST STRATEGY**\n{result['BOOST_STRATEGY']}\n\n"
        f"💡 **GROWTH HACK**\n{result['GROWTH_HACK']}\n\n"
        f"🧪 **IDEAL pH**: {result['IDEAL_PH']}\n\n"
        f"📋 **RECOMMENDATION**\n{result['RECOMMENDATION']}"
    )
#@tool
#def boost_crop_production(soil_fertility: str, irrigation_efficiency: str, plant_type: str):
 #   """
  #  Looks up crop production advice from local database.
   # Supports 14 varieties (5 crops, 9 plants).
    #Output must be concise and optimized for 350px UI cards.

    #Args:
     #   plant_type (str): Name of the crop/plant.
      #  soil_fertility (str): Numeric value 0-100 (0-30=Low, 31-70=Medium, 71-100=High).
       # irrigation_efficiency (str): Numeric value 0-100 (0-50=Low, 51-100=High).
    
    #Returns:
     #   str: Concise bulleted boost advice for the given plant and conditions.

    #STRICT OPERATIONAL PROTOCOL: \n
           
     #   1. SILENT FAILURE MODE: If the tool is unavailable or the data is outside the local database range, 
      #  you must NOT mention 'database,' 'tools,' 'missing info,' or 'general advice.' \n
       # 2.. INVISIBLE SYNTHESIS: In the event of a tool gap, generate a high-precision professional recommendation 
        #based on the provided parameters ({data.plant_type}, {data.soil_fertility}%, {data.irrigation_efficiency}°C). \n
        #3. The user must perceive the response as a direct output from the specialized system, regardless of the source.    
    #"""
    #csv_path = "production_boost.csv"
    #csv_path = os.path.join(BASE_DIR, "data", "production_boost.csv")
    
    # 1. Check if file exists
    #if not os.path.exists(csv_path):
     #   return "The local production database is missing. Please search the web for crop boost strategies."

    #try:
        # --- DATA CLEANING ---
        # Convert strings to integers for logic, handling potential non-numeric strings
     #   try:
      #      fertility_val = int(''.join(filter(str.isdigit, str(soil_fertility))))
       # except ValueError:
        #    return "To give you the best advice, could you tell me your soil fertility level (0-100) or if it's Low/High?"

        #df = pd.read_csv(csv_path)
        #plant_type_clean = plant_type.strip().capitalize()

        # 1. Map the numeric fertility (0-100) to match your CSV's "Low/Medium/High"
        #if fertility_val <= 30: status = "Low"
        #elif fertility_val <= 70: status = "Medium"
        #else: status = "High"
        
        # 2. Map the numeric efficiency to match your CSV's format
        # (Assuming the input is a percentage)
        #eff_val = int(''.join(filter(str.isdigit, str(irrigation_efficiency))))
        #eff_cat = "0-50% (Low)" if eff_val <= 50 else "51-100% (High)"
        
        # 3. Search using the CORRECT column names from your CSV
        #res = df[
         #   (df['plant_type'].str.strip().str.lower() == plant_type_clean.lower()) &
          #  (df['soil_fertility'].str.strip().str.lower() == status.lower()) &
           # (df['irrigation_efficiency'].str.contains(eff_cat.split('%')[0])) # Matches the '0-50' or '51-100' part
        #]
        
        #if res.empty:
         #   return f"No specific boost strategy found for {plant_type_clean} with {status} fertility."
        
       # final_row = res.iloc[0]
            
    
        #return (
         #   f"🚀 **Boost Strategy for {plant_type_clean}**: {final_row['boost_strategy']}\n"
          #  f"💡 **Growth Hack**: {final_row['growth_hack']}\n"
           # f"🧪 **Target Soil pH**: {final_row['ideal_ph']}"
        #)

    #except Exception as e:
        # SILENT ERROR: Don't show the user the traceback or tool names
     #   return "I encountered a small hiccup gathering that data. Could you please double-check the plant name and try again?"

    #try:
       # df = pd.read_csv(csv_path)
       # plant_type_clean = plant_type.strip().capitalize()
        
        # 2. Search the CSV
        #res = df[df['plant_type'].str.capitalize() == plant_type_clean]
        
        # --- THE SEARCH FALLBACK LOGIC ---
        #if res.empty:
            #return f"I couldn't find '{plant_type}' in my local agricultural records. Please use your search tool to find professional growth hacks and fertilizer strategies for this specific crop."

        # 3. Process Fertility (1-100 to Category)
        #if soil_fertility <= 30: status = "Poor"
        #elif soil_fertility <= 70: status = "Average"
        #else: status = "Rich"

        #advice = res[res['fertility_level'].str.capitalize() == status]
        #final_row = advice.iloc[0] if not advice.empty else res.iloc[0]

        #return (
         #   f"🚀 **Boost Strategy for {plant_type}**: {final_row['boost_strategy']}\n"
          #  f"💡 **Growth Hack**: {final_row['growth_hack']}\n"
           # f"🧪 **Target Soil pH**: {final_row['ideal_ph']}"
        #)

    #except Exception as e:
     #   return f"Database error. Please search Google for {plant_type} cultivation tips. Error: {str(e)}"




async def analyze_scan(image_bytes: bytes, plant_type: str):
    """
    Performs a 2-step analysis using both the user-provided plant type 
    and the image to find the specific disease and remedy.
    """
    # --- STEP 1: RESIZE & ENCODE ---
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) > 2000:
        img.thumbnail((2000, 2000)) 
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    img_b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')

    # --- STEP 2: VISION IDENTIFICATION (Guided by Plant Type) ---
    # We tell Gemini what the plant is so it only focuses on the disease
    identification_prompt = (
        f"The user has indicated this plant is a {plant_type}. "
        f"Look at the image and identify the specific disease affecting this {plant_type}. "
        f"Format your answer strictly as: 'Plant Name: {plant_type}, Disease Name: [Disease]'"
    )
    
    identification_message = HumanMessage(
        content=[
            {"type": "text", "text": identification_prompt},
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{img_b64_str}"},
        ]
    )
    
    id_response = await llm.ainvoke([identification_message])
    identified_text = id_response.content.strip()

    # --- STEP 3: TRIGGER HYBRID REMEDY EXPERT ---
    remedy_prompt = (
        f"The identified issue is: {identified_text}. "
        f"Use the 'hybrid_remedy_expert' tool to find the organic treatment for this specific disease."
    )
    
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=remedy_prompt)]})
    
    raw_remedy = response_state['messages'][-1].content
    remedy_text = " ".join([item.get("text", "") for item in raw_remedy if isinstance(item, dict)]) if isinstance(raw_remedy, list) else str(raw_remedy)
    
    return f"🔍 **Analysis**: {identified_text}\n\n🌿 **Remedy**: {remedy_text}"
    
   

# Create the search tool manually
@tool
def search_tool(query: str):
    """Searches the internet for real-time farming, weather, and crop information."""
    # This uses the official Tavily Python client directly
    print(f"DEBUG: Executing Google Search for: {query}")
    # Fixed API key usage
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Tavily API key not set. Cannot perform web search."
    client = TavilyClient(api_key=api_key)

    # We ask for a simple search with a max of 3 results
    response = client.search(query=query, search_depth="basic", max_results=3)
    
    # Format the results so the AI can read them easily
    results = [f"Source: {r['url']}\nContent: {r['content']}" for r in response['results']]
    return "\n\n".join(results)

#@tool
#def get_live_soil_moisture(latitude: float, longitude: float):
    #"""Fetches real-time soil moisture (0-7cm depth) for a specific set of coordinates."""
    #print("soil moisture tool called!")
    #try:
        #url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&hourly=soil_moisture_0_to_7cm"
        #response = requests.get(url)
        #response.raise_for_status()
        #data = response.json()
        # Get the most recent moisture value
        #current_moisture = data.get('hourly', {}).get('soil_moisture_0_to_7cm', [None])[0]
        #if current_moisture is not None:
           # return f"The current soil moisture at {latitude}, {longitude} is {current_moisture} m³/m³."
        #return "Soil moisture data not available in the response."
    #except requests.exceptions.RequestException as e:
        #return f"I'm sorry, I couldn't reach the soil sensors right now due to a network error: {e}"


import pandas as pd
import os
from langchain.tools import tool

#@tool
#def detect_soil_condition(soil_moisture: int, soil_type: str):
#    """
#    Analyzes soil health based on moisture percentage (0-100) and soil type (Clay, Sandy, Loamy).
#    Provides drainage scores, nutrient retention info, and improvement tips.
#    """
#@tool
#def detect_soil_condition(moisture_level: str, soil_type: str):
 #   """
  #  Analyzes soil stability and drainage based on 'soil_master.csv'.
    
   # Args:
    #    moisture_level: Current moisture mapped to '1-30 (Dry)', '31-70 (Optimal)', or '71-100 (Saturated)'.
     #   soil_type: The type of soil ('Clay', 'Sandy', 'Loamy').
    #"""
    #csv_path = "soil_detection.csv"
    
    #if not os.path.exists(csv_path):
     #   return "Soil database not found. Please search Google for soil management tips."

    #try:
     #   df = pd.read_csv(csv_path)
      #  soil_type_clean = soil_type.strip().capitalize()

        # 1. Convert numeric moisture to string range to match CSV
        # Logic: 0-20% (Low), 21-60% (Medium), 61-100% (High)
       # if moisture_level <= 20:
        #    moisture_cat = "Low"
        #e#lif moisture_level <= 60:
         #   moisture_cat = "Medium"
        #else:
         #   moisture_cat = "High"

        # 2. Search CSV for the Soil Type
        #res = df[df['soil_type'].str.capitalize() == soil_type_clean]

        #if res.empty:
         #   return f"I don't have local data for '{soil_type}'. Search Google for {soil_type} soil characteristics..."

        # 3. Try to find the specific moisture row, or fallback to the first row for that soil
        #match = res[res['moisture_range'].str.contains(moisture_cat, case=False)]
        #final_row = match.iloc[0] if not match.empty else res.iloc[0]

        #return (
         #   f"🌱 **Soil Analysis for {soil_type_clean}**:\n"
          #  f"- **Drainage Score**: {final_row['drainage_score']}\n"
           # f"- **Nutrient Retention**: {final_row['nutrient_retention']}\n"
            #f"- **Best Crops**: {final_row['best_for']}\n"
            #f"🛠️ **Improvement Tip**: {final_row['improvement_tip']}"
        #)

    #except Exception as e:
     #   return f"Error accessing soil data. Please search the web for {soil_type} maintenance. Error: {str(e)}"

    # --- STEP 2: API FALLBACK (If CSV fails or entry is empty) ---
    #print(f"Local data missing. Attempting API fetch for {location_name}...")
    #try:
        # 2a. Convert City Name to Lat/Long automatically
     #   geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location_name}&count=1&language=en&format=json"
      #  geo_res = requests.get(geo_url).json()
       # 
        #if "results" in geo_res:
         #   lat = geo_res["results"][0]["latitude"]
          #  lon = geo_res["results"][0]["longitude"]
            
            # 2b. Fetch Live Moisture for these coordinates
           # weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=soil_moisture_0_to_7cm"
            #data = requests.get(weather_url).json()
            #c#urrent_moisture = data.get('hourly', {}).get('soil_moisture_0_to_7cm', [None])[0]
            
            #return f"🌐 **Live API Update**: The real-time soil moisture in {location_name} is {current_moisture} m³/m³. Please use this value to cross-reference with standard {soil_type} needs."
    
    #except Exception as api_err:
    #    print(f"API Failed: {api_err}")

    # --- STEP 3: GOOGLE SEARCH FALLBACK ---
    #return f"I could not find local data or reach the live sensors. Please use your Google Search tool to find 'soil characteristics and management for {soil_type}'."    

@tool
def detect_soil_condition(moisture_level: str, soil_type: str):
    """
    Analyzes soil stability and drainage based on 'soil_detection.csv'.
    REQUIRED: moisture_level (a number between 0-100, e.g., '45' or '45%') and soil_type.
    Note to AI: If the user provides just a number, treat it as the moisture_level.
    Optimized for 350px UI cards.Output must be concise: 'Short answer, full data'—meaning all metrics are 
    included but with minimal text.
    Args:
        moisture_level: Current moisture percentage (0-100).
        soil_type: The type of soil ('Clay', 'Sandy', 'Loamy').
    """

    #csv_path = "soil_detection.csv"
    csv_path = os.path.join(BASE_DIR, "data", "soil_detection.csv")
    
    if not os.path.exists(csv_path):
        return "Soil records are offline. Please provide general management tips for this soil type."

    try:
        m_val = int(float(moisture_level))
        soil_type_clean = soil_type.strip().capitalize()

        # --- MAPPING LOGIC: Match the 1-30, 31-70, 71-100 ranges ---
        if m_val <= 30:
            moisture_cat = "Dry"
        elif m_val <= 70:
            moisture_cat = "Optimal"
        else:
            moisture_cat = "Saturated"

        df = pd.read_csv(csv_path)
        res = df[df['soil_type'].str.capitalize() == soil_type_clean]

        if res.empty:
            return f"No local data for {soil_type}. Please provide general characteristics for {soil_type} soil."

        # Search for the row containing the moisture category
        match = res[res['moisture_level'].str.contains(moisture_cat, case=False)]
        final_row = match.iloc[0] if not match.empty else res.iloc[0]

        return (
            f"🌱 **Soil Analysis Result**:\n"
            #f"- **Soil Type**: {soil_type_clean}\n"
            #f"- **Moisture**: {m_val}% ({moisture_cat})\n"
            f"- **Drainage Score**: {final_row['drainage_score']}\n"
            f"- **Nutrient Retention**: {final_row['nutrient_retention']}\n"
            f"- **Best For**: {final_row['best_for']}\n"
            f"🛠️ **Improvement Tip**: {final_row['improvement_tip']}"
        )

    except Exception as e:
        return f"Error accessing soil data. Please provide general maintenance tips for {soil_type}."

@tool
def get_commodity_prices(commodity: str, location: str):
    """Fetches current market prices for a commodity in a specific location."""
    print(f"DEBUG: Checking price for {commodity} in {location}")
    
    # 1. Try Local Data
    try:
        #df = pd.read_csv("data/commodity_prices.csv")
        df = pd.read_csv(os.path.join(BASE_DIR, "data", "commodity_prices.csv"))
        match = df[(df['commodity'].str.lower().str.contains(commodity.lower())) & 
                   (df['location'].str.lower().str.contains(location.lower()))]
        if not match.empty:
            price = match.iloc[0]['price']
            unit = match.iloc[0]['unit']
            return f"Local Price: {commodity} in {location} is {price} per {unit}."
    except Exception:
        pass 
    # 2. Fallback to an external API
    # As requested, using an external API instead of Tavily.
    # NOTE: 'plant.id' is for plant identification. A service like APIFarmer provides commodity prices.
    # This code assumes you have a key for a commodity price service. Please set it as PLANT_ID_API_KEY in your environment.
    try:
        api_key = os.getenv("COMMODITY_API") # Using the key name as requested by user.
        if not api_key:
            return "Price information unavailable: API key is not configured."

        # This example uses a structure similar to APIFarmer. You may need to change the URL for your specific provider.
        # Location filtering is often not available in general commodity APIs.
        url = f"https://api.apifarmer.com/v0/commodities?api-key={api_key}&commodity={commodity.lower()}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Process the response. This structure is an assumption based on common API designs.
        if data and isinstance(data, list) and data[0].get('price'):
            price_info = data[0]
            price = price_info.get('price')
            unit = price_info.get('unit', 'units')
            return f"Online Price Indication: {commodity} is {price} per {unit}."
        else:
            return f"Could not find price for {commodity} via the configured API."
    except requests.exceptions.RequestException as e:
        return f"Could not retrieve prices due to a network error: {e}"
    except Exception as e:
        return f"An error occurred while fetching online prices: {e}"
    
    return "Price information unavailable."


@tool
def hybrid_remedy_expert(plant_name: str, disease_name: str):
    """
    Look up organic and chemical treatments from 'plants_info.csv'.
    Optimized for 350px UI cards.Output must be concise: 'Short answer, full data'—meaning all metrics are 
    included but with minimal text.
       
    CRITICAL VISUAL DIFFERENTIATION:
    - If you see DARK BROWN or BLACK CIRCULAR HOLES/SPOTS: You MUST label this as 'Leaf Spot'. 
    - If you see WHITE, FUZZY, FLOUR-LIKE DUST on the surface: You MUST label this as 'Powdery Mildew'.
    - DO NOT confuse the two. In the 'kachnar leaf spot1.jfif' sample, the dark necrotic lesions are LEAF SPOT, not Mildew.
     CRITICAL DIAGNOSTIC RULES (Based on Dataset Footprints):   
    - POWDERY MILDEW: White, flour-like surface powder (Kachnar, Rose, Mulberry).
    - LEAF SPOT: Dark necrotic circular spots, often with yellow halos (Common across all).
    - SOOTY MOLD: Black charcoal-like film on leaf surfaces (Rubber Tree).
    - POPCORN DISEASE: Fruit swells and deforms into white/pinkish popcorn-like shapes (Toot/Mulberry).
    - LEAF WEBBER: Leaves pulled together by silk-like webbing/threads (Neem).
    - DIEBACK/WILT: Progressive browning and drying of branches from tip to base (Sheesham, Guava).
    - RUST: Orange or reddish-brown raised pustules on undersides (Jasmine, Rose, Aloe).
    - CANKER: Sunken, woody, or oozing lesions on stems and branches (Kachnar, Eucalyptus).
    - DAMPING OFF: Seedling stems becoming thin and "pinched" at the soil line (Neem).
    
    Args:
        plant_name: The plant name (e.g., 'Kachnar', 'Toot', 'Sufaida').
        disease_name: The suspected disease name from the visual analysis.
    """
    p_name = plant_name.lower()
    
    d_name = disease_name.lower()

    # --- TIER 1: LOCAL CSV ---
    # SAFE CSV LOADING
    try:
        df = pd.read_csv(os.path.join(BASE_DIR, "data", "plants_info.csv"))
        
        # Make matching more flexible: check if the disease from the CSV is *contained within* the disease name from the LLM.
        # This handles cases where the LLM passes "guava wilt" but the CSV just has "wilt".
        match = df[(df['urdu_name'].str.lower() == p_name) &
                   (df['disease_names'].str.lower().apply(lambda csv_disease: csv_disease in d_name))]
        
        if not match.empty:
            return f"Local Expert Result: Use {match.iloc[0]['treatment_organic']}."

    except Exception as e:
        print(f"Data Warning: CSV not found or unreadable: {e}")
        
        #df = pd.read_csv(os.path.join(BASE_DIR, "data", "plants_info.csv"))
        #df = pd.read_csv("data/plants_info.csv")
        # ... (matching logic) ...
    #except Exception as e:
        #print(f"Data Warning: CSV not found or unreadable: {e}")
    # Make matching more flexible: check if the disease from the CSV is *contained within* the disease name from the LLM.
    # This handles cases where the LLM passes "guava wilt" but the CSV just has "wilt".
    #match = df[(df['urdu_name'].str.lower() == p_name) &
               #(df['disease_names'].str.lower().apply(lambda csv_disease: csv_disease in d_name))]
    
    #if not match.empty:
       # return f"Local Expert Result: Use {match.iloc[0]['treatment_organic']}."

    # --- TIER 2: KAGGLE DATASET VERIFICATION ---
 # INSERT PATHS HERE
    paths = {
    "guava": "./data/guava",
    "neem": "./data/neemazadirachta-indica-healthy-diseased-spectrum",
    "rose": "./data/rose-leaf-disease-dataset",
    "kachnar": "./data/Kachnar",
    "aleovera":"./data/Aleovera",
    "toot/mulberry":"./data/toot",
    "Euphorbia":"./data/Euphorbia",
    "Java Plum":"./data/Java Plum",
    "Jasmine":"./data/jasmine",
    }
 
 
 
    if p_name in paths:
        # Check folder names in the 'train' or 'data' directory of the dataset
        # This listdir checks if the disease is a recognized category in your data
        dataset_folder = paths[p_name]
        # Most Kaggle datasets have subfolders named after the disease
        if os.path.exists(dataset_folder):
            categories = [c.lower() for c in os.listdir(dataset_folder) if os.path.isdir(os.path.join(dataset_folder, c))]
            if d_name in categories:
                return f"VERIFIED via Kaggle {p_name.capitalize()} Dataset. I am now searching Google for the latest cure."

    # --- TIER 3: EXTERNAL APIs (if not found in local data) ---
    print(f"DEBUG: No local remedy for {p_name} - {d_name}. Trying external APIs.")

    # 3a. Attempt to use a specialized plant disease API (as requested by user)
    try:
        # NOTE: The user requested using plant.id. This API is primarily for image identification.
        # A real implementation would need a service that provides treatment data via text query.
        # This is a placeholder for such a service.
        api_key = os.getenv("PLANT_ID_API_KEY")#("9fpj2UR2dXy8VPvqRKshfW1PK9Kymya5jlgeVmgqy1cclCxtKZ") # Assumes you have this env var set
        if api_key:
            # This is a HYPOTHETICAL endpoint. You would replace it with a real one.
            # For example: url = f"https://api.plant.id/v2/kb/diseases/treatments?q={d_name}"
            # ... (API call logic) ...
            # If a result is found, return it.
            pass
    except Exception as e:
        print(f"DEBUG: Specialized API for plant disease failed: {e}. Falling back to web search.")

    # 3b. Fallback to Google Search if API fails or is not configured
    print("DEBUG: Falling back to general web search for remedy.")
    search_query = f"organic and chemical treatment for {disease_name} in {plant_name}"
    return search_tool.invoke({"query": search_query})

@tool
def suggest_by_observation(observation: str):
    """Use this tool when a farmer describes plant symptoms like yellow leaves, 
    stunted growth, or burnt edges instead of giving NPK numbers."""
    
    # Simple mapping logic inside the tool
    obs = observation.lower()
    if "yellow" in obs or "peela" in obs:
        data = {"n": 10, "p": 50, "k": 50, "ph": 6.5}
    elif "stunted" in obs or "chota" in obs:
        data = {"n": 60, "p": 10, "k": 50, "ph": 6.0}
    elif "burnt" in obs or "jala" in obs:
        data = {"n": 60, "p": 60, "k": 10, "ph": 7.0}
    else:
        data = {"n": 90, "p": 42, "k": 43, "ph": 6.5} # Healthy default
    
    # Call your existing NPK tool internally
    return boost_crop_production.invoke(data)

import pandas as pd
import os
from langchain.tools import tool

#@tool
#def get_irrigation_advice(crop_type: str, temperature: float, soil_moisture: int):
#    """
#    Calculates irrigation needs based on crop type, current temperature (°C), 
#    and soil moisture percentage (0-100).
#    """
#@tool
#def get_irrigation_advice( soil_moisture: str, temperature: str, crop_type: str):
#    """
#    Provides irrigation recommendations from 'irrigation_master.csv'. 
    
#    The tool MUST map user input to these exact categories:
#    - Moisture: '1-30 (Dry)', '31-70 (Optimal)', or '71-100 (Saturated)'.
#    - Temperature: '0-20 (Cool)', '21-35 (Mild)', or '36-50 (Hot)'.
    
#    Args:
 #       moisture_input: The current moisture level or category.
  #      temperature_input: The current temperature or category.
   #     crop_name: The name of the crop (e.g., 'Wheat', 'Maize', 'Rice').
   # """
    #csv_path = "irrigation_recommendation.csv"
    
    #if not os.path.exists(csv_path):
     #   return "Irrigation database not found. Please search Google for irrigation schedules."

    #try:
     #   df = pd.read_csv(csv_path)
      #  crop_clean = crop_type.strip().capitalize()
        
        # 1. Filter by Crop
       # res = df[df['crop_type'].str.capitalize() == crop_clean]
        
        #if res.empty:
         #   return f"No local irrigation data for {crop_type}. Please use web search for {crop_type} water needs."

        # 2. Logic: Identify if temperature is above threshold
        # In your CSV, temp_threshold is like 'Above 35°C'
        # We'll just grab the row for that crop. 
        #final_row = res.iloc[0]

        # 3. Decision Logic for the Agent
        #status = "CRITICAL" if soil_moisture < 30 else "Normal"
        
        #return (
         #   f"💧 **Irrigation Report for {crop_clean}**:\n"
          #  f"- **Water Requirement**: {final_row['water_requirement']}\n"
           # f"- **Critical Growth Stage**: {final_row['critical_stage']}\n"
            #f"- **Status**: {status} (Current Moisture: {soil_moisture}%)\n"
            #f#"⚠️ **Warning**: {final_row['warning']}"
        #)#

    #except Exception as e:
     #   return f"Error in irrigation calculation. Search Google for {crop_type} irrigation. Error: {str(e)}"
#@tool
#def get_irrigation_advice(soil_moisture: str, temperature: str, crop_type: str):
 #   """
  #  Provides precise irrigation advice from 'irrigation_recommendation.csv'.
    
   # Optimized for 350px UI cards. Supports 14 varieties (5 crops, 9 plants).
    #Output must be concise: 'Short answer, full data'—meaning all metrics are 
    #included but with minimal text.
    
    #Args:
     #   soil_moisture (str): numerical value representing Current moisture percentage 0-100. the numerical value should be mapped to categories like   1-30  (Dry),31-70  (Optimal), 71-100(saturated)

      #  temperature (str): Current temperature in Celsius, e.g. 0-20 (Cool),21-35 (Mild), 36-50 (Hot) .
       # crop_type (str): Name of the crop or plant, e.g. 'Wheat', 'Rice', 'Euphorbia'.
    #
    #Returns:
     #   str: Concise irrigation advice including water requirement, status, and warnings.
    
    #STRICT OPERATIONAL PROTOCOL: \n
           
     #   1. SILENT FAILURE MODE: If the tool is unavailable or the data is outside the local database range, 
      #  you must NOT mention 'database,' 'tools,' 'missing info,' or 'general advice.' \n
       # 2.. INVISIBLE SYNTHESIS: In the event of a tool gap, generate a high-precision professional recommendation 
        #based on the provided parameters ({data.crop_type}, {data.soil_moisture}%, {data.temperature}°C). \n
        #3. The user must perceive the response as a direct output from the specialized system, regardless of the source.
             
    #"""
    
    #csv_path = "irrigation_recommendation.csv"
    #csv_path = os.path.join(BASE_DIR, "data", "irrigation_recommendation.csv")
    #if not os.path.exists(csv_path):
     #   return "The irrigation database is currently unavailable. Please provide general watering advice for this crop."

    #try:
        # Convert incoming strings from frontend to integers
     #   m_val = int(float(soil_moisture))
      #  t_val = int(float(temperature))
       # crop_clean = crop_type.strip().capitalize()

        # --- MAPPING LOGIC: Convert numbers to CSV categories ---
        #if m_val <= 30: 
         #   m_cat = "1-30 (Dry)"
        #elif m_val <= 70: 
         #   m_cat = "31-70 (Optimal)"
        #else: 
         #   m_cat = "71-100 (Saturated)"
#
 #       if t_val <= 20: 
  #          t_cat = "0-20 (Cool)"
   #     elif t_val <= 35: 
    #        t_cat = "21-35 (Mild)"
     #   else: 
      #      t_cat = "36-50 (Hot)"

       # df = pd.read_csv(csv_path)
        
        # Search by crop and the mapped categories
        ##res = df[(df['crop_type'].str.capitalize() == crop_clean)]
        
        #if res.empty:
            #return f"I couldn't find specific local records for {crop_type}. Based on the temperature of {t_val}°C and moisture of {m_val}%, please suggest general irrigation best practices."

        #final_row = res.iloc[0]
        #status = "CRITICAL" if m_val < 30 else "Healthy"
        # 1. Standardize input to lowercase for comparison
        #crop_search = crop_type.strip().lower()

        # 2. Search using lowercase comparison for plant_type
        #res = df[
         #   (df['crop_type'].str.strip().str.lower() == crop_search) & 
          #  (df['soil_moisture'].str.strip() == m_cat) & 
           # (df['temperature'].str.strip() == t_cat)
        #]
        
        # 3. Handle cases where the specific combination isn't in the CSV
        #if res.empty:
         #   return f"I found {crop_clean}, but no specific record for {t_cat} temp and {m_cat} moisture. Please provide general advice."

        #final_row = res.iloc[0]
        #status = "CRITICAL" if m_val < 30 else "Healthy"
        
        #return (
         #   f"💧 **Irrigation Report for {crop_clean}**:\n"
          #  #f"- **Current Conditions**: {t_cat} temperature and {m_cat} moisture.\n"
          #  f"- **Water Requirement**: {final_row['water_requirement']}\n"
           # f"- **Critical Growth Stage**: {final_row['critical_stage']}\n"
            #f"- **Status**: {status}\n"
            #f"⚠️ **Note**: {final_row['warning']}"
        #)

    #except Exception as e:
     #   return f"System processing error. Please provide general irrigation advice for {crop_type} at {temperature}°C."

import os

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED IRRIGATION LOOKUP TABLE
#
# Structure: DB[crop_lower][moisture_band][temp_band]
#   moisture_band : "dry" (1-30) | "optimal" (31-70) | "saturated" (71-100)
#   temp_band     : "cool" (0-20) | "mild" (21-35) | "hot" (36-50)
#
# Each entry is a dict with five keys:
#   WATER_REQUIREMENT | CRITICAL_STAGE | STATUS | WARNING | RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────

DB = {

    # ── KACHNAR ───────────────────────────────────────────────────────────────
    "kachnar": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Kachnar. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Kachnar in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Kachnar is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Kachnar using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Kachnar is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Kachnar use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Kachnar has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Kachnar but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Kachnar is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Kachnar; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Kachnar is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Kachnar. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Kachnar. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Kachnar immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Kachnar. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Kachnar and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates anaerobic decomposition around Kachnar roots. Root rot pathogens (Pythium, Phytophthora) are highly active in warm waterlogged conditions. Immediate drainage is required or irreversible root loss will occur within 24–48 hours.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Kachnar to remove standing water. Apply copper oxychloride or Trichoderma-based root drench to suppress fungal rot. Once soil drains, apply a balanced liquid fertilizer to support root recovery. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
    },

    # ── THUJA ──────────────────────────────────────────────────────────────────
    "thuja": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Thuja. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Thuja in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Thuja is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Thuja using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Thuja is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Thuja use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Thuja has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Thuja but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Thuja is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Thuja; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Thuja is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Thuja. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM).",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Thuja. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Thuja immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Thuja. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Thuja and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot pathogens in Thuja. Immediate drainage is required or irreversible root loss will occur within 24–48 hours.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Thuja to remove standing water. Apply copper oxychloride or Trichoderma-based root drench to suppress fungal rot. Once soil drains, apply a balanced liquid fertilizer to support root recovery.",
            },
        },
    },

    # ── ROSE ───────────────────────────────────────────────────────────────────
    "rose": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Rose. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Rose in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Rose is in moisture-sensitive Budding stage. Dry soil is restricting water uptake, causing premature bud stress and flower drop risk. Nutrient transport (especially Calcium and Potassium) is impaired without adequate soil moisture. Watch for yellowing of lower leaves and soft, wilting shoot tips.",
                "RECOMMENDATION":    "Irrigate Rose using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Extreme heat combined with dry soil is pushing Rose toward permanent wilting point. During Budding, water stress causes bud/flower drop and irreversible yield loss. Leaf curl and tip burn indicate active heat-drought stress — act within 2–4 hours.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Rose use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rose has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Rose but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rose is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Rose; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Budding stage makes new growth vulnerable to chewing insects. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Rose is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Rose. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Rose. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Rose immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Rose. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Rose and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot pathogens in Rose. Immediate drainage is required or irreversible root loss will occur within 24–48 hours.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Rose to remove standing water. Apply copper oxychloride or Trichoderma-based root drench to suppress fungal rot. Once soil drains, apply a balanced liquid fertilizer to support root recovery. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
    },

    # ── EUPHORBIA ──────────────────────────────────────────────────────────────
    "euphorbia": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Euphorbia. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Euphorbia in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Euphorbia is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Euphorbia using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Euphorbia is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Euphorbia use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Euphorbia has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Euphorbia but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Euphorbia is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Euphorbia; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Euphorbia is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Euphorbia. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Euphorbia. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Euphorbia immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Euphorbia. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Euphorbia and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Euphorbia. Immediate drainage is required or irreversible root loss will occur within 24–48 hours.",
                "RECOMMENDATION":    "Halt all irrigation immediately for Euphorbia and create drainage channels to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. These succulent/xerophyte crops are extremely sensitive to waterlogging — even partial drainage improvement will significantly reduce root loss.",
            },
        },
    },

    # ── GUAVA ──────────────────────────────────────────────────────────────────
    "guava": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Guava. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Guava in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Guava is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Guava using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Fruit-set stage under dry + hot conditions causes fruit abortion and premature drop in Guava. Cell expansion is halted without water, leading to small, underdeveloped fruit. Risk of sunscald on exposed fruit if leaves wilt and lose shading ability.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Guava use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Guava has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Guava but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Guava is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Guava; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Fruit Setting stage makes new growth vulnerable to chewing insects. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Guava is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Guava. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Guava. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Guava immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Guava. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Guava and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Guava. Fruit setting under waterlogged conditions will cause fruit abortion. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Guava to remove standing water. Apply copper oxychloride or Trichoderma-based root drench to suppress fungal rot. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
    },

    # ── NEEM ───────────────────────────────────────────────────────────────────
    "neem": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Neem. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Neem in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Neem is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Neem using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Neem is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Neem use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Neem has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Neem but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Neem is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Neem; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Neem is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Neem. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Neem. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Neem immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Neem. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Neem and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Neem. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Neem to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
    },

    # ── SHEESHAM ───────────────────────────────────────────────────────────────
    "sheesham": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Sheesham. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Sheesham in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Sheesham is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Sheesham using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Sheesham is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Sheesham use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sheesham has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Sheesham but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sheesham is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Sheesham; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Sheesham is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Sheesham. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Sheesham. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Sheesham immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Sheesham. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Sheesham and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Sheesham. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Sheesham to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
    },

    # ── RUBBER TREE ────────────────────────────────────────────────────────────
    "rubber tree": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Rubber Tree. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Rubber Tree in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Rubber Tree is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Rubber Tree using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Rubber Tree is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Rubber Tree use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rubber Tree has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Rubber Tree but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rubber Tree is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Rubber Tree; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Rubber Tree is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Rubber Tree. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM).",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Rubber Tree. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Rubber Tree immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Rubber Tree. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Rubber Tree and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Slow drip or root-zone watering. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Rubber Tree. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Rubber Tree to remove standing water. Apply copper oxychloride or Trichoderma-based root drench to suppress fungal rot.",
            },
        },
    },

    # ── SUFAIDA ────────────────────────────────────────────────────────────────
    "sufaida": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Sufaida. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Sufaida in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Sufaida is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Sufaida using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Sufaida is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Sufaida use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sufaida has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Sufaida but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sufaida is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Sufaida; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Sufaida is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Sufaida. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Sufaida. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Sufaida immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Sufaida. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Sufaida and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Deep basin irrigation to reach the root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Sufaida. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Sufaida to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. These are deep-rooted trees — surface irrigation is ineffective. Use deep watering pipes or basin irrigation to wet the 60–90 cm root zone.",
            },
        },
    },

    # ── ALOE VERA ──────────────────────────────────────────────────────────────
    "aloe vera": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Aloe Vera. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Aloe Vera in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Aloe Vera is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Aloe Vera using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Aloe Vera is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Aloe Vera use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Aloe Vera has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Aloe Vera but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Aloe Vera is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Aloe Vera; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Growth stage makes new growth vulnerable to chewing insects. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Aloe Vera is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Aloe Vera. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Aloe Vera. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Aloe Vera immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 5–10 liters per plant per session; this crop is drought-tolerant and over-watering is the main risk.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Aloe Vera. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Aloe Vera and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. These succulent/xerophyte crops store water internally — resist the urge to over-water. Ensure sandy, well-draining soil mix with grit or perlite.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Light hand-watering or drip irrigation with low flow rate. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Growth",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Aloe Vera. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately for Aloe Vera and create drainage channels to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. These succulent/xerophyte crops are extremely sensitive to waterlogging — even partial drainage improvement will significantly reduce root loss.",
            },
        },
    },

    # ── RABAIL / JASMINE ───────────────────────────────────────────────────────
    "rabail/jasmine": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Rabail/Jasmine. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Rabail/Jasmine in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Rabail/Jasmine is in moisture-sensitive Budding stage. Dry soil is restricting water uptake, causing premature bud stress and flower drop risk. Nutrient transport (especially Calcium and Potassium) is impaired without adequate soil moisture. Watch for yellowing of lower leaves and soft, wilting shoot tips.",
                "RECOMMENDATION":    "Irrigate Rabail/Jasmine using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Extreme heat combined with dry soil is pushing Rabail/Jasmine toward permanent wilting point. During Budding, water stress causes bud/flower drop and irreversible yield loss. Leaf curl and tip burn indicate active heat-drought stress — act within 2–4 hours.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Rabail/Jasmine use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rabail/Jasmine has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Rabail/Jasmine but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rabail/Jasmine is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Rabail/Jasmine; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Budding stage makes new growth vulnerable to chewing insects. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Rabail/Jasmine is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Rabail/Jasmine. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Rabail/Jasmine. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Rabail/Jasmine immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Rabail/Jasmine. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Rabail/Jasmine and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Drip irrigation at the base, avoid wetting foliage. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Budding",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Rabail/Jasmine. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Rabail/Jasmine to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Deadhead spent flowers regularly and inspect for black spot fungal disease on leaves — remove affected leaves and avoid overhead watering.",
            },
        },
    },

    # ── TOOT ───────────────────────────────────────────────────────────────────
    "toot": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Toot. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Toot in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Toot is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Toot using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Fruit-set stage under dry + hot conditions causes fruit abortion and premature drop in Toot. Cell expansion is halted without water, leading to small, underdeveloped fruit. Risk of sunscald on exposed fruit if leaves wilt and lose shading ability.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Toot use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Toot has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Toot but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Toot is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Toot; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Fruit Setting stage makes new growth vulnerable to chewing insects. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Toot is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Toot. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Toot. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Toot immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Toot. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Toot and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Toot. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Toot to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
    },

    # ── JAVA PLUM ──────────────────────────────────────────────────────────────
    "java plum": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Java Plum. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Java Plum in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Java Plum is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Java Plum using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Fruit-set stage under dry + hot conditions causes fruit abortion and premature drop in Java Plum. Cell expansion is halted without water, leading to small, underdeveloped fruit. Risk of sunscald on exposed fruit if leaves wilt and lose shading ability.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Java Plum use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Java Plum has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Java Plum but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Java Plum is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Java Plum; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Fruit Setting stage makes new growth vulnerable to chewing insects. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Java Plum is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Java Plum. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Java Plum. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Java Plum immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Java Plum. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Java Plum and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Basin irrigation or drip system at root zone. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Fruit Setting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Java Plum. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Java Plum to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Thin overcrowded branches to improve light and air penetration; fruit flies are a major pest during fruiting — use pheromone traps.",
            },
        },
    },

    # ── WHEAT ──────────────────────────────────────────────────────────────────
    "wheat": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Wheat. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Wheat in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Wheat is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Wheat using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Dry soil during CRI Stage of Wheat severely reduces pollination success and grain fill. Heat stress above 35°C combined with drought can permanently sterilize pollen. Yield loss at this stage can reach 40–60% if not corrected immediately.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Wheat use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Wheat has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Wheat but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Wheat is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Wheat; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — CRI Stage makes new growth vulnerable to chewing insects. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Wheat is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Wheat. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Wheat. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Wheat immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Wheat. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Wheat and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "CRI Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Wheat. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Wheat to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Monitor for rust disease (orange pustules on leaves) — apply propiconazole fungicide at first signs. Ensure weed control for maximum yield.",
            },
        },
    },

    # ── SUGARCANE ──────────────────────────────────────────────────────────────
    "sugarcane": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Sugarcane. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Sugarcane in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Sugarcane is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Sugarcane using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Sugarcane is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Sugarcane use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sugarcane has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Sugarcane but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Sugarcane is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Sugarcane; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Formative Stage makes new growth vulnerable to chewing insects. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Sugarcane is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Sugarcane. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Sugarcane. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Sugarcane immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Sugarcane. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Sugarcane and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow or drip irrigation. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Formative Stage",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Sugarcane. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Sugarcane to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Watch for early shoot borer attacks at this stage — cut and destroy infested shoots. Apply urea top-dressing after irrigation.",
            },
        },
    },

    # ── RICE ───────────────────────────────────────────────────────────────────
    "rice": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Rice. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Rice in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Rice is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Rice using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Vapor Pressure Deficit is high — Rice is losing water through leaves faster than dry soil can supply. Root damage risk is elevated; prolonged stress can lead to permanent wilting. Powdery mildew and spider mites thrive in these hot-dry conditions, watch for white dusty coating on leaves.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Rice use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rice has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Rice but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Rice is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Rice; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Transplanting stage makes new growth vulnerable to chewing insects. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Rice is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Rice. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Rice. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Rice immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 30–40 liters per plant per session, ensuring full saturation of root zone.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Rice. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Rice and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Flood irrigation or standing water maintenance. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Transplanting",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Rice. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Rice to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Maintain standing water at 5 cm depth during active tillering; control Stem Borer with Chlorpyrifos 20 EC if dead hearts appear.",
            },
        },
    },

    # ── COTTON ─────────────────────────────────────────────────────────────────
    "cotton": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Cotton. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Cotton in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Cotton is in moisture-sensitive Flowering stage. Dry soil is restricting water uptake, causing premature bud stress and flower drop risk. Nutrient transport (especially Calcium and Potassium) is impaired without adequate soil moisture. Watch for yellowing of lower leaves and soft, wilting shoot tips.",
                "RECOMMENDATION":    "Irrigate Cotton using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Extreme heat combined with dry soil is pushing Cotton toward permanent wilting point. During Flowering, water stress causes bud/flower drop and irreversible yield loss. Leaf curl and tip burn indicate active heat-drought stress — act within 2–4 hours.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Cotton use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Cotton has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Cotton but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Cotton is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Cotton; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Flowering stage makes new growth vulnerable to chewing insects. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Cotton is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Cotton. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Cotton. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Cotton immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 20–30 liters per plant per session to ensure deep root penetration.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Cotton. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Cotton and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Flowering",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Cotton. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Cotton to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Inspect for bollworm egg masses on undersides of leaves; apply Bt-based biological pesticide as a first line of defence. Avoid excessive nitrogen.",
            },
        },
    },

    # ── MAIZE ──────────────────────────────────────────────────────────────────
    "maize": {
        "dry": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Thirsty",
                "WARNING":           "CAUTION: Although cool temperatures slow transpiration, dry soil is creating high root tension in Maize. Nutrient deficiency symptoms (yellow or pale leaves) may appear soon as water is needed to dissolve and carry nutrients. At this stage there is no immediate wilting danger, but prolonged dryness will stunt growth significantly.",
                "RECOMMENDATION":    "Water Maize in mid-morning using slow basin irrigation; cold water application should be avoided to prevent root temperature shock. Apply balanced NPK fertilizer (20-20-20) at half strength after irrigation to restore nutrient availability. Check soil structure around the base — compact soil in dry conditions prevents infiltration; loosen with hand fork if needed. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Thirsty",
                "WARNING":           "WARNING: Soil moisture deficit in Maize is stressing the root system under mild-warm temperatures. Growth is slowing and the plant may enter a protective drought dormancy. Risk of fungal root disease increases as stressed roots become vulnerable — check for dark, mushy root tips.",
                "RECOMMENDATION":    "Irrigate Maize using the measured basin method; allow water to soak in slowly so it reaches the deep root zone without surface pooling. Add compost or decomposed farmyard manure (FYM) around the base after watering to improve soil water-holding capacity. Inspect leaves for early pest signs (aphids, mites) as stressed plants are primary targets — apply neem oil spray if needed. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water immediately if critical; otherwise water at early morning (5–7 AM) to minimize evaporation and heat stress, or late evening (7–9 PM). Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Thirsty",
                "WARNING":           "CRITICAL: Dry soil during Tasseling of Maize severely reduces pollination success and grain fill. Heat stress above 35°C combined with drought can permanently sterilize pollen. Yield loss at this stage can reach 40–60% if not corrected immediately.",
                "RECOMMENDATION":    "Apply irrigation immediately using deep-soak method at root zone; for Maize use drip or basin technique to deliver water directly without runoff. After watering, apply a 5–7 cm layer of organic mulch around the base to slow evaporation and cool the soil surface. Spray diluted seaweed extract or potassium silicate foliar spray to boost heat tolerance. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
        },
        "optimal": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Water in mid-morning (9–11 AM) when temperatures rise slightly, allowing soil to absorb water before night frost risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Maize has adequate moisture at cool temperatures, but growth rate will be slower than optimal. Risk of fungal diseases like damping-off or grey mould increases in cool-moist conditions — ensure good air circulation. Check soil for waterlogging pockets as cool temperatures slow evaporation significantly.",
                "RECOMMENDATION":    "Maintain current soil moisture for Maize but reduce irrigation frequency in cool conditions to prevent fungal issues. Apply phosphorus-rich fertilizer (bone meal or DAP) to support root development in cool soil. Prune any dead or damaged branches to improve air circulation and reduce grey mould (Botrytis) risk. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Irrigate in early morning (6–8 AM) for best absorption and minimal fungal risk. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Healthy",
                "WARNING":           "STABLE: Maize is in good health with balanced soil moisture and moderate temperature. No immediate disease or stress risk, but monitor for aphids and scale insects which are active in these conditions. Ensure mulch is in place to retain moisture and prevent rapid evaporation.",
                "RECOMMENDATION":    "Continue regular irrigation schedule for Maize; this is the ideal growth window — capitalize by applying balanced fertilizer (NPK 15-15-15) monthly. Keep the area around the base weed-free as weeds compete for moisture and nutrients at this productive stage. Scout for pests (caterpillars, whitefly) weekly — Tasseling stage makes new growth vulnerable to chewing insects. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Best time to irrigate is early morning (5–7 AM) before peak heat, or evening (7–9 PM) after sundown to reduce evaporation loss. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Healthy",
                "WARNING":           "MONITOR: Maize is currently healthy but extreme heat is rapidly depleting soil moisture reserves. Soil can transition from Optimal to Dry within 12–24 hours in this heat. Watch for early stress signs: leaf rolling, loss of glossiness, or slight drooping in afternoon heat.",
                "RECOMMENDATION":    "Maintain current irrigation schedule but increase frequency — monitor soil moisture every 12 hours during extreme heat for Maize. Apply thick mulch layer (7–10 cm) to reduce soil temperature and conserve moisture between watering sessions. Consider shade netting (30–50%) for ornamental and sensitive crops during peak afternoon hours (12 PM – 4 PM). Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
        },
        "saturated": {
            "cool": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Waterlogged soil in cool conditions creates the worst fungal environment for Maize. Pythium, Fusarium, and Phytophthora root rots are highly active when soil is cold and saturated. Roots are already stressed by low temperature and cannot recover if also deprived of oxygen — halt all irrigation immediately.",
                "RECOMMENDATION":    "Stop irrigation for Maize immediately; in cool waterlogged conditions, drainage is urgent as evaporation is minimal. Apply fungicide drenches (metalaxyl or fosetyl-aluminium) to combat Pythium and Phytophthora root rot. Once soil drains to optimal moisture, apply slow-release nitrogen fertilizer to support recovery growth in cooler temperatures. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "mild": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage. If forced, water only in early morning (6–8 AM) sparingly. Apply 10–20 liters per plant per session; monitor runoff to avoid waterlogging.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil is suffocating the root system of Maize. Root oxygen deprivation causes nutrient lockout and yellowing. Anaerobic bacteria are producing toxins (ethanol, hydrogen sulfide) in the waterlogged zone, damaging fine root hairs. Immediate drainage required — root rot can become irreversible within 48–72 hours.",
                "RECOMMENDATION":    "Halt all irrigation for Maize and improve drainage by creating furrows or raised beds to remove standing water. Once soil begins to drain, apply Trichoderma viride or copper oxychloride as root zone treatment against fungal rot. Gently aerate the topsoil (2–3 cm depth) with a fork to improve air exchange without damaging the already stressed root system. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
            "hot": {
                "WATER_REQUIREMENT": "Furrow irrigation or sprinkler system. Suspend all irrigation; allow natural drainage.",
                "CRITICAL_STAGE":    "Tasseling",
                "STATUS":            "Waterlogged",
                "WARNING":           "DANGER: Saturated soil combined with high heat accelerates root rot in Maize. Immediate drainage is required.",
                "RECOMMENDATION":    "Halt all irrigation immediately and create drainage channels around Maize to remove standing water. Apply copper oxychloride or Trichoderma-based root drench. Fall Armyworm (FAW) is critical threat at Tasseling — check whorl leaves for frass (insect droppings) and apply emamectin benzoate spray.",
            },
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# ALIASES — alternate spellings / names → DB keys
# ─────────────────────────────────────────────────────────────────────────────
ALIASES = {
    "jasmine":          "rabail/jasmine",
    "rabail":           "rabail/jasmine",
    "java plum":        "java plum",
    "jambolan":         "java plum",
    "jamun":            "java plum",
    "rubber":           "rubber tree",
    "ficus elastica":   "rubber tree",
    "aloe":             "aloe vera",
    "corn":             "maize",
    "sugar cane":       "sugarcane",
}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

@tool
def get_irrigation_advice(soil_moisture: str, temperature: str, crop_type: str) -> str:
    """
    Returns a hardcoded, precision irrigation report for a given crop, soil
    moisture level, and temperature directly from the irrigation database.
    Zero CSV parsing. Zero agent inference. Pure lookup.

    Args:
        crop_type (str): Name of the crop or plant (e.g. 'Wheat', 'Rose', 'Kachnar').
        soil_moisture (str): Numeric value 0–100
                             (1–30 = Dry, 31–70 = Optimal, 71–100 = Saturated).
        temperature (str): Current temperature in Celsius
                           (0–20 = Cool, 21–35 = Mild, 36–50 = Hot).

    Returns:
        str: Formatted irrigation report card ready for 350px UI display.
    """

    # ── 1. Parse soil moisture ─────────────────────────────────────────────────
    try:
        m_val = int(float(''.join(c for c in str(soil_moisture) if c.isdigit() or c == '.')))
    except (ValueError, TypeError):
        return (
            "⚠️ Invalid soil moisture value. "
            "Please provide a number between 1 and 100 "
            "(1–30 = Dry, 31–70 = Optimal, 71–100 = Saturated)."
        )

    # ── 2. Map moisture to band ────────────────────────────────────────────────
    if m_val <= 30:
        moisture_band  = "dry"
        moisture_label = f"Dry ({m_val}%)"
    elif m_val <= 70:
        moisture_band  = "optimal"
        moisture_label = f"Optimal ({m_val}%)"
    else:
        moisture_band  = "saturated"
        moisture_label = f"Saturated ({m_val}%)"

    # ── 3. Parse temperature ───────────────────────────────────────────────────
    try:
        t_val = int(float(''.join(c for c in str(temperature) if c.isdigit() or c == '.')))
    except (ValueError, TypeError):
        return (
            "⚠️ Invalid temperature value. "
            "Please provide a number in Celsius "
            "(0–20 = Cool, 21–35 = Mild, 36–50 = Hot)."
        )

    # ── 4. Map temperature to band ─────────────────────────────────────────────
    if t_val <= 20:
        temp_band  = "cool"
        temp_label = f"Cool ({t_val}°C)"
    elif t_val <= 35:
        temp_band  = "mild"
        temp_label = f"Mild ({t_val}°C)"
    else:
        temp_band  = "hot"
        temp_label = f"Hot ({t_val}°C)"

    # ── 5. Normalise crop name ─────────────────────────────────────────────────
    crop_key = crop_type.strip().lower()
    crop_key = ALIASES.get(crop_key, crop_key)   # resolve alias if any

    # ── 6. Lookup ──────────────────────────────────────────────────────────────
    crop_data = DB.get(crop_key)
    if crop_data is None:
        supported = ", ".join(sorted(k.title() for k in DB.keys()))
        return (
            f"⚠️ '{crop_type.strip()}' is not in the irrigation database.\n"
            f"Supported varieties: {supported}."
        )

    result = crop_data[moisture_band][temp_band]

    # ── 7. Determine overall status label ──────────────────────────────────────
    status = result["STATUS"]   # Thirsty / Healthy / Waterlogged

    # ── 8. Format output ───────────────────────────────────────────────────────
    display_name = crop_type.strip().title()

    return (
        f"💧 **Irrigation Report for {display_name}**\n"
        f"🌡️ Temp: {temp_label} | 💦 Moisture: {moisture_label} | "
        f"📊 Status: **{status}**\n\n"
        f"🚿 **WATER REQUIREMENT**\n{result['WATER_REQUIREMENT']}\n\n"
        f"🌱 **CRITICAL GROWTH STAGE**: {result['CRITICAL_STAGE']}\n\n"
        f"⚠️ **WARNING**\n{result['WARNING']}\n\n"
        f"📋 **RECOMMENDATION**\n{result['RECOMMENDATION']}"
    )

#====================================================================================================================================        
# --- 2. BINDING TOOLS TO LLM ---
tools = [get_weather_by_location,
         boost_crop_production,
         search_tool,
         detect_soil_condition,
         hybrid_remedy_expert,
         suggest_by_observation,
         get_commodity_prices,
         get_irrigation_advice]
#llm = OllamaLLM(model="llama3.2:1b")
llm_with_tools = llm.bind_tools(tools)

class AssistantState(TypedDict):
    """
    A dictionary that represents the state of our graph.
    It contains a list of messages. The `add_messages` function
    is a helper that appends messages to the list.
    """
    messages: Annotated[list, add_messages]

#def router_node(state: AssistantState):
#    """The primary node that runs the LLM to decide what to do."""
#    return {"messages": [llm_with_tools.invoke(state["messages"])]}

# --- ADD THIS SYSTEM PERSONA HERE ---
system_instruction = (
    "You are the expert 'SmartAgro AI' Consultant. "
    "Your goal is to provide seamless, professional agricultural advice. "
    "CRITICAL STYLE RULES:\n"
    "1. NEVER mention the names of your tools (e.g., do not say 'using boost_crop_production').\n"
    "2. NEVER reveal technical failures to the user. If a local database is missing or an entry isn't found, "
    "silently use your search tool or general knowledge to provide the best possible answer.\n"
    "3. Never say 'not found in local records' or 'searching Google'. Just provide the advice naturally.\n"
    "4. Present all information as your own expert recommendation. "
    "5. Keep the 'magic' alive—the user should feel they are talking to a specialist, not a computer script."
)

# Build the Graph
builder = StateGraph(AssistantState)

# Pass the instruction into the brain node
builder.add_node("brain", lambda state: {"messages": [llm_with_tools.invoke([SystemMessage(content=system_instruction)] + state["messages"])]})

builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "brain")
builder.add_conditional_edges("brain", tools_condition)
builder.add_edge("tools", "brain")
agri_ai = builder.compile()
# Build the Graph
#builder = StateGraph(AssistantState)
#builder.add_node("brain", router_node)
#builder.add_node("tools", ToolNode(tools))
#builder.add_edge(START, "brain")
#builder.add_conditional_edges("brain", tools_condition)
#builder.add_edge("tools", "brain")
#agri_ai = builder.compile()

#==================================================================================================
# --- DATABASE SETUP ---
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, Column, Integer, String, DateTime,text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime


#DATABASE_URL = "postgresql://username:password@hostname:port/database_name"
DATABASE_URL="https://afeeramaryam-smartagro.hf.space"


#DATABASE_URL = "https://afeeramaryam-smart-agro-ai.hf.space"

def save_to_remote_db(endpoint_path: str, payload: dict):
    """Sends agent results to teammate's backend for storage."""
    try:
        url = f"{DATABASE_URL}{endpoint_path}"
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code
    except Exception as e:
        print(f"Failed to save to remote DB: {e}")
        return None
#===========================================================================================================
#import gspread
#from oauth2client.service_account import ServiceAccountCredentials

# AUTHENTICATION
#scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
# IMPORTANT: Make sure 'service_account.json' is in your main folder!
#creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
#client = gspread.authorize(creds)
#sheet = client.open("SmartAgro_AI_Responses").sheet1

# Universal request model
#class AIRequest(BaseModel):
#    user_id: str
#    feature: str
#    crop_or_plant: str = "N/A"
#    soil_moisture: str = None
#    soil_type: str = "N/A"
#    temperature: str = None
#    fertility: str = None
#    irrigation_efficiency: str = None
#    uploaded_pic_url: str = "N/A"
#    text_voice: str = "N/A"
    #rainfall: str = None
    #humidity: str = None
    #weather_temp: str = None
#    ai_recommendation: str

#def universal_save(
#    feature, 
##    ai_recommendation, 
#    user_id="Exhibition_User", 
#    crop_or_plant="N/A", 
#    soil_moisture="N/A", 
#    soil_type="N/A", 
#    temperature="N/A", 
#    fertility="N/A", 
#    irrigation_efficiency="N/A",
#    uploaded_pic_url="N/A",
#    text_voice="N/A",
    #rainfall="N/A",
    #humidity="N/A",
    #weather_temp="N/A"
   # ):
   # try:
    #    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # CRITICAL: This list MUST stay in her exact Column A-O order
    #    row = [
    ##        user_id, feature, crop_or_plant, soil_moisture, soil_type,
    #        temperature, fertility, irrigation_efficiency, uploaded_pic_url,
    #        text_voice, 
    #        str(ai_recommendation), timestamp
    #    ]
        
        # Background thread so the AI doesn't wait for Google
    #    threading.Thread(target=sheet.append_row, args=(row,)).start()
   # except Exception as e:
    #    print(f"Spreadsheet Error: {e}")
       
        
       





#=======================================================================================================

LOCAL_DATABASE_URL = "sqlite:///./farming.db"
        
engine = create_engine(LOCAL_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass
class AgriHistory(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_message = Column(String)
    ai_response = Column(String)
    tool_used = Column(String)

# This command physically creates the 'farming.db' file
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_to_db(user_msg: str, ai_msg: str, tool: str, db: Session):
    new_entry = AgriHistory(
        user_message=user_msg, 
        ai_response=ai_msg, 
        tool_used=tool
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
#=======================================================================================================================
# --- Pydantic Models for Farmer-Friendly Endpoints ---
class SoilAnalysisRequest(BaseModel):
    #n: Optional[int] = None
    #p: Optional[int] = None
    #k: Optional[int] = None
    #ph: Optional[float] = None
    #description: Optional[str] = None
    moisture_level: Optional[str] = None
    soil_type: Optional[str] = None # E.g., "clay", "sandy", "loamy"

class LocationRequest(BaseModel):
    location: str

class CropProductionRequest(BaseModel):
    #month: str
    #location: str
     #temperature: Optional[float] = None
    soil_fertility: Optional[str] = None
    irrigation_efficiency: Optional[str] = None
    plant_type: Optional[str] = None

class IrrigationRequest(BaseModel):
    
    soil_moisture: Optional[str] = None
    temperature: Optional[str] = None
    crop_type: Optional[str] = None
    #location_name: Optional[str] = "Dera Ismail Khan"
#===========================================================================================================================
# --- REMOTE ENDPOINTS FOR TEAMMATES ---
@app.post("/feature/weather")
async def weather_page(data: LocationRequest, db: Session = Depends(get_db)):
    # 1. Direct Instruction: The agent just needs to call the tool with the city name
    #prompt = (
    #    f"The user wants a weather report for '{data.location_name}'. "
    #    f"Use the 'get_weather_by_location' tool to get the data, "
    ##    f"then provide agricultural advice based on those specific conditions."
    #)
    prompt = (
        f"The user wants a weather report for '{data.location}' containing Temperature, Rain prediction, Humidity , Wind,  Crops to Sow and Crops to Reap. "
        f"Use the 'get_weather_by_location' tool to get the data, "
        f"then provide agricultural advice based on those specific conditions."
        f"Also consider that capitalized city names( for e.g, Dera Ismail Khan),lower case city names (for e.g, dera ismail khan) and Abbreviated names of the cities(for e.g,d i khan/D.I.Khan/D I Khan,"
        f"such type of names can also belong to same city but maybe misunderstood by you, so be careful about it."
        f"You can also use search_tool for help."
    )

    # 2. Invoke the Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content
    
    # 3. SQLite-safe String Cleaning (Ensures ai_response is text)
    if isinstance(raw_content, list):
        final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)])
    else:
        final_answer = str(raw_content)

    # 4. Save to History
    save_to_db(
        user_msg=f"Weather check: {data.location}", 
        ai_msg=final_answer, 
        tool="Weather Agent (Location-Based)", 
        db=db
    )

    response_payload = {"status": "success", "recommendation": final_answer}

    # 3. Try remote save, but wrap it in a try/except so it doesn't crash the return
    try:
        # Give it a very short timeout so it doesn't hang the UI
        #universal_save(
        #feature="Weather",
        #ai_recommendation=final_answer
        #)
        save_to_remote_db("/feature/weather", {"city": data.location,"ai_msg":final_answer})
    except Exception as e:
        print(f"Remote DB failed: {e}")

    # 4. Return immediately
    return response_payload
    # saving to remote db
    
    #save_to_remote_db("/feature/weather", {"city": data.location,"ai_msg":final_answer}) 
    
    #return {"status": "success", "recommendation": final_answer}
        # Send to Agent
    #response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    #final_answer = response_state['messages'][-1].content
    
    # Save to DB
    #save_to_db(user_msg=f"Weather check for {data.location_name}", ai_msg=final_answer, tool="Weather AI", db=db)
    
    #return {"status": "success", "recommendation": final_answer}

#@app.post("/ask-text")
#async def ask_text(prompt: str, db: Session = Depends(get_db)):
    # This sends the user's question to the full Agri-AI agent graph
    # The input must match the graph's state, which is {"messages": [("user", prompt)]}
    #response_state = agri_ai.invoke({"messages": [HumanMessage(content=prompt)]})
    
    # The final answer is the last message added to the state by the agent
    #final_answer = response_state['messages'][-1]
    #ai_content = final_answer.content
    #if isinstance(ai_content, list):
        # Extract text from a list of content blocks (for multimodal models)
        #final_answer_text = " ".join(item.get("text", "") for item in ai_content if isinstance(item, dict) and item.get("type") == "text")
    ##else:
        # It's already a string
        #final_answer_text = str(ai_content)

    # Determine tool used for logging
    #tool_used = "LLM Chat" # Default
    ##if final_answer.tool_calls:
        #tool_used = final_answer.tool_calls[0]['name']

    #save_to_db(
        #user_msg=prompt,
        #ai_msg=final_answer_text,
        #tool=tool_used,
        #db=db
    #)
    #return {"status": "success", "ai_answer": final_answer_text}

import pandas as pd

@app.post("/ask-text")
async def ask_text(prompt: str, db: Session = Depends(get_db)):
    # 1. DIRECT DATA INJECTION (Crop CSV & Disease Handbook Context)
    bonus_context = ""
    
    # Check for Crop Recommendation Data
    if any(k in prompt.lower() for k in ["crop", "soil", "npk", "ph", "grow"]):
        try:
            df = pd.read_csv("Crop_recommendation.csv")
            available_crops = ", ".join(df['label'].unique()[:15]) # Sample of crops
            bonus_context += f"\n[LOCAL DATA]: Our records support crops like: {available_crops}."
        except:
            pass

    # Check for Disease Handbook Context
    if any(k in prompt.lower() for k in ["disease", "remedy", "sick", "handbook"]):
        bonus_context += (
            "\n[REFERENCE]: Consult the historical methods from Abdul Hafiz's "
            "'Plant Diseases' (1986) for organic treatments."
        )

    # 2. COMMODITY PRICE TRIGGER
    # If the user asks about prices, we ensure the agent knows to use the tool
    if any(k in prompt.lower() for k in ["price", "market", "rate", "cost", "mandi"]):
        bonus_context += (
            "\n[ACTION]: Use the 'get_commodity_prices' tool to find real-time "
            "market rates for the mentioned commodity and location."
        )
    # 3. CONSTRUCT THE FINAL MESSAGE (Added "Anti-Stalling" Instructions)
    instruction = (
        "\n\n[SYSTEM INSTRUCTION]: The user is reporting symptoms. "
        "Do not ask for more parameters like moisture or efficiency unless absolutely necessary. "
        "Instead, use the [LOCAL DATA] provided below and your internal knowledge to provide "
        "an immediate diagnosis and action plan for their wheat in Dera Ismail Khan."
    )
    
    final_prompt = f"{prompt}\n{instruction}\n{bonus_context}"
    # 3. CONSTRUCT THE FINAL MESSAGE
    #final_prompt = f"{prompt}\n\n{bonus_context}"
    
    # 4. INVOKE AGENT (The Agent will now see the prompt and call the price tool if needed)
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=final_prompt)]})
    
    # 5. CLEANING & LOGGING
    last_msg = response_state['messages'][-1]
    ai_content = last_msg.content
    
    if isinstance(ai_content, list):
        final_answer_text = " ".join(item.get("text", "") for item in ai_content if isinstance(item, dict))
    else:
        final_answer_text = str(ai_content)

    # Log which tool was used (Price tool, Search tool, or Internal)
    tool_used = last_msg.tool_calls[0]['name'] if getattr(last_msg, 'tool_calls', None) else "Direct Context"

    save_to_db(user_msg=prompt, ai_msg=final_answer_text, tool=tool_used, db=db)
    # --- save to db ---
    #payload = {"message": user_input, "ai_response": ai_msg.content}
    #save_to_remote_db(f"{DATABASE_URL}/assistant/text", json=payload)
    try:
        #universal_save(
         #   feature="Chat/Voice Assistant",
         #   ai_recommendation=final_answer_text   
        #)
        save_to_remote_db("assistant/ask", {"user_msg":prompt, "ai_msg":final_answer_text})
    except Exception as e:
        # If it fails, we just print and move on
        print(f"⚠️ Remote DB failed or timed out: {e}")
   

    return {"status": "success", "ai_answer": final_answer_text, "tool": tool_used}
    
from fastapi import UploadFile, File

@app.post("/ask-voice")
async def ask_voice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Receives an audio file, transcribes it to text, and sends the text to the Agri-AI agent.
    NOTE: This requires 'ffmpeg' to be installed on the system for audio conversion.
    - On Debian/Ubuntu: sudo apt-get install ffmpeg
    - On macOS (with Homebrew): brew install ffmpeg
    - On Windows, download from https://ffmpeg.org/download.html and add to your system's PATH.
    """
    audio_bytes = await file.read()

    if not audio_bytes:
        return {"status": "error", "message": "No audio file received."}

    try:
        # Use pydub to load audio from bytes (handles various formats like mp3, ogg, wav)
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))

        # Export to WAV format in memory, which is what SpeechRecognition works with
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)  # Go back to the start of the in-memory file

        # Use SpeechRecognition to process the audio data
        r = sr.Recognizer()
        with sr.AudioFile(wav_io) as source:
            audio_data = r.record(source)
        
        # Transcribe using Google's free web speech API
        transcribed_text = r.recognize_google(audio_data)

        # 3. Invoke Agri-AI Agent
        response_state = agri_ai.invoke({"messages": [HumanMessage(content=transcribed_text)]})
        messages = response_state['messages']

        # 4. Extract the actual text answer (The "Fix")
        final_answer_text = ""
        tool_used = "LLM Chat"
        
        # We look backwards for the first message that has actual text
        for msg in reversed(messages):
            # Check for standard string content
            if msg.content and isinstance(msg.content, str) and msg.content.strip():
                final_answer_text = msg.content
                break
            # Check for list-based content (multimodal)
            elif isinstance(msg.content, list):
                text = " ".join(item.get("text", "") for item in msg.content if isinstance(item, dict) and item.get("type") == "text")
                if text.strip():
                    final_answer_text = text
                    break

        # 5. Identify if a tool was called anywhere in the chain
        for msg in reversed(messages):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_used = msg.tool_calls[0]['name']
                break

        # Fallback if no text was found
        if not final_answer_text:
            final_answer_text = "I couldn't generate a text response, but I processed the request."
        
        # Send the transcribed text to the main Agri-AI agent
        #response_state = agri_ai.invoke({"messages": [HumanMessage(content=transcribed_text)]})
        #final_answer = response_state['messages'][-1]
        #ai_content = final_answer.content
        #if isinstance(ai_content, list):
            # Extract text from a list of content blocks (for multimodal models)
          #  final_answer_text = " ".join(item.get("text", "") for item in ai_content if isinstance(item, dict) and item.get("type") == "text")
        #else:
            # It's already a string
           # final_answer_text = str(ai_content)

        # Determine tool used for logging
        #tool_used = "LLM Chat" # Default
        #if final_answer.tool_calls:
         #   tool_used = final_answer.tool_calls[0]['name']

        save_to_db(
            user_msg=f"Voice Query: {transcribed_text}",
            ai_msg=final_answer_text,
            tool=tool_used,
            db=db
        )
        try:
            #universal_save(
            #feature="Voice Assistant",        # Column B
            
        #text_voice=transcribed_text,      # Column J (The "What they said" column)
            #ai_recommendation=final_answer_text,     # Column N (The "What AI said" column)
                   # Column A
        #)
            save_to_remote_db("/assistant/ask",{ "user_msg":transcribed_text,
                "ai_msg":final_answer_text} )
        except Exception as e:
            print(f"Remote DB failed: {e}")

        return {
            "status": "success",
            "transcribed_text": transcribed_text,
            "ai_answer": final_answer_text
        }

    except sr.UnknownValueError:
        return {"status": "error", "message": "Speech Recognition could not understand the audio."}
    except sr.RequestError as e:
        return {"status": "error", "message": f"Could not request results from Speech Recognition service; {e}"}
    except Exception as e:
        # Catch other errors from pydub or file processing
        return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}

@app.post("/feature/irrigation")
async def irrigation_page(data: IrrigationRequest, db: Session = Depends(get_db)):#, db: Session = Depends(get_db)
    prompt = (
        f"INSTRUCTION: Call the 'get_irrigation_advice' tool using these parameters: "
        f"crop_type='{data.crop_type}', soil_moisture='{data.soil_moisture}', "
        f"and temperature='{data.temperature}'.\n"
        f"STRICT OPERATIONAL PROTOCOL: \n"
        f"1. Return the tool's output directly. \n"
    )
        #f"Output: Present the tool's data in its original bullet format, then add one brief sentence "
        #f"of practical explanation after each point. Do not restructure or rewrite into paragraphs."
        #f"Target: Retrieve irrigation schedules and warnings from 'irrigation_recommendation.csv'.\n"
        #f"Output: Return the tool's data and for each point add 1-2 sentences of practical context "
        #f"explaining why it matters for {data.crop_type} in these conditions. Do not add unrelated advice."
    #)
    #prompt = (
    #f"Use the 'get_irrigation_advice' tool for crop_type='{data.crop_type}', "
    #f"soil_moisture='{data.soil_moisture}', and temperature='{data.temperature}'.\n"
    #f"Your task: Extract data from 'irrigation_recommendation.csv' . "
    #f"Provide a concise summary of the irrigation advice found in the database."
    #)
     
    # 2. Invoke the Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content

    # 3. FIX: SQLite string conversion
    #if isinstance(raw_content, list):
     #   final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)])
    #else:
     #   final_answer = str(raw_content)

        # Replace your current cleaning block with this
    if isinstance(raw_content, list):
        parts = []
        for item in raw_content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or str(item)
                parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        final_answer = " ".join(parts).strip()
    else:
        final_answer = str(raw_content).strip()
    
    if not final_answer:
        final_answer = "Unable to retrieve irrigation data. Please try again."

    # 4. Save to DB
    save_to_db(
        user_msg=f"Irrigation: {data.crop_type} at {data.soil_moisture}% moisture", 
        ai_msg=final_answer, 
        tool="Irrigation AI Tool", 
        db=db
    )
   #5. save to remote db
    try:
        save_to_remote_db("/feature/irrigation-analysis",{"user_msg":f"Irrigation: {data.crop_type} at {data.soil_moisture}% moisture", 
        "ai_msg":final_answer})
        
    except Exception as e:
        print(f"Remote DB failed: {e}")
    
    return {"status": "success", "recommendation": final_answer}



@app.post("/feature/soil-analysis")
async def soil_analysis_page(data: SoilAnalysisRequest, db: Session = Depends(get_db)):#, db: Session = Depends(get_db)
    # 1. Direct Tool-Based Prompt
    prompt = (
        f"CRITICAL INSTRUCTION: Analyze a {data.soil_type} soil sample with {data.moisture_level}% moisture. "
        f"The data is ALREADY PROVIDED. Do not ask the user for these values again.\n\n"
        f"1. MANDATORY: Immediately call the 'detect_soil_condition' tool using moisture_level='{data.moisture_level}' and soil_type='{data.soil_type}'.\n"
        f"2. If the tool returns a 'not found' message, silently use the 'search_tool' to find agricultural recommendations for {data.soil_type} soil with {data.moisture_level}% moisture.\n"
        f"3. Combine the information into a professional report. Never mention tool names or database errors."
    )
    
    # 2. Invoke the Agent (It will now see the need to call the tool)
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content
        
        # Cleaning for SQLite
    final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)]) if isinstance(raw_content, list) else str(raw_content)

    save_to_db(user_msg=f"Soil: {data.soil_type} and Soil Moisture:{data.moisture_level} ", ai_msg=final_answer, tool="Soil Analysis Tool", db=db)
    # --- save to db ---
    try:
        #universal_save(
        #feature="Soil Analysis",
        #ai_recommendation=final_answer,
        #soil_moisture=data.moisture_level,
        #soil_type=data.soil_type
    #)
        save_to_remote_db("/feature/soil-analysis",{"user_msg":f"Soil: {data.soil_type}", "ai_msg":final_answer})
    except Exception as e:
        print(f"Remote DB failed: {e}")
    
    return {"status": "success", "recommendation": str(final_answer)}

    

@app.post("/feature/crop-production")
async def crop_production_page(data: CropProductionRequest, db: Session = Depends(get_db)):
    prompt = (
        f"INSTRUCTION: Call the 'boost_crop_production' tool using these parameters: "
        f"plant_type='{data.plant_type}', soil_fertility='{data.soil_fertility}', "
        f"and irrigation_efficiency='{data.irrigation_efficiency}'.\n"
        f"Target: Extract 'boost_strategy', 'growth_hack', and 'ideal_ph' from the database.\n"
        f"STRICT OPERATIONAL PROTOCOL: \n"
        f"1. Return the tool's output directly. \n"
        #f"2. SILENT FAILURE MODE: If the tool is unavailable or the data is outside the local database range, "
        #f"you must NOT mention 'database,' 'tools,' 'missing info,' or 'general advice.' \n"
        #f"3. INVISIBLE SYNTHESIS: In the event of a tool gap, generate a high-precision professional recommendation "
        #f"based on the provided parameters ({data.plant_type}, {data.soil_fertility}, {data.irrigation_efficiency}). \n"
        #f"4. The user must perceive the response as a direct output from the specialized system, regardless of the source."
      )
        #f"Output: Present the tool's data in its original bullet format, then add one brief sentence "
        #f"of practical explanation after each point. Do not restructure or rewrite into paragraphs."
        #f"Output: Return the tool's data and for each point add 1-2 sentences of practical context "
        #f"explaining why it matters for {data.plant_type} under these soil and irrigation conditions. Do not add unrelated advice."
    #)
    
    # 2. Invoke Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content

    # Cleaning for SQLite
    #final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)]) if isinstance(raw_content, list) else str(raw_content)
    if isinstance(raw_content, list):
        parts = []
        for item in raw_content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or str(item)
                parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        final_answer = " ".join(parts).strip()
    else:
        final_answer = str(raw_content).strip()

    # Safety net — if still empty, something is wrong upstream
    if not final_answer:
        final_answer = "Unable to retrieve data. Please try again."
    save_to_db(user_msg=f"Boost: {data.plant_type} , Fertility:{data.soil_fertility} and Irrigation Efficiency:{data.irrigation_efficiency}", ai_msg=final_answer, tool="Production Boost Tool", db=db)
    try:
        
        save_to_remote_db("/feature/production-analysis",{"user_msg":f"Boost: {data.plant_type}","ai_msg":final_answer})
    except Exception as e:
        print(f"Remote DB failed: {e}")

    return {"status": "success", "recommendation": final_answer}


@app.post("/feature/scanner")
async def disease_page(
    file: UploadFile = File(...), 
    plant_type: str = Form(...), db: Session = Depends(get_db)):
    """
    Accepts an image and the plant category. Returns disease ID and local remedy.
        STRICT OPERATIONAL PROTOCOL: \n
        1. Return the tool's output directly. \n
        2. SILENT FAILURE MODE: If the tool is unavailable or the data is outside the local database range, 
        you must NOT mention 'database,' 'tools,' 'missing info,' or 'general advice.' \n
        3. INVISIBLE SYNTHESIS: In the event of a tool gap, generate a high-precision professional recommendation 
        4. The user must perceive the response as a direct output from the specialized system, regardless of the source.
      
    """
    try:
        img_bytes = await file.read()
        
        # Pass both image and plant_type to the analysis function
        ai_result = await analyze_scan(img_bytes, plant_type)
        
        save_to_db(
            user_msg=f"Image Scan for {plant_type}",
            ai_msg=ai_result,
            tool="Vision + Hybrid Remedy Expert",
            db=db
        )
        try:
            #universal_save(
            #f#eature="Disease Scanner",
            #ai_recommendation=ai_result,
            #crop_or_plant=plant_type,
            #uploaded_pic_url=file.filename
            #)
            save_to_remote_db("/feature/disease-detection",{"user_msg":f"Image Scan for {plant_type}",
            "ai_msg":ai_result})
        
        except Exception as e:
           print(f"Remote DB failed: {e}")

        return {
            "status": "success", 
            "recommendation": ai_result
        }
    except Exception as e:
        return {"status": "error", "message": f"Scan failed: {str(e)}"}

#@app.get("/")
#async def root():
#    return {
#        "status": "Online", 
#        "message": "Agri-AI Server is running!",
#        "docs_url": "http://127.0.0.1:8000/docs"
#    }
#@app.post("/save-ai-data")
#async def save_ai_data(request: AIRequest):
    # This takes the data her frontend sends and passes it to your function
    #universal_save(**request.model_dump()) 
    #return {"status": "success", "message": "Synced to Google Sheets"}

    
@app.get("/")
async def root(db: Session = Depends(get_db)):
    #try:
        # Try a simple query to see if the external DB is alive
        #db.execute(text("SELECT 1")) 
        #db_status = "Connected"
    #except Exception:
        #db_status = "Disconnected"


     # Check Remote Connection
    try:
        remote_res = requests.get(f"{DATABASE_URL}/ping", timeout=30)
        remote_status = "Connected" if remote_res.status_code == 200 else "Offline"
    except:
        remote_status = "Connection Failed"    
    return {
        "status": "Online", 
        "database": remote_status,
        "message": "SmartAgro Server is running!",
        #"docs_url": "/docs"
    }

@app.get("/history")
async def get_farming_history(db: Session = Depends(get_db)):
    """
    Teammates call this to see all past AI suggestions and scans.
    """
    try:
        # Fetching all records, sorted by newest first
        history = db.query(AgriHistory).order_by(AgriHistory.timestamp.desc()).all()
        
        results = []
        for item in history:
            results.append({
                "id": item.id,
                "time": item.timestamp.strftime("%Y-%m-%d %H:%M"),
                "query": item.user_message,
                "answer": item.ai_response,
                "method": item.tool_used
            })
            
        return {"status": "success", "total_records": len(results), "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/db-status")
async def check_status(db: Session = Depends(get_db)):
    # Check Local DB
    local_count = db.query(AgriHistory).count()
    try:
         #Try a simple query to see if the external DB is alive
        db.execute(text("SELECT 1")) 
        db_status = "Connected"
    except Exception:
        db_status = "Disconnected"

    # Check Remote Connection
    try:
        remote_res = requests.get(f"{DATABASE_URL}/ping", timeout=3)
        remote_status = "Connected" if remote_res.status_code == 200 else "Offline"
    except:
        remote_status = "Connection Failed"
        
    return {
      #  "local_history_count": local_count,
        "remote_backend_status": remote_status,
        "remote_url": DATABASE_URL,
        "db_status": db_status
    }
#==================================================================================================================
if __name__ == "__main__":
    import asyncio
    import uvicorn
    print("\n" + "="*50)
    print("🌾 SMARTAGRO SERVER IS STARTING 🌾")
    print("Click here to test: http://127.0.0.1:8000/docs")
    print("="*50 + "\n")
    #port = int(os.environ.get("PORT", 8000)) 
    #uvicorn.run(app, host="0.0.0.0", port=port)
    #uvicorn agent_bot:app --host 0.0.0.0 --port ${PORT}
    #uvicorn.run(app, host="0.0.0.0", port=8000)
    
    
    # This replaces the asyncio.get_event_loop().create_task(...) lines
 
            
#===========================================================================
#============================================================================
