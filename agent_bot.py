import nest_asyncio
import pandas as pd
import base64
import uvicorn
import io
# For Speech-to-Text. You will need to install these libraries:
# pip install SpeechRecognition pydub
import speech_recognition as sr
from pydub import AudioSegment
from PIL import Image
import requests
import re
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
import os
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition
from tavily import TavilyClient
#from langchain_tavily  import TavilySearchResults
from dotenv import load_dotenv 
import glob
load_dotenv()

# Fix for Windows path length limit (MAX_PATH 260 characters)
# Set a shorter cache directory for Kagglehub to prevent FileNotFoundError on deep paths

nest_asyncio.apply()
app = FastAPI()


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow any frontend to connect (ideal for exhibitions)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



os.environ["KAGGLEHUB_CACHE"] = os.path.join(os.path.expanduser("~"), ".khub")
import kagglehub
import os

# Download all datasets and store their paths
print("Syncing Agricultural Datasets...")

paths = {
  #  "guava": kagglehub.dataset_download("shuvokumarbasak4004/guava-fruit-and-leaf-diseases-data-latest-and-updated"),
   # "rose": kagglehub.dataset_download("shuvokumarbasak4004/rose-leaf-disease-dataset"),
   # "neem": kagglehub.dataset_download("vidyahanand/neemazadirachta-indica-healthy-diseased-spectrum")
   # "guava": "C:\Users\A\.khub\datasets\shuvokumarbasak4004\guava-fruit-and-leaf-diseases-data-latest-and-updated",
   # "rose": "C:\Users\A\.khub\datasets\shuvokumarbasak4004\rose-leaf-disease-dataset",
   # "neem": "C:\Users\A\.khub\datasets\vidyahanand\neemazadirachta-indica-healthy-diseased-spectrum"
    "guava": r"C:\Users\A\.khub\datasets\shuvokumarbasak4004\guava-fruit-and-leaf-diseases-data-latest-and-updated",
    "rose": r"C:\Users\A\.khub\datasets\shuvokumarbasak4004\rose-leaf-disease-dataset",
    "neem": r"C:\Users\A\.khub\datasets\vidyahanand\neemazadirachta-indica-healthy-diseased-spectrum"
    "aleovera": r"C:\Users\A\.khub\datasets\aleovera"
    }


for plant, path in paths.items():
    print(f"✅ {plant.capitalize()} data ready at: {path}")

# Initialize Llama 3.2 (The memory-efficient model)
#llm = ChatOllama(model="llama3.2:1b")


# Define the primary (2.5) and fallback (1.5) models
llm_2_5 = ChatGoogleGenerativeAI(model="models/gemini-2.5-flash", api_key=os.getenv("GOOGLE_API_KEY"))
llm_1_5 = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", api_key=os.getenv("GOOGLE_API_KEY"))
# Create a new LLM instance that automatically falls back to 1.5 if 2.5 fails due to errors like resource exhaustion
llm = llm_2_5.with_fallbacks([llm_1_5])

from langchain_core.messages import SystemMessage, HumanMessage

# --- 2. BINDING TOOLS TO LLM ---
@tool
def get_weather_tool(latitude: float, longitude: float):
    """Provides a weather forecast for a specific set of geographic coordinates (latitude and longitude)."""
    print(f"DEBUG: Weather tool was called for lat: {latitude}, lon: {longitude}!")
    
    try:
        # Updated to fetch temperature, humidity, rain, and wind speed
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,rain,wind_speed_10m"
        response = requests.get(url)
        response.raise_for_status() # Will raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        current = data.get('current', {})
        temp = current.get('temperature_2m')
        humidity = current.get('relative_humidity_2m')
        rain = current.get('rain')
        wind = current.get('wind_speed_10m')
        
        if temp is not None:
            return (f"Weather at ({latitude}, {longitude}):\n"
                    f"Temperature: {temp}°C\n"
                    f"Humidity: {humidity}%\n"
                    f"Rain: {rain} mm\n"
                    f"Wind Speed: {wind} km/h")
        return f"Could not retrieve weather. API response: {data}"
    except requests.exceptions.RequestException as e:
        return f"Network error while fetching weather: {e}"
    except Exception as e:
        return f"An unexpected error occurred in get_weather_tool: {e}"
@tool
def get_crop_recommendation(n: int, p: int, k: int, ph: float):
    """Find the best crops based on Nitrogen (n), Phosphorus (p), Potassium (k), and pH levels."""
    print("crop_recommendation tool called!")
    try:
        df = pd.read_csv("data/Crop_recommendation.csv")
        # Improved logic: Check N, P, K and pH with a tolerance range
        mask = (df['ph'].between(ph-1, ph+1)) & \
               (df['N'].between(n-15, n+15)) & \
               (df['P'].between(p-15, p+15)) & \
               (df['K'].between(k-15, k+15))
        res = df[mask]['label'].unique()
        return f"Top matches: {', '.join(res[:3])}" if len(res) > 0 else "Suggesting Hardy Wheat or Maize."
    except FileNotFoundError:
        return "Crop recommendation data file not found. Cannot perform recommendation."

# 2. GOOGLE SEARCH TOOL (Fallback)
# Note: You need a free API Key from tavily.com for this to work
#os.environ["TAVILY_API_KEY"] = "your_tavily_api_key_here"
#search_tool = TavilySearchResults(k=3)

# --- FEATURE 2: Disease Scanner (Logic) ---

async def analyze_scan(image_bytes: bytes):
    """
    Performs a 2-step analysis:
    1. Resizes large images for efficiency.
    2. Sends the image to Gemini to identify the plant and disease.
    3. Runs the identified disease through the Agri-AI graph to get the remedy.
    """
    # --- STEP 1: RESIZE & COMPRESS (for performance and safety) ---
    img = Image.open(io.BytesIO(image_bytes))
    
    # If the image is huge, we resize it but keep it high-quality
    if max(img.size) > 2000:
        img.thumbnail((2000, 2000)) 
    
    # Convert back to bytes with compression
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85) # High quality, but smaller file size
    processed_image_bytes = buffer.getvalue()

    # Base64-encode the image for the API
    img_b64_str = base64.b64encode(processed_image_bytes).decode('utf-8')
    
    # --- STEP 2: IDENTIFY with Gemini Vision ---
    identification_prompt = "Identify the plant and the specific disease shown in this image. Respond with only the plant name and disease name, for example: Guava Anthracnose"
    
    identification_message = HumanMessage(
        content=[
            {"type": "text", "text": identification_prompt},
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{img_b64_str}"},
        ]
    )
    
    # Call the LLM directly for the identification task
    identification_response = await llm.ainvoke([identification_message])
    identified_text = identification_response.content.strip()
    
    # --- STEP 3: GET REMEDY with Agri-AI Agent ---
    # This prompt is designed to trigger the 'hybrid_remedy_expert' tool via the agent's protocol.
    
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=hybrid_remedy_expert)]})
    
    # The agent's final answer will contain the remedy
    remedy_text = response_state['messages'][-1].content
    
    # Combine the results for a comprehensive and clear response
    return f"I have identified the issue as **{identified_text}**. \n\nHere is the recommended action: {remedy_text}"

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

@tool
def get_live_soil_moisture(latitude: float, longitude: float):
    """Fetches real-time soil moisture (0-7cm depth) for a specific set of coordinates."""
    print("soil moisture tool called!")
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&hourly=soil_moisture_0_to_7cm"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        # Get the most recent moisture value
        current_moisture = data.get('hourly', {}).get('soil_moisture_0_to_7cm', [None])[0]
        if current_moisture is not None:
            return f"The current soil moisture at {latitude}, {longitude} is {current_moisture} m³/m³."
        return "Soil moisture data not available in the response."
    except requests.exceptions.RequestException as e:
        return f"I'm sorry, I couldn't reach the soil sensors right now due to a network error: {e}"

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
        api_key = os.getenv("87V2ZAHWIdBotYbSh0oWT95Mj1b3IgWFD1Rw6Aaq") # Using the key name as requested by user.
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
    Step 1: Checks CSV for local DI Khan cures.
    Step 2: Checks Kaggle folder names for scientific verification.
    Step 3: If verified but no cure in CSV, returns 'SEARCH_REQUIRED'.
    """
    p_name = plant_name.lower()
    
    d_name = disease_name.lower()

    # --- TIER 1: LOCAL CSV ---
    df = pd.read_csv("data/plants_info.csv")
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
        api_key = os.getenv("9fpj2UR2dXy8VPvqRKshfW1PK9Kymya5jlgeVmgqy1cclCxtKZ") # Assumes you have this env var set
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
    return get_crop_recommendation.invoke(data)



# --- 2. BINDING TOOLS TO LLM ---
tools = [get_weather_tool, get_crop_recommendation, search_tool, get_live_soil_moisture, hybrid_remedy_expert, suggest_by_observation, get_commodity_prices]
#llm = OllamaLLM(model="llama3.2:1b")
llm_with_tools = llm.bind_tools(tools)

class AssistantState(TypedDict):
    """
    A dictionary that represents the state of our graph.
    It contains a list of messages. The `add_messages` function
    is a helper that appends messages to the list.
    """
    messages: Annotated[list, add_messages]

def router_node(state: AssistantState):
    """The primary node that runs the LLM to decide what to do."""
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

# Build the Graph
builder = StateGraph(AssistantState)
builder.add_node("brain", router_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "brain")
builder.add_conditional_edges("brain", tools_condition)
builder.add_edge("tools", "brain")
agri_ai = builder.compile()

# --- DATABASE SETUP ---
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, Column, Integer, String, DateTime,text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime


# 1. 'sqlite:///./farming.db' creates a file in the same folder as your script
#For PostgreSQL:DATABASE_URL = "postgresql://username:password@hostname:port/database_name"

#For MySQL:
#DATABASE_URL = "mysql+pymysql://username:password@hostname:port/database_name"

#For a remote SQLite file (on a shared drive):
#DATABASE_URL = "sqlite:///path/to/remote/shared_farming.db"
DATABASE_URL = "sqlite:///./farming.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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

# --- Pydantic Models for Farmer-Friendly Endpoints ---
class SoilAnalysisRequest(BaseModel):
    n: Optional[int] = None
    p: Optional[int] = None
    k: Optional[int] = None
    ph: Optional[float] = None
    description: Optional[str] = None
    soil_moisture: Optional[float] = None
    soil_type: Optional[str] = None # E.g., "clay", "sandy", "loamy"

class LocationRequest(BaseModel):
    location_name: str

class CropProductionRequest(BaseModel):
    month: str
    location: str
    soil_fertility: Optional[str] = None
    irrigation_efficiency: Optional[str] = None
    temperature: Optional[float] = None
    plant_type: Optional[str] = None

class IrrigationRequest(BaseModel):
    crop_type: str
    location_name: Optional[str] = "Dera Ismail Khan"
    soil_moisture: Optional[float] = None
    temperature: Optional[float] = None

# --- REMOTE ENDPOINTS FOR TEAMMATES ---
@app.post("/feature/weather")
async def weather_page(data: LocationRequest, db: Session = Depends(get_db)):
    # Construct prompt
    prompt = f"What is the current weather in {data.location_name}? Please provide a detailed report including temperature, humidity, rain, and wind speed, and advice for farmers based on this weather."
    
    # Send to Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    final_answer = response_state['messages'][-1].content
    
    # Save to DB
    save_to_db(user_msg=f"Weather check for {data.location_name}", ai_msg=final_answer, tool="Weather AI", db=db)
    
    return {"status": "success", "recommendation": final_answer}

@app.post("/ask-text")
async def ask_text(prompt: str, db: Session = Depends(get_db)):
    # This sends the user's question to the full Agri-AI agent graph
    # The input must match the graph's state, which is {"messages": [("user", prompt)]}
    response_state = agri_ai.invoke({"messages": [HumanMessage(content=prompt)]})
    
    # The final answer is the last message added to the state by the agent
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
        user_msg=prompt,
        ai_msg=final_answer_text,
        tool=tool_used,
        db=db
    )
    return {"status": "success", "ai_answer": final_answer_text}

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
async def irrigation_page(data: IrrigationRequest, db: Session = Depends(get_db)):
    # Construct prompt from inputs
    prompt = (f"I am growing {data.crop_type} in {data.location_name or 'Dera Ismail Khan'}. "
              f"Current temperature is {data.temperature if data.temperature else 'unknown'}°C and soil moisture is {data.soil_moisture if data.soil_moisture else 'unknown'}%. "
              f"Should I irrigate now? Give me a schedule.")

    # Send to Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    final_answer = response_state['messages'][-1].content

    save_to_db(user_msg=f"Irrigation check for {data.crop_type}", ai_msg=final_answer, tool="Irrigation AI", db=db)

    return {"status": "success", "recommendation": final_answer}

@app.post("/feature/soil-analysis")
async def soil_analysis_page(data: SoilAnalysisRequest, db: Session = Depends(get_db)):
    # 1. Construct a rich prompt from the dropdowns
    prompt = f"Perform a soil analysis. "
    if data.soil_type: prompt += f"The soil type is {data.soil_type}. "
    if data.n: prompt += f"NPK values are {data.n}-{data.p}-{data.k}. "
    if data.ph: prompt += f"The pH level is {data.ph}. "
    if data.soil_moisture: prompt += f"Soil moisture is {data.soil_moisture}. "
    if data.description: prompt += f"Farmer's observation: {data.description}. "
    prompt += "Based on this, what crops should I plant and what fertilizers do I need?"

    # 2. Send it to the AI Agent (the 'brain')
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    final_answer = response_state['messages'][-1].content

    # 3. Save to History
    save_to_db(user_msg="Soil Analysis Request", ai_msg=final_answer, tool="Soil Analysis AI", db=db)

    return {"status": "success", "recommendation": final_answer}

@app.post("/feature/crop-production")
async def crop_production_page(data: CropProductionRequest, db: Session = Depends(get_db)):
    # Construct prompt
    prompt = (
        f"Based on historical weather patterns and common agricultural practices, "
        f"what crops are best to plant in '{data.location}' during the month of '{data.month}'? "
        f"If location and month are not given , then consider soil fertility,temperatue and plant type"
    )
    if data.soil_fertility: prompt += f"Soil fertility is {data.soil_fertility}. "
    if data.irrigation_efficiency: prompt += f"Irrigation method is {data.irrigation_efficiency}. "
    if data.temperature: prompt += f"Expected temperature is {data.temperature}°C. "
    if data.plant_type: prompt += f"Preference: {data.plant_type}. "
    
    prompt += "Provide a concise list of suitable crops with brief justifications."

    # Send to Agent
    response_state = await agri_ai.ainvoke({"messages": [HumanMessage(content=prompt)]})
    final_answer = response_state['messages'][-1].content

    # Save to DB
    save_to_db(user_msg=f"Crop Production Request for {data.location}", ai_msg=final_answer, tool="Crop Production AI", db=db)

    return {"status": "success", "recommendation": final_answer}

@app.post("/feature/scanner")
async def disease_page(file: UploadFile = File(..., description="Upload an image of a plant. To avoid server issues, please use images under 10MB."), db: Session = Depends(get_db)):
    """
    The main endpoint your teammates will call from the frontend.
    It accepts an image file containing plant's disease and it will scan and check the disease, runs it through the analysis pipeline, and after identifying the disease it will give the remedy to get rid of diseasereturns the result.
    """
    img_bytes = await file.read()
    
    # 1. Run your analysis (the code we fixed earlier)
    ai_result = await analyze_scan(img_bytes)
    
    # 2. SAVE TO DB
    save_to_db(
        user_msg="Image Scan: Plant Disease Identification",
        ai_msg=ai_result,
        tool="Gemini-2.5-Flash-Vision",
        db=db
    )
    
    return {
        "status": "success",
        "recommendation": ai_result
    }

#@app.get("/")
#async def root():
#    return {
#        "status": "Online", 
#        "message": "Agri-AI Server is running!",
#        "docs_url": "http://127.0.0.1:8000/docs"
#    }

@app.get("/")
async def root(db: Session = Depends(get_db)):
    try:
        # Try a simple query to see if the external DB is alive
        db.execute(text("SELECT 1")) 
        db_status = "Connected"
    except Exception:
        db_status = "Disconnected"

    return {
        "status": "Online", 
        "database": db_status,
        "message": "Agri-AI Server is running!",
        "docs_url": "/docs"
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
    

if __name__ == "__main__":
    import asyncio
    import uvicorn
    print("\n" + "="*30)
    print("🌾 AGRI-AI SERVER IS STARTING 🌾")
    print("Click here to test: http://127.0.0.1:8000/docs")
    print("="*30 + "\n")
    
    # This replaces the asyncio.get_event_loop().create_task(...) lines
    uvicorn.run(app, host="0.0.0.0", port=8000)
    #uvicorn.run(app, host="0.0.0.0", port=10000)


    #print("--- 🌾 Starting Agri-AI Server 🌾 ---")
    #print("Checking Ollama connection...")
    #config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio")
    #server = uvicorn.Server(config)
    #import asyncio
    #asyncio.get_event_loop().create_task(server.serve())


    #if __name__ == "__main__":
    # Standard uvicorn run keeps the process alive
    #uvicorn.run(app, host="0.0.0.0", port=8000)

#@app.post("/feature/ai-chat")
async def ai_assistant(data: dict):
    user_input = data.get("message", "")
    
    # Gemini decides if it needs a tool or just a chat response
    ai_msg = llm_with_tools.invoke(user_input)
    
    # If Gemini wants to use a tool, it returns 'tool_calls'
 #   if ai_msg.tool_calls:
        # For a simple exhibition, we can just manually call the first tool it picked
       # tool_name = ai_msg.tool_calls[0]['name']
       # args = ai_msg.tool_calls[0]['args']
        
       # if tool_name == "get_weather_advice":
          #  return {"answer": get_weather_advice.invoke(args)}
        #if tool_name == "get_soil_moisture":
           # return {"answer": get_soil_moisture.invoke(args)}
            
    #return {"answer": ai_msg.content}


    # To install: pip install tavily-python
#from tavily import TavilyClient
#client = TavilyClient("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")
#response = client.search(
#    query="how to get api key\n",
#    search_depth="advanced"
#)
#print(response)
#============================================================================