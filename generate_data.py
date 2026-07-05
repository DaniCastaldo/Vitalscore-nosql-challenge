"""
VitalCore — Generador de datos 
Genera pacientes, médicos, telemetría, consultas y referidos
con coherencia médica real.
"""

import json
import random
import uuid
from datetime import datetime, timedelta

from faker import Faker
from faker.providers import person, address, phone_number

from config import (
    NUM_PATIENTS, NUM_DOCTORS, NUM_TELEMETRY,
    NUM_CONSULTATIONS, NUM_REFERRALS,
    SIM_START, SIM_END,
    SPECIALTIES, SENSORS, BLOOD_TYPES
)

fake = Faker("es_MX")
random.seed(42)

SIM_START_DT = datetime.strptime(SIM_START, "%Y-%m-%d")
SIM_END_DT   = datetime.strptime(SIM_END,   "%Y-%m-%d")
SIM_RANGE    = (SIM_END_DT - SIM_START_DT).days


def random_ts(start: datetime = SIM_START_DT, end: datetime = SIM_END_DT) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.random() * delta)


def risk_for_reading(sensor: str, value: float) -> str:
    cfg = SENSORS[sensor]
    low  = cfg["critical_low"]
    high = cfg["critical_high"]

    if low is not None and value <= low:
        return "critical"
    if high is not None and value >= high:
        return "critical"
    if value < cfg["normal_min"] or (high is not None and value > cfg["normal_max"]):
        return "high"
    if value > cfg["normal_max"]:
        return "medium"
    return "low"


# MÉDICOS 

def generate_doctors(n: int) -> list[dict]:
    doctors = []
    specialties_cycle = SPECIALTIES * (n // len(SPECIALTIES) + 1)
    random.shuffle(specialties_cycle)

    for i in range(n):
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doctors.append({
            "id":         doc_id,
            "name":       fake.name(),
            "specialty":  specialties_cycle[i],
            "license":    f"MP-{random.randint(10000, 99999)}",
            "phone":      fake.phone_number(),
            "email":      fake.email(),
            "clinic":     fake.company() + " Clínica",
            "active":     True,
        })
    print(f"  ✓ {n} médicos generados")
    return doctors


# PACIENTES 

def generate_patients(n: int, doctors: list[dict]) -> list[dict]:
    patients = []
    doctor_ids = [d["id"] for d in doctors]

    for _ in range(n):
        dob = fake.date_of_birth(minimum_age=18, maximum_age=90)
        age = (datetime.today().date() - dob).days // 365
        pat_id = f"pat_{uuid.uuid4().hex[:8]}"

        # Condiciones crónicas simuladas
        conditions = []
        if age > 50:
            conditions += random.sample(
                ["Hipertensión", "Diabetes Tipo 2", "Obesidad", "Dislipidemia"],
                k=random.randint(0, 2)
            )

        patients.append({
            "id":          pat_id,
            "name":        fake.name(),
            "dob":         str(dob),
            "age":         age,
            "gender":      random.choice(["M", "F"]),
            "blood_type":  random.choice(BLOOD_TYPES),
            "phone":       fake.phone_number(),
            "email":       fake.email(),
            "address":     fake.address(),
            "doctor_id":   random.choice(doctor_ids),
            "status":      random.choices(["active", "inactive"], weights=[85, 15])[0],
            "conditions":  conditions,
            "registered":  str(random_ts(
                SIM_START_DT - timedelta(days=365),
                SIM_START_DT
            ).date()),
            "risk_level":  "low",  # se recalcula al ingerir telemetría
        })

    print(f"  ✓ {n} pacientes generados")
    return patients


# TELEMETRÍA 

def generate_telemetry(n: int, patients: list[dict]) -> list[dict]:
    """
    Distribuye N lecturas entre los pacientes de forma ponderada.
    Pacientes con condiciones crónicas tienen más frecuencia de lecturas.
    """
    readings = []
    patient_ids = [p["id"] for p in patients]
    sensor_names = list(SENSORS.keys())

    # Pesos: pacientes con condiciones y lecturas
    weights = []
    for p in patients:
        w = 1 + len(p.get("conditions", [])) * 0.5
        weights.append(w)
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    chosen_patients = random.choices(patient_ids, weights=weights, k=n)

    for pat_id in chosen_patients:
        sensor = random.choice(sensor_names)
        cfg    = SENSORS[sensor]

        # Valor con distribución normal centrada en el rango normal
        mean  = (cfg["normal_min"] + cfg["normal_max"]) / 2
        sigma = (cfg["normal_max"] - cfg["normal_min"]) * 0.4
        value = random.gauss(mean, sigma)

        # 8% de probabilidad de valor fuera de rango (alerta)
        if random.random() < 0.08:
            value = random.uniform(cfg["plausible_min"], cfg["plausible_max"])

        value = round(
            max(cfg["plausible_min"], min(cfg["plausible_max"], value)),
            2
        )

        ts    = random_ts()
        risk  = risk_for_reading(sensor, value)

        readings.append({
            "id":         f"tel_{uuid.uuid4().hex[:10]}",
            "patient_id": pat_id,
            "sensor":     sensor,
            "value":      value,
            "unit":       cfg["unit"],
            "risk":       risk,
            "timestamp":  ts.isoformat(),
            "ts_epoch":   int(ts.timestamp()),
            "device":     random.choice(["Fitbit", "Apple Watch", "Garmin", "Withings", "Manual"]),
        })

    # Ordenar por timestamp para facilitar carga
    readings.sort(key=lambda r: r["ts_epoch"])
    print(f"  ✓ {n} lecturas de telemetría generadas")
    return readings


# CONSULTAS MÉDICAS 

DIAGNOSES = [
    "Hipertensión arterial controlada",
    "Diabetes Mellitus Tipo 2 — ajuste de dosis",
    "Infección respiratoria aguda",
    "Control rutinario anual",
    "Evaluación post-quirúrgica",
    "Fibromialgia — seguimiento",
    "Hipotiroidismo en tratamiento",
    "Anemia ferropénica",
    "Arritmia cardíaca — monitoreo",
    "Ansiedad generalizada",
]

def generate_consultations(n: int, patients: list[dict], doctors: list[dict]) -> list[dict]:
    consultations = []
    pat_map = {p["id"]: p for p in patients}

    for _ in range(n):
        patient = random.choice(patients)
        # Preferir médico asignado (70%) o cualquier otro (30%)
        if random.random() < 0.7:
            doc_id = patient["doctor_id"]
        else:
            doc_id = random.choice(doctors)["id"]

        ts = random_ts()
        consultations.append({
            "id":           f"cons_{uuid.uuid4().hex[:10]}",
            "patient_id":   patient["id"],
            "doctor_id":    doc_id,
            "timestamp":    ts.isoformat(),
            "ts_epoch":     int(ts.timestamp()),
            "diagnosis":    random.choice(DIAGNOSES),
            "notes":        fake.paragraph(nb_sentences=random.randint(3, 8)),
            "prescription": f"{fake.word().capitalize()} {random.randint(5,500)}mg c/{random.randint(6,24)}h",
            "follow_up_days": random.choice([7, 14, 30, 60, 90]),
        })

    consultations.sort(key=lambda c: c["ts_epoch"])
    print(f"  ✓ {n} consultas médicas generadas")
    return consultations


# REFERIDOS 

REFERRAL_REASONS = [
    "Evaluación cardiovascular",
    "Control glucémico avanzado",
    "Estudio neurológico",
    "Seguimiento oncológico",
    "Evaluación renal",
    "Segunda opinión diagnóstica",
    "Manejo de dolor crónico",
]

def generate_referrals(n: int, patients: list[dict], doctors: list[dict]) -> list[dict]:
    referrals = []
    doc_by_specialty = {}
    for d in doctors:
        doc_by_specialty.setdefault(d["specialty"], []).append(d["id"])

    for _ in range(n):
        patient   = random.choice(patients)
        from_doc  = patient["doctor_id"]
        # Referir a especialidad diferente
        to_spec   = random.choice(SPECIALTIES)
        to_doc    = random.choice(doc_by_specialty.get(to_spec, doctors))["id"] \
                    if isinstance(random.choice(doc_by_specialty.get(to_spec, doctors)), dict) \
                    else random.choice(doc_by_specialty.get(to_spec, [d["id"] for d in doctors]))

        if from_doc == to_doc:
            continue

        ts = random_ts()
        referrals.append({
            "id":          f"ref_{uuid.uuid4().hex[:10]}",
            "patient_id":  patient["id"],
            "from_doc_id": from_doc,
            "to_doc_id":   to_doc,
            "to_specialty": to_spec,
            "reason":      random.choice(REFERRAL_REASONS),
            "timestamp":   ts.isoformat(),
            "ts_epoch":    int(ts.timestamp()),
            "status":      random.choice(["pending", "completed", "cancelled"]),
        })

    print(f"  ✓ {len(referrals)} referidos generados")
    return referrals


# MAIN 

def generate_all() -> dict:
    print("\n[VitalCore] Generando datos sintéticos...")
    doctors       = generate_doctors(NUM_DOCTORS)
    patients      = generate_patients(NUM_PATIENTS, doctors)
    telemetry     = generate_telemetry(NUM_TELEMETRY, patients)
    consultations = generate_consultations(NUM_CONSULTATIONS, patients, doctors)
    referrals     = generate_referrals(NUM_REFERRALS, patients, doctors)

    data = {
        "doctors":       doctors,
        "patients":      patients,
        "telemetry":     telemetry,
        "consultations": consultations,
        "referrals":     referrals,
    }

    # Guardar JSON para Power BI
    with open("data_dump.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n  ✓ data_dump.json guardado (útil para Power BI / debug)\n")

    return data


if __name__ == "__main__":
    generate_all()
