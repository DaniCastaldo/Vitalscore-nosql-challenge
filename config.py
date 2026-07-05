import os

# Redis  
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))

# Volumen de datos  
NUM_PATIENTS      = 500
NUM_DOCTORS       = 50
NUM_TELEMETRY     = 200_000
NUM_CONSULTATIONS = 1_000
NUM_REFERRALS     = 300   # red de referidos

# Periodo simulado  
SIM_START = "2024-01-01"
SIM_END   = "2024-06-30"

# Especialidades médicas
SPECIALTIES = [
    "Cardiología",
    "Endocrinología",
    "Medicina General",
    "Neurología",
    "Neumología",
    "Nefrología",
    "Oncología",
]

# Sensores / tipos de telemetría 
# Cada sensor tiene: unidad, rango plausible, umbral crítico bajo, umbral crítico alto
SENSORS = {
    "glucose": {
        "unit": "mg/dL",
        "normal_min": 70,
        "normal_max": 140,
        "plausible_min": 40,
        "plausible_max": 450,
        "critical_low": 60,
        "critical_high": 250,
    },
    "heart_rate": {
        "unit": "bpm",
        "normal_min": 60,
        "normal_max": 100,
        "plausible_min": 35,
        "plausible_max": 200,
        "critical_low": 45,
        "critical_high": 150,
    },
    "spo2": {
        "unit": "%",
        "normal_min": 95,
        "normal_max": 100,
        "plausible_min": 80,
        "plausible_max": 100,
        "critical_low": 90,
        "critical_high": None,   # no hay crítico alto para SpO2
    },
    "systolic_bp": {
        "unit": "mmHg",
        "normal_min": 90,
        "normal_max": 130,
        "plausible_min": 70,
        "plausible_max": 200,
        "critical_low": 80,
        "critical_high": 180,
    },
    "temperature": {
        "unit": "°C",
        "normal_min": 36.1,
        "normal_max": 37.2,
        "plausible_min": 34.0,
        "plausible_max": 41.5,
        "critical_low": 35.0,
        "critical_high": 39.5,
    },
    "sleep_hours": {
        "unit": "h",
        "normal_min": 6,
        "normal_max": 9,
        "plausible_min": 2,
        "plausible_max": 12,
        "critical_low": 3,
        "critical_high": None,
    },
}

# Grupos de riesgo  
RISK_LEVELS = ["low", "medium", "high", "critical"]

# Tipos de sangre  
BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
