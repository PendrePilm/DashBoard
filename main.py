import os
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from garminconnect import Garmin

load_dotenv()

GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def format_time(seconds):
    """Formatte des secondes en HH:MM:SS ou MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def get_garmin_data(limit=200):
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        raw_activities = client.get_activities(0, limit)
        
        activities = []
        yearly_stats = defaultdict(lambda: {
            "count": 0, 
            "km": 0.0, 
            "hours": 0.0,
            "monthly_km": [0.0] * 12
        })

        # Variables pour tracker les meilleurs temps calculés
        best_5k = float('inf')
        best_10k = float('inf')
        best_half = float('inf')
        best_marathon = float('inf')

        for act in raw_activities:
            raw_type = act.get("activityType", {}).get("typeKey", "").lower()
            date_str = act.get("startTimeLocal", "")[:10]
            if not date_str:
                continue
                
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year = str(dt.year)
            month_idx = dt.month - 1

            dist_m = act.get("distance", 0)
            duration_sec = act.get("duration", 0)
            dist_km = round(dist_m / 1000, 2)
            duration_min = round(duration_sec / 60)

            # Identification du type de sport
            if "running" in raw_type or "run" in raw_type:
                act_type = "Running"
                is_run = True
            elif "cycling" in raw_type or "bike" in raw_type:
                act_type = "Cycling"
                is_run = False
            elif "swimming" in raw_type or "swim" in raw_type:
                act_type = "Swimming"
                is_run = False
            elif "walking" in raw_type or "hiking" in raw_type:
                act_type = "Walking"
                is_run = False
            else:
                act_type = raw_type.capitalize()
                is_run = False

            if is_run and dist_km > 0 and duration_sec > 0:
                # Statistiques annuelles (Course à pied uniquement)
                yearly_stats[year]["count"] += 1
                yearly_stats[year]["km"] += dist_km
                yearly_stats[year]["hours"] += duration_sec / 3600
                yearly_stats[year]["monthly_km"][month_idx] += dist_km

                # Detection automatique des meilleurs chronos
                # 5k (entre 4.9 km et 5.5 km)
                if 4.9 <= dist_km <= 5.5:
                    time_5k = duration_sec * (5.0 / dist_km)
                    if time_5k < best_5k:
                        best_5k = time_5k

                # 10k (entre 9.8 km et 10.8 km)
                if 9.8 <= dist_km <= 10.8:
                    time_10k = duration_sec * (10.0 / dist_km)
                    if time_10k < best_10k:
                        best_10k = time_10k

                # Semi-Marathon (entre 20.5 km et 22.0 km)
                if 20.5 <= dist_km <= 22.0:
                    time_half = duration_sec * (21.0975 / dist_km)
                    if time_half < best_half:
                        best_half = time_half

                # Marathon (entre 41.5 km et 43.5 km)
                if 41.5 <= dist_km <= 43.5:
                    time_marathon = duration_sec * (42.195 / dist_km)
                    if time_marathon < best_marathon:
                        best_marathon = time_marathon

            # Allure moyenne (min/km)
            pace_str = ""
            if dist_km > 0 and duration_min > 0:
                pace = duration_min / dist_km
                pace_min = int(pace)
                pace_sec = int((pace - pace_min) * 60)
                pace_str = f"{pace_min}:{pace_sec:02d} /km"

            activities.append({
                "name": act.get("activityName", "Activité"),
                "type": act_type,
                "is_run": is_run,
                "distance": dist_km,
                "duration": duration_min,
                "pace": pace_str,
                "elevation": round(act.get("elevationGain", 0)),
                "date": date_str,
                "year": year
            })

        # Formater les records calculés
        records = {
            "5k": format_time(best_5k) if best_5k != float('inf') else "--:--",
            "10k": format_time(best_10k) if best_10k != float('inf') else "--:--",
            "half_marathon": format_time(best_half) if best_half != float('inf') else "--:--",
            "marathon": format_time(best_marathon) if best_marathon != float('inf') else "--:--"
        }

        formatted_yearly = {}
        for yr in sorted(yearly_stats.keys(), reverse=True):
            formatted_yearly[yr] = {
                "year": yr,
                "count": yearly_stats[yr]["count"],
                "total_km": round(yearly_stats[yr]["km"], 1),
                "total_hours": round(yearly_stats[yr]["hours"], 1),
                "monthly_km": [round(x, 1) for x in yearly_stats[yr]["monthly_km"]]
            }

        return formatted_yearly, activities, records
    except Exception as e:
        print(f"Erreur Garmin : {e}")
        empty_prs = {"5k": "--:--", "10k": "--:--", "half_marathon": "--:--", "marathon": "--:--"}
        return {}, [], empty_prs

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/running", response_class=HTMLResponse)
def running_page(request: Request):
    yearly_stats, activities, records = get_garmin_data(limit=200)
    current_year = str(datetime.now().year)
    
    return templates.TemplateResponse(
        request=request, 
        name="running.html", 
        context={
            "yearly_stats": yearly_stats,
            "activities": activities,
            "records": records,
            "current_year": current_year
        }
    )