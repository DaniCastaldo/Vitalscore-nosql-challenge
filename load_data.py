"""
VitalCore — Pipeline de ingesta a Redis
Carga todos los datos sintéticos respetando el modelo orientado a consultas.

ESQUEMA REDIS (orientado a patrones de acceso):
================================================

  MÉDICOS
  -------
  doctor:{id}                  HASH   → campos del médico
  specialty:{nombre}:doctors   SET    → IDs de médicos por especialidad
  doctors:all                  SET    → todos los IDs de médicos

  PACIENTES
  ---------
  patient:{id}                 HASH   → campos del paciente (incluye doctor_id, risk_level)
  patients:active              SET    → IDs de pacientes activos
  doctor:{id}:patients         SET    → IDs de pacientes asignados a un médico
  risk:{level}:patients        SET    → IDs de pacientes por nivel de riesgo

  TELEMETRÍA (Patrón 1 y 2)
  -------------------------
  telemetry:{patient_id}:{sensor}   ZSET   → score=ts_epoch, value="{reading_id}"
  reading:{reading_id}              HASH   → todos los campos del reading

  CONSULTAS CLÍNICAS (Patrón 1)
  ------------------------------
  patient:{id}:consultations   ZSET   → score=ts_epoch, value="{consult_id}"
  consultation:{id}            HASH   → campos de la consulta

  ALERTAS (Patrón 4)
  ------------------
  alert:{id}                   HASH   → detalle de la alerta
  alerts:active                ZSET   → score=ts_epoch, value="{alert_id}"
  patient:{id}:alerts          SET    → IDs de alertas de un paciente

  REFERIDOS (Patrón 5)
  --------------------
  referral:{id}                HASH   → detalle del referido
  patient:{id}:referrals       ZSET   → score=ts_epoch, value="{referral_id}"
"""

import json
import time
import redis
import uuid
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, SENSORS
from generate_data import generate_all


def get_redis_client() -> redis.Redis:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                    decode_responses=True)
    r.ping()
    print(f"  ✓ Conectado a Redis {REDIS_HOST}:{REDIS_PORT}")
    return r


# FLUSH (limpia la BD antes de recargar) ─

def flush_db(r: redis.Redis):
    r.flushdb()
    print("  ✓ Base de datos limpiada")


# MÉDICOS 

def load_doctors(r: redis.Redis, doctors: list[dict]):
    pipe = r.pipeline(transaction=False)
    for d in doctors:
        key = f"doctor:{d['id']}"
        pipe.hset(key, mapping={k: str(v) for k, v in d.items()})
        pipe.sadd("doctors:all", d["id"])
        pipe.sadd(f"specialty:{d['specialty']}:doctors", d["id"])
    pipe.execute()
    print(f"  ✓ {len(doctors)} médicos cargados")


# PACIENTES 

def load_patients(r: redis.Redis, patients: list[dict]):
    pipe = r.pipeline(transaction=False)
    for p in patients:
        key = f"patient:{p['id']}"
        flat = {k: str(v) for k, v in p.items() if not isinstance(v, list)}
        flat["conditions"] = json.dumps(p.get("conditions", []))
        pipe.hset(key, mapping=flat)

        if p["status"] == "active":
            pipe.sadd("patients:active", p["id"])
        pipe.sadd(f"doctor:{p['doctor_id']}:patients", p["id"])
        pipe.sadd(f"risk:{p['risk_level']}:patients", p["id"])
    pipe.execute()
    print(f"  ✓ {len(patients)} pacientes cargados")


# TELEMETRÍA 

def load_telemetry(r: redis.Redis, telemetry: list[dict]):
    """
    Carga en lotes de 5 000 para no saturar memoria del pipeline.
    Actualiza risk_level del paciente si detecta lectura crítica.
    """
    BATCH = 5_000
    alerts_generated = 0
    patient_max_risk: dict[str, str] = {}   # patient_id → peor riesgo visto

    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    for start in range(0, len(telemetry), BATCH):
        chunk = telemetry[start:start + BATCH]
        pipe  = r.pipeline(transaction=False)

        for t in chunk:
            rid = t["id"]
            # Almacenar detalle del reading
            pipe.hset(f"reading:{rid}", mapping={k: str(v) for k, v in t.items()})

            # Índice temporal por paciente+sensor (patrón 2)
            pipe.zadd(
                f"telemetry:{t['patient_id']}:{t['sensor']}",
                {rid: t["ts_epoch"]}
            )

            # Índice de última lectura por paciente (para dashboard médico)
            pipe.zadd(
                f"telemetry:{t['patient_id']}:all",
                {rid: t["ts_epoch"]}
            )

            # Alertas (patrón 4)
            if t["risk"] == "critical":
                alert_id = f"alert_{uuid.uuid4().hex[:10]}"
                pipe.hset(f"alert:{alert_id}", mapping={
                    "id":         alert_id,
                    "patient_id": t["patient_id"],
                    "sensor":     t["sensor"],
                    "value":      str(t["value"]),
                    "unit":       t["unit"],
                    "threshold":  str(SENSORS[t["sensor"]].get("critical_high") or
                                      SENSORS[t["sensor"]].get("critical_low")),
                    "timestamp":  t["timestamp"],
                    "ts_epoch":   str(t["ts_epoch"]),
                    "resolved":   "false",
                    "reading_id": rid,
                })
                pipe.zadd("alerts:active", {alert_id: t["ts_epoch"]})
                pipe.sadd(f"patient:{t['patient_id']}:alerts", alert_id)
                alerts_generated += 1

            # Rastrear peor riesgo del paciente
            curr = patient_max_risk.get(t["patient_id"], "low")
            if risk_order[t["risk"]] > risk_order[curr]:
                patient_max_risk[t["patient_id"]] = t["risk"]

        pipe.execute()
        print(f"    → {min(start + BATCH, len(telemetry))}/{len(telemetry)} lecturas cargadas")

    # Actualizar risk_level de cada paciente
    pipe = r.pipeline(transaction=False)
    for pat_id, risk in patient_max_risk.items():
        old_risk = r.hget(f"patient:{pat_id}", "risk_level") or "low"
        if risk != old_risk:
            pipe.hset(f"patient:{pat_id}", "risk_level", risk)
            pipe.smove(f"risk:{old_risk}:patients", f"risk:{risk}:patients", pat_id)
    pipe.execute()

    print(f"  ✓ {len(telemetry)} lecturas cargadas | {alerts_generated} alertas generadas")


# CONSULTAS 

def load_consultations(r: redis.Redis, consultations: list[dict]):
    pipe = r.pipeline(transaction=False)
    for c in consultations:
        cid = c["id"]
        pipe.hset(f"consultation:{cid}", mapping={k: str(v) for k, v in c.items()})
        # Índice cronológico por paciente (patrón 1)
        pipe.zadd(
            f"patient:{c['patient_id']}:consultations",
            {cid: c["ts_epoch"]}
        )
        # Índice por médico
        pipe.zadd(
            f"doctor:{c['doctor_id']}:consultations",
            {cid: c["ts_epoch"]}
        )
    pipe.execute()
    print(f"  ✓ {len(consultations)} consultas cargadas")


# REFERIDOS 

def load_referrals(r: redis.Redis, referrals: list[dict]):
    pipe = r.pipeline(transaction=False)
    for ref in referrals:
        rid = ref["id"]
        pipe.hset(f"referral:{rid}", mapping={k: str(v) for k, v in ref.items()})
        # Red de referidos por paciente (patrón 5)
        pipe.zadd(f"patient:{ref['patient_id']}:referrals", {rid: ref["ts_epoch"]})
        # Índice por médico destino
        pipe.sadd(f"doctor:{ref['to_doc_id']}:referrals_received", rid)
    pipe.execute()
    print(f"  ✓ {len(referrals)} referidos cargados")


# RESUMEN 

def print_summary(r: redis.Redis):
    print("  VitalCore Redis — Resumen de carga")
    print(f"  Médicos:           {r.scard('doctors:all')}")
    print(f"  Pacientes activos: {r.scard('patients:active')}")
    print(f"  Alertas activas:   {r.zcard('alerts:active')}")
    total_keys = r.dbsize()
    print(f"  Total de keys:     {total_keys:,}")


# MAIN 

def main():
    print("\n[VitalCore] Iniciando pipeline de ingesta...\n")
    t0 = time.time()

    data = generate_all()
    r    = get_redis_client()

    flush_db(r)
    print()
    load_doctors(r, data["doctors"])
    load_patients(r, data["patients"])
    load_telemetry(r, data["telemetry"])
    load_consultations(r, data["consultations"])
    load_referrals(r, data["referrals"])

    elapsed = time.time() - t0
    print(f"\n  ✓ Carga completada en {elapsed:.1f}s")
    print_summary(r)


if __name__ == "__main__":
    main()
