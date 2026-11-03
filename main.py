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
            "monthly_km": [0.0] * 12,
            "types": defaultdict(int)
        })

        for act in raw_activities:
            dist_m = act.get("distance", 0)
            duration_sec = act.get("duration", 0)
            date_str = act.get("startTimeLocal", "")[:10]  # "YYYY-MM-DD"
            
            if not date_str:
                continue
                
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year = str(dt.year)
            month_idx = dt.month - 1

            dist_km = round(dist_m / 1000, 2)
            duration_min = round(duration_sec / 60)
            act_type = act.get("activityType", {}).get("typeKey", "running").capitalize()
            
            # Statistiques par année
            yearly_stats[year]["count"] += 1
            yearly_stats[year]["km"] += dist_km
            yearly_stats[year]["hours"] += duration_sec / 3600
            yearly_stats[year]["monthly_km"][month_idx] += dist_km
            yearly_stats[year]["types"][act_type] += 1

            # Calcul de l'allure (min/km)
            pace_str = ""
            if dist_km > 0 and duration_min > 0:
                pace = duration_min / dist_km
                pace_min = int(pace)
                pace_sec = int((pace - pace_min) * 60)
                pace_str = f"{pace_min}:{pace_sec:02d} /km"

            activities.append({
                "name": act.get("activityName", "Activité"),
                "type": act_type,
                "distance": dist_km,
                "duration": duration_min,
                "pace": pace_str,
                "elevation": round(act.get("elevationGain", 0)),
                "date": date_str,
                "year": year
            })

        # Dictionnaire obligatoire pour Jinja2 (.items())
        formatted_yearly = {}
        for yr in sorted(yearly_stats.keys(), reverse=True):
            formatted_yearly[yr] = {
                "year": yr,
                "count": yearly_stats[yr]["count"],
                "total_km": round(yearly_stats[yr]["km"], 1),
                "total_hours": round(yearly_stats[yr]["hours"], 1),
                "monthly_km": [round(x, 1) for x in yearly_stats[yr]["monthly_km"]],
                "types": dict(yearly_stats[yr]["types"])
            }

        return formatted_yearly, activities
    except Exception as e:
        print(f"Erreur Garmin : {e}")
        # Dictionnaire vide {} pour éviter l'erreur Jinja2
        return {}, []

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html"
    )

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