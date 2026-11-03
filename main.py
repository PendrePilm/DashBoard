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

def get_garmin_data(limit=150):
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

            # Identification du type pour l'icône/affichage
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

            # Cumul des stats annuelles UNIQUEMENT si c'est du Running
            if is_run:
                yearly_stats[year]["count"] += 1
                yearly_stats[year]["km"] += dist_km
                yearly_stats[year]["hours"] += duration_sec / 3600
                yearly_stats[year]["monthly_km"][month_idx] += dist_km

            # Calcul de l'allure (min/km)
            pace_str = ""
            if dist_km > 0 and duration_min > 0:
                pace = duration_min / dist_km
                pace_min = int(pace)
                pace_sec = int((pace - pace_min) * 60)
                pace_str = f"{pace_min}:{pace_sec:02d} /km"

            # ON AJOUTE TOUTES LES ACTIVITÉS DANS LA LISTE
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

        formatted_yearly = {}
        for yr in sorted(yearly_stats.keys(), reverse=True):
            formatted_yearly[yr] = {
                "year": yr,
                "count": yearly_stats[yr]["count"],
                "total_km": round(yearly_stats[yr]["km"], 1),
                "total_hours": round(yearly_stats[yr]["hours"], 1),
                "monthly_km": [round(x, 1) for x in yearly_stats[yr]["monthly_km"]]
            }

        return formatted_yearly, activities
    except Exception as e:
        print(f"Erreur Garmin : {e}")
        return {}, []

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/running", response_class=HTMLResponse)
def running_page(request: Request):
    yearly_stats, activities = get_garmin_data(limit=150)
    current_year = str(datetime.now().year)
    
    return templates.TemplateResponse(
        request=request, 
        name="running.html", 
        context={
            "yearly_stats": yearly_stats,
            "activities": activities,
            "current_year": current_year
        }
    )