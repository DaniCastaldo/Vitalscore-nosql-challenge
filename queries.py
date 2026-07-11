"""
VitalCore — Capa de consulta
Implementa los 5 patrones de acceso críticos del proyecto más
consultas auxiliares para el dashboard.
"""

import json
import time
import redis
from typing import Optional
from config import REDIS_HOST, REDIS_PORT, REDIS_DB


def get_client() -> redis.Redis:
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                       decode_responses=True)


# PATRÓN 1 
# Historial clínico completo de un paciente, ordenado cronológicamente.
# Incluye consultas + lecturas de telemetría mezcladas en orden de tiempo.

def get_patient_full_history(patient_id: str,
                              limit: int = 50) -> dict:
    """
    Retorna el historial clínico cronológico de un paciente.
    Mezcla consultas y lecturas de telemetría en un solo timeline.
    Complejidad: O(log N + M)  → ZRANGE sobre ZSET
    """
    r     = get_client()
    t0    = time.perf_counter()
    result = {"patient_id": patient_id, "events": []}

    # Perfil del paciente
    patient = r.hgetall(f"patient:{patient_id}")
    if not patient:
        return {"error": "Paciente no encontrado"}
    patient["conditions"] = json.loads(patient.get("conditions", "[]"))
    result["patient"] = patient

    # Consultas ordenadas por tiempo (más reciente primero)
    consult_ids = r.zrange(
        f"patient:{patient_id}:consultations",
        0, limit - 1, desc=True
    )
    for cid in consult_ids:
        c = r.hgetall(f"consultation:{cid}")
        if c:
            c["type"] = "consultation"
            result["events"].append(c)

    # Últimas lecturas de telemetría (todas las de todos los sensores)
    tel_ids = r.zrange(
        f"telemetry:{patient_id}:all",
        0, limit - 1, desc=True
    )
    for tid in tel_ids:
        t = r.hgetall(f"reading:{tid}")
        if t:
            t["type"] = "telemetry"
            result["events"].append(t)

    # Mezclar y ordenar por timestamp
    result["events"].sort(key=lambda e: e.get("ts_epoch", "0"), reverse=True)
    result["events"] = result["events"][:limit]
    result["query_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return result


# PATRÓN 2 
# Lecturas de un sensor específico de un paciente en un rango de fechas.

def get_sensor_readings_in_range(patient_id: str,
                                  sensor: str,
                                  from_ts: int,
                                  to_ts: int) -> dict:
    """
    Retorna lecturas de telemetría por sensor y rango de tiempo.
    Complejidad: O(log N + M)  → ZRANGEBYSCORE
    """
    r  = get_client()
    t0 = time.perf_counter()

    reading_ids = r.zrangebyscore(
        f"telemetry:{patient_id}:{sensor}",
        from_ts, to_ts
    )

    readings = []
    if reading_ids:
        pipe = r.pipeline(transaction=False)
        for rid in reading_ids:
            pipe.hgetall(f"reading:{rid}")
        readings = [row for row in pipe.execute() if row]

    return {
        "patient_id": patient_id,
        "sensor":     sensor,
        "from_ts":    from_ts,
        "to_ts":      to_ts,
        "count":      len(readings),
        "readings":   readings,
        "query_ms":   round((time.perf_counter() - t0) * 1000, 2),
    }


# PATRÓN 3 
# Todos los pacientes activos de un médico con su última lectura vital.

def get_doctor_active_patients(doctor_id: str) -> dict:
    """
    Retorna pacientes activos de un médico + última lectura vital de cada uno.
    Complejidad: O(P * log T)  → SET lookup + ZRANGE -1 por paciente
    """
    r  = get_client()
    t0 = time.perf_counter()

    # IDs de pacientes del médico
    all_patient_ids  = r.smembers(f"doctor:{doctor_id}:patients")
    active_patient_ids = [
        pid for pid in all_patient_ids
        if r.hget(f"patient:{pid}", "status") == "active"
    ]

    doctor = r.hgetall(f"doctor:{doctor_id}")
    patients_data = []

    if active_patient_ids:
        pipe = r.pipeline(transaction=False)
        for pid in active_patient_ids:
            pipe.hgetall(f"patient:{pid}")
            # Última lectura vital (ZRANGE con desc=True, limit 1)
            pipe.zrange(f"telemetry:{pid}:all", -1, -1)
        results = pipe.execute()

        for i in range(0, len(results), 2):
            pat = results[i]
            if not pat:
                continue
            last_tel_ids = results[i + 1]

            last_reading = None
            if last_tel_ids:
                last_reading = r.hgetall(f"reading:{last_tel_ids[0]}")

            pat["conditions"] = json.loads(pat.get("conditions", "[]"))
            patients_data.append({
                "patient":      pat,
                "last_reading": last_reading,
            })

        # Ordenar por nivel de riesgo descendente
        risk_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        patients_data.sort(
            key=lambda x: risk_order.get(x["patient"].get("risk_level", "low"), 0),
            reverse=True
        )

    return {
        "doctor":          doctor,
        "active_patients": len(patients_data),
        "patients":        patients_data,
        "query_ms":        round((time.perf_counter() - t0) * 1000, 2),
    }


# PATRÓN 4 
# Alertas críticas activas (valores que superaron umbral).

def get_active_alerts(limit: int = 100,
                       patient_id: Optional[str] = None) -> dict:
    """
    Retorna alertas críticas sin resolver.
    Si se pasa patient_id, filtra sólo las de ese paciente.
    Complejidad: O(log N + M)  → ZRANGE sobre ZSET de alertas
    """
    r  = get_client()
    t0 = time.perf_counter()

    if patient_id:
        alert_ids = list(r.smembers(f"patient:{patient_id}:alerts"))
    else:
        alert_ids = r.zrange("alerts:active", 0, limit - 1, desc=True)

    alerts = []
    if alert_ids:
        pipe = r.pipeline(transaction=False)
        for aid in alert_ids[:limit]:
            pipe.hgetall(f"alert:{aid}")
        alerts = [a for a in pipe.execute() if a and a.get("resolved") == "false"]

    return {
        "total_active": r.zcard("alerts:active"),
        "returned":     len(alerts),
        "alerts":       alerts,
        "query_ms":     round((time.perf_counter() - t0) * 1000, 2),
    }


def resolve_alert(alert_id: str) -> dict:
    """Marca una alerta como resuelta y la elimina del ZSET activo."""
    r = get_client()
    r.hset(f"alert:{alert_id}", "resolved", "true")
    r.zrem("alerts:active", alert_id)
    return {"resolved": alert_id}


# PATRÓN 5 
# Red de referidos de un paciente 

def get_patient_referral_network(patient_id: str) -> dict:
    """
    Retorna la red de referidos del paciente:
    quién lo refirió y a quién fue referido.
    Complejidad: O(log N + M)  → ZRANGE + HGETALL por referido
    """
    r  = get_client()
    t0 = time.perf_counter()

    referral_ids = r.zrange(f"patient:{patient_id}:referrals", 0, -1, desc=True)
    referrals    = []

    if referral_ids:
        pipe = r.pipeline(transaction=False)
        for rid in referral_ids:
            pipe.hgetall(f"referral:{rid}")
        raw = pipe.execute()

        for ref in raw:
            if not ref:
                continue
            # Enriquecer con nombre de médicos
            from_doc = r.hgetall(f"doctor:{ref.get('from_doc_id')}")
            to_doc   = r.hgetall(f"doctor:{ref.get('to_doc_id')}")
            ref["from_doctor_name"]      = from_doc.get("name", "—")
            ref["from_doctor_specialty"] = from_doc.get("specialty", "—")
            ref["to_doctor_name"]        = to_doc.get("name", "—")
            ref["to_doctor_specialty"]   = to_doc.get("specialty", "—")
            referrals.append(ref)

    return {
        "patient_id":   patient_id,
        "total_referrals": len(referrals),
        "network":      referrals,
        "query_ms":     round((time.perf_counter() - t0) * 1000, 2),
    }


# DASHBOARD AUXILIAR 

def get_patient_dashboard(patient_id: str, last_n: int = 10) -> dict:
    """
    Dashboard del paciente: últimas N lecturas de cada sensor con indicadores de riesgo.
    """
    r    = get_client()
    t0   = time.perf_counter()
    pat  = r.hgetall(f"patient:{patient_id}")
    if not pat:
        return {"error": "Paciente no encontrado"}

    sensors_data = {}
    for sensor in ["glucose", "heart_rate", "spo2", "systolic_bp", "temperature"]:
        ids = r.zrange(f"telemetry:{patient_id}:{sensor}", -last_n, -1, desc=True)
        if ids:
            pipe = r.pipeline(transaction=False)
            for i in ids:
                pipe.hgetall(f"reading:{i}")
            sensors_data[sensor] = [x for x in pipe.execute() if x]

    pat["conditions"] = json.loads(pat.get("conditions", "[]"))
    return {
        "patient":    pat,
        "sensors":    sensors_data,
        "query_ms":   round((time.perf_counter() - t0) * 1000, 2),
    }


def get_platform_stats() -> dict:
    """Estadísticas generales de la plataforma para el dashboard administrativo."""
    r  = get_client()
    t0 = time.perf_counter()
    return {
        "total_active_patients":  r.scard("patients:active"),
        "active_alerts":          r.zcard("alerts:active"),
        "critical_patients":      r.scard("risk:critical:patients"),
        "high_risk_patients":     r.scard("risk:high:patients"),
        "medium_risk_patients":   r.scard("risk:medium:patients"),
        "low_risk_patients":      r.scard("risk:low:patients"),
        "query_ms":               round((time.perf_counter() - t0) * 1000, 2),
    }


# PRUEBA RÁPIDA EN CONSOLA 

if __name__ == "__main__":
    r = get_client()

    # Tomar un paciente y médico de ejemplo
    sample_patient = next(iter(r.smembers("patients:active")), None)
    sample_doctor  = next(iter(r.smembers("doctors:all")), None)

    if sample_patient:
        print("\n[P1] Historial clínico completo:")
        hist = get_patient_full_history(sample_patient, limit=5)
        print(f"  {len(hist['events'])} eventos | {hist['query_ms']}ms")

        print("\n[P2] Lecturas de glucosa (rango completo):")
        from datetime import datetime
        from_ts = int(datetime(2024, 1, 1).timestamp())
        to_ts   = int(datetime(2024, 6, 30).timestamp())
        readings = get_sensor_readings_in_range(sample_patient, "glucose", from_ts, to_ts)
        print(f"  {readings['count']} lecturas | {readings['query_ms']}ms")

        print("\n[P4] Alertas activas:")
        alerts = get_active_alerts(limit=5)
        print(f"  {alerts['total_active']} alertas activas | {alerts['query_ms']}ms")

        print("\n[P5] Red de referidos:")
        net = get_patient_referral_network(sample_patient)
        print(f"  {net['total_referrals']} referidos | {net['query_ms']}ms")

    if sample_doctor:
        print("\n[P3] Pacientes activos del médico:")
        dp = get_doctor_active_patients(sample_doctor)
        print(f"  {dp['active_patients']} pacientes activos | {dp['query_ms']}ms")

    print("\n[STATS] Plataforma:")
    stats = get_platform_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
