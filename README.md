══════════════════════════════════════════════════════════════
  VitalCore: NoSQL Implementation Challenge (Redis)
  Proyecto #02 Tópicos Especiales para la Gestión de Datos
══════════════════════════════════════════════════════════════

PASOS PARA LEVANTAR EL PROYECTO DESDE CERO

╔═══════════════════════════════════╗
║  PASO 1 — Instalar Docker Desktop ║
╚═══════════════════════════════════╝

1. Ir a: https://www.docker.com/products/docker-desktop/
2. Descargar para Windows (o Mac)
3. Instalar y reiniciar la computadora si pide
4. Abrir Docker Desktop y esperar que el ícono de la ballena
   aparezca verde (Running)


╔══════════════════════════════════╗
║  PASO 2 — Levantar Redis         ║
╚══════════════════════════════════╝

Abrir una terminal (PowerShell o CMD) en la carpeta del proyecto:

  cd vitalcore (nombre de la carpeta donde se tengan los archivos del proyecto)
  docker compose up -d

Esto descarga la imagen de Redis Stack 
Cuando termine verás:
   Container vitalcore_redis  Started

Para verificar que está corriendo:
  docker ps

Deberías ver "vitalcore_redis" con status "Up".

Además en el navegador:
  http://localhost:8001


╔══════════════════════════════════╗
║  PASO 3 — Python y dependencias  ║
╚══════════════════════════════════╝

Necesitas Python 3.11 o superior.
Descarga desde: https://www.python.org/downloads/

Instalar dependencias:
  pip install -r requirements.txt

Entorno virtual:
  python -m venv venv
  venv\Scripts\activate        ← Windows
  source venv/bin/activate     ← Mac/Linux
  pip install -r requirements.txt


╔══════════════════════════════════╗
║  PASO 4 — Generar y cargar datos ║
╚══════════════════════════════════╝

Un solo comando que hace todo:
  python load_data.py

Esto:
  1. Genera 500 pacientes, 50 médicos, 200.000 lecturas,
     1.000 consultas y ~300 referidos (datos sintéticos)
  2. Los carga en Redis respetando el esquema orientado a consultas
  3. Genera data_dump.json (útil para Power BI y debug)
En consola:
  50 médicos generados
  500 pacientes generados
  200000 lecturas generadas
  ...
  Carga completada en Xs


╔═════════════════════════╗
║ PASO 5 — Iniciar la API ║
╚═════════════════════════╝

  uvicorn api:app --reload --port 8000

Deja esa terminal corriendo.
Abre en el navegador:
  http://localhost:8000         → health check
  http://localhost:8000/docs    → documentación interactiva automática (Swagger)
  http://localhost:8000/stats   → KPIs de la plataforma


╔═══════════════════════════════════════════════╗
║  PASO 6 — Conectar Power BI                   ║
╚═══════════════════════════════════════════════╝

La API expone endpoints CSV especialmente para Power BI:

  http://localhost:8000/export/alerts    → alertas activas
  http://localhost:8000/export/patients  → pacientes activos con riesgo
  http://localhost:8000/export/doctors   → médicos

Para conectar en Power BI Desktop:
  1. Abrir Power BI Desktop
  2. Inicio → Obtener datos → Web
  3. Pegar la URL (ej: http://localhost:8000/export/patients)
  4. Power BI carga la tabla automáticamente
  5. Repetir para cada endpoint
  6. Crear relaciones entre tablas usando doctor_id / patient_id

Visualizaciones sugeridas en Power BI:
  - Tarjeta: Total alertas activas
  - Tarjeta: Pacientes críticos
  - Gráfico de barras: Pacientes por nivel de riesgo
  - Gráfico de torta: Médicos por especialidad
  - Tabla: Alertas activas con paciente y sensor
  - Filtro: Por especialidad del médico


╔══════════════════════════════════════════════╗
║  ENDPOINTS DE LA API (Patrones de Acceso)    ║
╚══════════════════════════════════════════════╝

PATRÓN 1 — Historial clínico completo cronológico:
  GET /patients/{patient_id}/history?limit=50

PATRÓN 2 — Lecturas de un sensor en rango de fechas:
  GET /patients/{patient_id}/telemetry/glucose?from_ts=1704067200&to_ts=1719705600
  (timestamps Unix: 2024-01-01 → 2024-06-30)

PATRÓN 3 — Pacientes activos de un médico con última vital:
  GET /doctors/{doctor_id}/patients

PATRÓN 4 — Alertas críticas activas:
  GET /alerts/active?limit=100

PATRÓN 5 — Red de referidos de un paciente:
  GET /patients/{patient_id}/referrals

DASHBOARD paciente:
  GET /patients/{patient_id}/dashboard?last_n=10

RESOLVER alerta:
  POST /alerts/{alert_id}/resolve


╔═══════════════════════════════════════════════╗
║  ESTRUCTURA DEL PROYECTO                      ║
╚═══════════════════════════════════════════════╝

vitalcore/
├── docker-compose.yml   → levanta Redis Stack
├── requirements.txt     → dependencias Python
├── config.py            → configuración y constantes
├── generate_data.py     → generador de datos sintéticos
├── load_data.py         → pipeline de ingesta a Redis
├── queries.py           → los 5 patrones de acceso
├── api.py               → API REST (FastAPI)
├── SETUP.txt            → este archivo
└── data_dump.json       → generado al ejecutar load_data.py
                           (sirve para Power BI / debug)


