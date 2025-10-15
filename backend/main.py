# backend/main.py
import os, time, math
import requests
from typing import List, Optional, Tuple, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# 1) CREATE THE APP FIRST
app = FastAPI(title="Crop Recommendation API")

# 2) THEN ADD CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # add your Vercel domain when running in production:
        # "https://crop-recommender-beta.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Optional weather/forecast config (safe if key missing) ----
OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "600"))
OWM_MIN_INTERVAL = float(os.getenv("OWM_MIN_INTERVAL_SECONDS", "1.2"))
FORECAST_HOURS = int(os.getenv("FORECAST_HOURS", "72"))

_weather_cache: Dict[Tuple[str, float, float], Tuple[float, Dict[str, Any]]] = {}
_last_owm_call_ts: float = 0.0

def _round_coord(x: float, dp: int = 2) -> float:
    m = 10 ** dp
    return math.floor(x * m + 0.5) / m

def _cache_get(kind: str, lat: float, lon: float):
    key = (kind, _round_coord(lat), _round_coord(lon))
    v = _weather_cache.get(key)
    if not v: return None
    ts, data = v
    if time.time() - ts <= CACHE_TTL:
        return data
    _weather_cache.pop(key, None)
    return None

def _cache_put(kind: str, lat: float, lon: float, data: Dict[str, Any]):
    key = (kind, _round_coord(lat), _round_coord(lon))
    _weather_cache[key] = (time.time(), data)

def _respect_rate_limit():
    global _last_owm_call_ts
    elapsed = time.time() - _last_owm_call_ts
    if elapsed < OWM_MIN_INTERVAL:
        time.sleep(OWM_MIN_INTERVAL - elapsed)
    _last_owm_call_ts = time.time()

def fetch_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Returns OWM 5-day/3-hour forecast; if no API key, returns empty stub."""
    if not OPENWEATHER_KEY:
        return {"list": []}  # safe stub for local runs without a key
    cached = _cache_get("forecast", lat, lon)
    if cached:
        return cached
    _respect_rate_limit()
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_KEY, "units": "metric"}
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error fetching forecast")
    data = resp.json()
    _cache_put("forecast", lat, lon, data)
    return data

def aggregate_forecast(forecast: Dict[str, Any], hours: int = FORECAST_HOURS) -> Dict[str, float]:
    steps = forecast.get("list") or []
    if not steps:
        return {"min_temp": None, "max_temp": None, "precip_sum_mm": 0.0}
    need = max(1, hours // 3)
    slots = steps[:need]
    temps, precip = [], 0.0
    for it in slots:
        main = it.get("main") or {}
        if "temp" in main:
            temps.append(main["temp"])
        precip += float((it.get("rain") or {}).get("3h", 0.0) or 0.0)
        precip += float((it.get("snow") or {}).get("3h", 0.0) or 0.0)
    return {
        "min_temp": (min(temps) if temps else None),
        "max_temp": (max(temps) if temps else None),
        "precip_sum_mm": round(precip, 1),
    }

# ---- Models ----
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

@app.post("/recommend", response_model=List[CropScore])
def recommend(req: RecommendRequest):
    # Weather (safe if no key)
    fc = fetch_forecast(req.lat, req.lon)
    agg = aggregate_forecast(fc, hours=FORECAST_HOURS)
    fmin, fmax, precip = agg["min_temp"], agg["max_temp"], agg["precip_sum_mm"]

    crops = [
        {"name":"Rice",   "preferred_texture":"loamy","min_ph":5.5,"max_ph":7.0,"min_temp":20,"max_temp":35,"rain_window_mm":(40,180)},
        {"name":"Wheat",  "preferred_texture":"loamy","min_ph":6.0,"max_ph":7.5,"min_temp":10,"max_temp":25,"rain_window_mm":(15,90)},
        {"name":"Maize",  "preferred_texture":"loamy","min_ph":5.5,"max_ph":7.5,"min_temp":18,"max_temp":32,"rain_window_mm":(20,120)},
        {"name":"Millet", "preferred_texture":"sandy","min_ph":5.0,"max_ph":8.0,"min_temp":18,"max_temp":35,"rain_window_mm":(5,80)},
        {"name":"Sorghum","preferred_texture":"sandy","min_ph":5.5,"max_ph":8.0,"min_temp":20,"max_temp":38,"rain_window_mm":(8,100)},
        {"name":"Pulses", "preferred_texture":"loamy","min_ph":6.0,"max_ph":7.5,"min_temp":15,"max_temp":30,"rain_window_mm":(8,90)},
    ]

    def texture_score(field, pref): return 1.0 if str(field).lower()==str(pref).lower() else 0.5
    def ph_score(val, mn, mx):
        mid = (mn + mx)/2.0; tol = (mx - mn)/2.0 + 0.5; return max(0.0, 1 - abs(val-mid)/tol)
    def temp_overlap(fmin, fmax, cmin, cmax):
        if fmin is None or fmax is None: return 0.0
        lo, hi = max(fmin, cmin), min(fmax, cmax)
        overlap = max(0.0, hi - lo)
        span = max(1.0, cmax - cmin)
        return min(1.0, overlap/span)
    def rain_window(total, win):
        rmin, rmax = win
        if total <= rmin: return max(0.0, total/max(1.0, rmin))
        if total >= rmax: return max(0.0, 1.0 - (total - rmax)/max(1.0, rmax))
        return 1.0

    results: List[Dict[str, Any]] = []
    for c in crops:
        t_sc = texture_score(req.soil_type, c["preferred_texture"])
        p_sc = ph_score(req.ph, c["min_ph"], c["max_ph"])
        to_sc = temp_overlap(fmin, fmax, c["min_temp"], c["max_temp"])
        rw_sc = rain_window(precip, c["rain_window_mm"])
        score = 25*t_sc + 25*p_sc + 30*to_sc + 20*rw_sc
        results.append({
            "crop": c["name"],
            "score": round(score, 1),
            "reasons": {
                "texture_match": round(t_sc,2),
                "ph_fit": round(p_sc,2),
                "forecast_temp_min_c": fmin,
                "forecast_temp_max_c": fmax,
                "temp_overlap": round(to_sc,2),
                "forecast_precip_mm": precip,
                "rain_window_fit": round(rw_sc,2),
            }
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)
