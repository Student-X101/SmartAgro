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
model_1 = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=primary_key)
model_2 = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=secondary_key)

# 3. Create the "Smart" model with fallback logic
# This replaces your manual rotation function
llm = model_1.with_fallbacks([model_2])

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
    Fetches real-time weather. 
    REQUIRED: You must ask the user for a specific city or location if it is not provided. 
    DO NOT guess the location.Fetches a full weather report (Temp, Humidity, Rain, Wind) 
    using only the name of the city or region.
    
    Args:
        location: The city or area name required for weather lookups.
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
            #f"🌤️ **Weather Report for {location}** ({lat}, {lon}):\n"
            #f"- Temperature: {current.get('temperature_2m')}°C\n"
            #f"- Humidity: {current.get('relative_humidity_2m')}%\n"
            #f"- Rain: {current.get('rain')} mm\n"
            #f"- Wind Speed: {current.get('wind_speed_10m')} km/h\n"
            #f"Source: Open-Meteo Real-time Data"
        )
    except Exception as e:
        return f"Error connecting to weather services: {str(e)}"
import os
import pandas as pd
from langchain.tools import tool

#@tool
#def boost_crop_production(soil_fertility: int, irrigation_efficiency: int, plant_type: str):
#    """
#    Provides strategies to boost yield based on soil fertility (1-100), 
#    irrigation efficiency (%), and plant type.
#    """
@tool
def boost_crop_production(soil_fertility: str, irrigation_efficiency: str, plant_type: str ):
    """
    Provides NPK fertilizer and system repair advice from 'production_master.csv'.
    
    Args:
        soil_fertility: The current nutrient status ('Low', 'Medium', 'High').
        irrigation_efficiency: The system efficiency ('0-50% (Low)' or '51-100% (High)').
        plant_type: The specific plant name (e.g., 'Kachnar', 'Thuja', 'Java Plum').
    """
    csv_path = "production_boost.csv"
    
    # 1. Check if file exists
    if not os.path.exists(csv_path):
        return "The local production database is missing. Please search the web for crop boost strategies."

    try:
        df = pd.read_csv(csv_path)
        plant_type_clean = plant_type.strip().capitalize()
        
        # 2. Search the CSV
        res = df[df['plant_type'].str.capitalize() == plant_type_clean]
        
        # --- THE SEARCH FALLBACK LOGIC ---
        if res.empty:
            return f"I couldn't find '{plant_type}' in my local agricultural records. Please use your search tool to find professional growth hacks and fertilizer strategies for this specific crop."

        # 3. Process Fertility (1-100 to Category)
        if soil_fertility <= 30: status = "Poor"
        elif soil_fertility <= 70: status = "Average"
        else: status = "Rich"

        advice = res[res['fertility_level'].str.capitalize() == status]
        final_row = advice.iloc[0] if not advice.empty else res.iloc[0]

        return (
            f"🚀 **Boost Strategy for {plant_type}**: {final_row['boost_strategy']}\n"
            f"💡 **Growth Hack**: {final_row['growth_hack']}\n"
            f"🧪 **Target Soil pH**: {final_row['ideal_ph']}"
        )

    except Exception as e:
        return f"Database error. Please search Google for {plant_type} cultivation tips. Error: {str(e)}"




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
    Args:
        moisture_level: Current moisture percentage (0-100).
        soil_type: The type of soil ('Clay', 'Sandy', 'Loamy').
    """

    csv_path = "soil_detection.csv"
    
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
            f"- **Soil Type**: {soil_type_clean}\n"
            f"- **Moisture**: {m_val}% ({moisture_cat})\n"
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
        df = pd.read_csv("data/commodity_prices.csv")
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
        df = pd.read_csv("data/plants_info.csv")
        # ... (matching logic) ...
    except Exception as e:
        print(f"Data Warning: CSV not found or unreadable: {e}")
    # Make matching more flexible: check if the disease from the CSV is *contained within* the disease name from the LLM.
    # This handles cases where the LLM passes "guava wilt" but the CSV just has "wilt".
    match = df[(df['urdu_name'].str.lower() == p_name) &
               (df['disease_names'].str.lower().apply(lambda csv_disease: csv_disease in d_name))]
    
    if not match.empty:
        return f"Local Expert Result: Use {match.iloc[0]['treatment_organic']}."

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
@tool
def get_irrigation_advice(soil_moisture: str, temperature: str, crop_type: str):
    """
    Provides irrigation recommendations from 'irrigation_recommendation.csv'. 
    
    Args:
        soil_moisture: The current moisture percentage (0-100).
        temperature: The current temperature in Celsius.
        crop_type: The name of the crop (e.g., 'Wheat', 'Maize', 'Rice', 'Euphorbia').
    """
    csv_path = "irrigation_recommendation.csv"
    
    if not os.path.exists(csv_path):
        return "The irrigation database is currently unavailable. Please provide general watering advice for this crop."

    try:
        # Convert incoming strings from frontend to integers
        m_val = int(float(soil_moisture))
        t_val = int(float(temperature))
        crop_clean = crop_type.strip().capitalize()

        # --- MAPPING LOGIC: Convert numbers to CSV categories ---
        if m_val <= 30: 
            m_cat = "1-30 (Dry)"
        elif m_val <= 70: 
            m_cat = "31-70 (Optimal)"
        else: 
            m_cat = "71-100 (Saturated)"

        if t_val <= 20: 
            t_cat = "0-20 (Cool)"
        elif t_val <= 35: 
            t_cat = "21-35 (Mild)"
        else: 
            t_cat = "36-50 (Hot)"

        df = pd.read_csv(csv_path)
        
        # Search by crop and the mapped categories
        res = df[(df['crop_type'].str.capitalize() == crop_clean)]
        
        if res.empty:
            return f"I couldn't find specific local records for {crop_type}. Based on the temperature of {t_val}°C and moisture of {m_val}%, please suggest general irrigation best practices."

        final_row = res.iloc[0]
        status = "CRITICAL" if m_val < 30 else "Healthy"
        
        return (
            f"💧 **Irrigation Report for {crop_clean}**:\n"
            f"- **Current Conditions**: {t_cat} temperature and {m_cat} moisture.\n"
            f"- **Water Requirement**: {final_row['water_requirement']}\n"
            f"- **Critical Growth Stage**: {final_row['critical_stage']}\n"
            f"- **Status**: {status}\n"
            f"⚠️ **Note**: {final_row['warning']}"
        )

    except Exception as e:
        return f"System processing error. Please provide general irrigation advice for {crop_type} at {temperature}°C."
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
    crop_type: str
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
        f"The user wants a weather report for '{data.location}' containing Temperature, Rain prediction, Humidity and Wind. "
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
        
        # Send the transcribed text to the main Agri-AI agent
        response_state = agri_ai.invoke({"messages": [HumanMessage(content=transcribed_text)]})
        final_answer = response_state['messages'][-1]
        ai_content = final_answer.content
        if isinstance(ai_content, list):
            # Extract text from a list of content blocks (for multimodal models)
            final_answer_text = " ".join(item.get("text", "") for item in ai_content if isinstance(item, dict) and item.get("type") == "text")
        else:
            # It's already a string
            final_answer_text = str(ai_content)

        # Determine tool used for logging
        tool_used = "LLM Chat" # Default
        if final_answer.tool_calls:
            tool_used = final_answer.tool_calls[0]['name']

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
    # 1. Force the Agent to use the new tool
    #prompt = (
    #    f"Use the 'get_irrigation_advice' tool for crop_type='{data.crop_type}', "
    #    f"temperature={data.temperature}, and soil_moisture={data.soil_moisture}.\n"
    #    f"Based on the tool's report, give the farmer a clear 'Yes/No' on whether to water now "
    #    f"and explain why based on the growth stage."
    #)
    prompt = (
    f"Act as a professional agronomist. Use the 'get_irrigation_advice' tool to retrieve "
    f"specific data for crop: '{data.crop_type}', temperature: {data.temperature}°C, "
    f"and soil moisture: {data.soil_moisture}%.\n"
    f"Your task: Provide a comprehensive irrigation schedule and management strategy. "
    f"You can also use irrigation_recommendation.csv to recommend.Detail the exact watering depth, recommended "
    f"time of day for irrigation, and any specific techniques (like drip or flooding) "
    f"based on the current moisture levels and heat stress(if present in irrigation_recommendation.csv)."
    f"If the desired/asked details are not mentioned in irrigation_recommendation.csv, then use search_tool to search on Google about the asked/needed information."
       
    )

    # 2. Invoke the Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content

    # 3. FIX: SQLite string conversion
    if isinstance(raw_content, list):
        final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)])
    else:
        final_answer = str(raw_content)

    # 4. Save to DB
    save_to_db(
        user_msg=f"Irrigation: {data.crop_type} at {data.soil_moisture}% moisture", 
        ai_msg=final_answer, 
        tool="Irrigation AI Tool", 
        db=db
    )
   #5. save to remote db
    try:
        #universal_save(
        #feature="Irrigation",
        #ai_recommendation=final_answer,
        #crop_or_plant=data.crop_type,
        #soil_moisture=data.soil_moisture,
        #temperature=data.temperature
    #)
        save_to_remote_db("/feature/irrigation-analysis",{"user_msg":f"Irrigation: {data.crop_type} at {data.soil_moisture}% moisture", 
        "ai_msg":final_answer})
    except Exception as e:
        print(f"Remote DB failed: {e}")
    
    return {"status": "success", "recommendation": final_answer}

#@app.post("/feature/soil-analysis")
#async def soil_analysis_page(data: SoilAnalysisRequest, db: Session = Depends(get_db)):
    # 1. Construct a rich prompt from the dropdowns
   # Updated Prompt Construction for Observable Inputs
#    prompt = (
#        "Acting as a local agricultural expert for Pakistan, provide a crop and fertilizer "
#        "recommendation based ONLY on the following observable data: "
 #   )

    # Core Inputs
  #  if data.soil_type: 
   #     prompt += f"\n- Soil Type: {data.soil_type}. "

 #   if data.temperature: 
  #      prompt += f"\n- Current Temperature: {data.temperature}°C. "

   # if data.plant_type: 
    #    prompt += f"\n- Preferred Crop Category: {data.plant_type}. "

    #if data.soil_moisture: 
     #   prompt += f"\n- Soil Moisture Level: {data.soil_moisture}. "

# Contextual Description (If the farmer adds notes like 'leaves are yellow' or 'very dry')
    #if data.descript9ion: 
     #   prompt += f"\n- Farmer's Observation: {data.description}. "
    
    # Logic for missing lab data
    #prompt += (
     #   "\n\nSince laboratory soil data (pH and NPK) is currently unavailable, "
      #  "suggest crops that thrive in this soil type and climate. "
       # "Also, recommend a general-purpose fertilizer or organic soil amendment "
        #"typically used for these conditions in this region. Provide a concise response."
    #)

    # 2. Send it to the AI Agent (the 'brain')
    #response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    #final_answer = response_state['messages'][-1].content

    # 3. Save to History
    #save_to_db(user_msg="Soil Analysis Request", ai_msg=final_answer, tool="Soil Analysis AI", db=db)

    #return {"status": "success", "recommendation": final_answer}

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

    
#@app.post("/feature/crop-production")
#async def crop_production_page(data: CropProductionRequest, db: Session = Depends(get_db)):
    # Construct prompt
    # Updated Prompt Construction
# This ignores location/month and focuses strictly on Soil, Temp, and Type

#    prompt = (
#        "Acting as an expert agronomist, recommend the best crops based strictly on the following conditions: "
##    )
    
    # Adding the specific constraints
 #   if data.soil_fertility: 
 #       prompt += f"The soil fertility level is {data.soil_fertility}. "
    
 #   if data.temperature: 
 #       prompt += f"The current/expected temperature is {data.temperature}°C. "
 #   
 ##   if data.plant_type: 
  #      prompt += f"The specific plant category or type requested is {data.plant_type}. "
    
    # Final instruction
#    prompt += (
 #       "\n\nBased ONLY on these three factors, provide a concise list of suitable crops "
#        "with a one-sentence justification for each based on how they fit these conditions."
#    )

    # Send to Agent
##    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
##    final_answer = response_state['messages'][-1].content

    # Save to DB
#    save_to_db(user_msg=f"Crop Production Request for {data.location}", ai_msg=final_answer, tool="Crop Production AI", db=db)

 #   return {"status": "success", "recommendation": final_answer}

@app.post("/feature/crop-production")
async def crop_production_page(data: CropProductionRequest, db: Session = Depends(get_db)):
    # 1. Direct Tool-Based Prompt
    #prompt = (
    #    f"Use the 'boost_crop_production' tool for plant_type='{data.plant_type}', "
    #    f"fertility={data.soil_fertility}, and efficiency={data.irrigation_efficiency}.\n"
    #    f"Summarize the boost strategy and growth hacks provided by the tool."
    #)
    prompt = (
        f"Use the 'boost_crop_production' tool for plant_type='{data.plant_type}', "
        f"fertility={data.soil_fertility}, and efficiency={data.irrigation_efficiency}.\n"
        f"Your task: Provide a comprehensive recommendation for crop production."
        f"You can also use production_boost.csv for your help."
        f"If desired/asked/needed information is not available in production_boost.csv, use search_tool to search on Google for the needed information."
        f"Summarize the boost strategy and growth hacks provided by the tool."
    )

    # 2. Invoke Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    raw_content = response_state['messages'][-1].content

    # Cleaning for SQLite
    final_answer = " ".join([item.get("text", "") for item in raw_content if isinstance(item, dict)]) if isinstance(raw_content, list) else str(raw_content)

    save_to_db(user_msg=f"Boost: {data.plant_type} , Fertility:{data.soil_fertility} and Irrigation Efficiency:{data.irrigation_efficiency}", ai_msg=final_answer, tool="Production Boost Tool", db=db)
    try:
        #universal_save(
        #feature="Production Boost",
        #ai_recommendation=final_answer,
        #crop_or_plant=data.plant_type,
        ##fertility=data.soil_fertility,
        #irrigation_efficiency=data.irrigation_efficiency
    #)
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
