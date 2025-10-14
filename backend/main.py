# backend/main.py
import os, time, math
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Tuple, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Crop Recommendation API with Weather + Cache")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
if not OPENWEATHER_KEY:
    raise RuntimeError("OPENWEATHER_API_KEY not set in .env")

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "600"))             # 10 min
OWM_MIN_INTERVAL = float(os.getenv("OWM_MIN_INTERVAL_SECONDS", "1.2"))

# ---- Simple in-memory cache + polite rate limit ----
# cache: { (lat_2dp, lon_2dp): (timestamp, data_dict) }
_weather_cache: Dict[Tuple[float, float], Tuple[float, Dict[str, Any]]] = {}
_last_owm_call_ts: float = 0.0

def _round_coord(x: float, dp: int = 2) -> float:
    # reduce cache keys so nearby points reuse results
    m = 10 ** dp
    return math.floor(x * m + 0.5) / m

def _from_cache(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    key = (_round_coord(lat), _round_coord(lon))
    entry = _weather_cache.get(key)
    if not entry: return None
    ts, data = entry
    if time.time() - ts <= CACHE_TTL:
        return data
    # expired
    _weather_cache.pop(key, None)
    return None

def _save_cache(lat: float, lon: float, data: Dict[str, Any]) -> None:
    key = (_round_coord(lat), _round_coord(lon))
    _weather_cache[key] = (time.time(), data)

def _respect_rate_limit():
    global _last_owm_call_ts
    elapsed = time.time() - _last_owm_call_ts
    if elapsed < OWM_MIN_INTERVAL:
        time.sleep(OWM_MIN_INTERVAL - elapsed)
    _last_owm_call_ts = time.time()

def fetch_weather(lat: float, lon: float) -> Dict[str, Any]:
    # 1) Try cache first
    cached = _from_cache(lat, lon)
    if cached:
        return cached

    # 2) Polite spacing between calls
    _respect_rate_limit()

    # 3) Request with small retry/backoff
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_KEY, "units": "metric"}

    backoff = 0.8
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 429:
                # Too Many Requests → wait a bit more and retry
                time.sleep(2.0 + attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            _save_cache(lat, lon, data)
            return data
        except Exception as e:
            last_err = e
            time.sleep(backoff)
            backoff *= 1.6

    # 4) As a last resort, serve slightly-stale cache (if we have it)
    stale = _from_cache(lat, lon)  # this will be None because we popped on expiry
    if stale:
        return stale

    raise HTTPException(status_code=502, detail=f"Weather provider error: {last_err}")

# ---- API models ----
class RecommendRequest(BaseModel):
    lat: float
    lon: float
    soil_type: str
    ph: float
    season: Optional[str] = None

class CropScore(BaseModel):
    crop: str
    score: float
    reasons: dict

@app.get("/")
def root():
    return {"message": "Crop Recommendation API is running"}

# ---- Recommendation logic (uses weather) ----
@app.post("/recommend", response_model=List[CropScore])
def recommend(req: RecommendRequest):
    w = fetch_weather(req.lat, req.lon)
    temp_c = w.get("main", {}).get("temp")
    rain_1h = w.get("rain", {}).get("1h", 0.0) or 0.0

    crops = [
        {"name":"Rice",   "preferred_texture":"loamy","min_ph":5.5,"max_ph":7.0,"min_temp":20,"max_temp":35,"min_rain":50,"max_rain":200},
        {"name":"Wheat",  "preferred_texture":"loamy","min_ph":6.0,"max_ph":7.5,"min_temp":10,"max_temp":25,"min_rain":20,"max_rain":100},
        {"name":"Maize",  "preferred_texture":"loamy","min_ph":5.5,"max_ph":7.5,"min_temp":18,"max_temp":32,"min_rain":25,"max_rain":150},
        {"name":"Millet", "preferred_texture":"sandy","min_ph":5.0,"max_ph":8.0,"min_temp":18,"max_temp":35,"min_rain":10,"max_rain":120},
        {"name":"Sorghum","preferred_texture":"sandy","min_ph":5.5,"max_ph":8.0,"min_temp":20,"max_temp":38,"min_rain":15,"max_rain":140},
        {"name":"Pulses", "preferred_texture":"loamy","min_ph":6.0,"max_ph":7.5,"min_temp":15,"max_temp":30,"min_rain":15,"max_rain":110},
    ]

    def texture_score(field_texture, pref_texture):
        return 1.0 if str(field_texture).lower()==str(pref_texture).lower() else 0.5

    def ph_score(field_ph, min_ph, max_ph):
        mid = (min_ph + max_ph) / 2.0
        tol = (max_ph - min_ph) / 2.0 + 0.5
        diff = abs(field_ph - mid)
        return max(0.0, 1 - (diff / tol))

    def temp_fit(temp_val, mn, mx):
        if temp_val is None: return 0.0
        return 1.0 if mn <= temp_val <= mx else 0.0

    def rain_fit(rain_val, mn, mx):
        # Using 1h rain; for better signal, consider forecast sums next iteration
        return 1.0 if mn <= rain_val <= mx else 0.0

    results = []
    for c in crops:
        t_sc = texture_score(req.soil_type, c["preferred_texture"])
        p_sc = ph_score(req.ph, c["min_ph"], c["max_ph"])
        tm_sc = temp_fit(temp_c, c["min_temp"], c["max_temp"])
        rn_sc = rain_fit(rain_1h, c["min_rain"], c["max_rain"])
        score = 30*t_sc + 30*p_sc + 20*tm_sc + 20*rn_sc
        results.append({
            "crop": c["name"],
            "score": round(score, 1),
            "reasons": {
                "texture_match": round(t_sc,2),
                "ph_fit": round(p_sc,2),
                "temp_c": temp_c,
                "temp_fit": round(tm_sc,2),
                "rain_1h_mm": rain_1h,
                "rain_fit": round(rn_sc,2),
            }
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)
