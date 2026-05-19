# BotDaily — Bot de Telegram para Reportes de Equipo

Bot de Telegram que guía al usuario a través de formularios dinámicos configurados en JSON. Al finalizar, envía un resumen formateado al administrador.

## Flujos disponibles

| Comando | Descripción |
|---------|-------------|
| `/daily` | Daily Standup: fecha, trabajo de ayer (horas + descripción), plan de hoy, bloqueos y reunión |
| `/incidencia` | Reporte de Incidencia: región, negocio, módulo, descripción y evidencia fotográfica (opcional) |
| `/cancelar` | Cancela cualquier flujo en curso |

## Requisitos

- Python 3.10 o superior
- Un bot de Telegram creado con [@BotFather](https://t.me/BotFather)
- Tu `ADMIN_CHAT_ID` (habla con [@userinfobot](https://t.me/userinfobot) para obtenerlo)

## Instalación

```bash
# 1. Clona el repositorio
git clone <url-del-repo>
cd BotDaily

# 2. Crea y activa un entorno virtual
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 3. Instala las dependencias
pip install -r requirements.txt

# 4. Configura las variables de entorno
cp .env.example .env
# Edita .env y rellena BOT_TOKEN y ADMIN_CHAT_ID
```

## Configuración

Edita el archivo `.env` con tus valores:

```env
BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_CHAT_ID=987654321
```

- **BOT_TOKEN**: Token proporcionado por @BotFather al crear el bot.
- **ADMIN_CHAT_ID**: ID del chat (tuyo o de un grupo) donde llegarán los reportes. Puede ser negativo si es un grupo.

## Ejecución

```bash
python main.py
```

El bot arrancará en modo polling. Verás en consola los flujos cargados y que el bot está activo.

## Estructura del Proyecto

```
BotDaily/
├── main.py                  # Punto de entrada: carga flujos, construye la app
├── .env                     # Variables secretas (no subir al repo)
├── .env.example             # Plantilla de .env
├── requirements.txt
├── README.md
├── bot/
│   ├── __init__.py
│   ├── conversation.py      # Motor dinámico: construye ConversationHandlers desde JSON
│   ├── flow_loader.py       # Carga y valida archivos flow.json
│   ├── validator.py         # Validadores por tipo de dato
│   ├── formatter.py         # Formatea el resumen final para el admin
│   └── state_store.py       # Almacena respuestas por usuario en memoria
└── flows/
    ├── daily_flow.json      # Definición del flujo Daily Standup
    └── incidencia_flow.json # Definición del flujo Reporte de Incidencia
```

## Cómo agregar un nuevo flujo

1. Crea un archivo `flows/mi_flujo.json` siguiendo el esquema documentado abajo.
2. Reinicia el bot. El nuevo flujo se cargará automáticamente.

No es necesario modificar ningún archivo Python.

## Esquema de un flujo JSON

```json
{
  "flow_id": "mi_flujo",
  "command": "/comando",
  "title": "Título del Flujo",
  "steps": [
    {
      "id": "step_ejemplo",
      "question": "¿Pregunta al usuario?\n*Ej:* respuesta de ejemplo",
      "validation": { "type": "text" },
      "optional": false,
      "keyboard": null,
      "next_step": "step_siguiente"
    },
    {
      "id": "step_opciones",
      "question": "¿Selecciona una opción?",
      "validation": { "type": "boolean", "choices": ["Sí", "No"] },
      "optional": false,
      "keyboard": {
        "enabled": true,
        "layout": "row",
        "buttons": [
          {"label": "Sí", "value": "yes"},
          {"label": "No", "value": "no"}
        ]
      },
      "next_step": {
        "type": "conditional",
        "on": "step_opciones",
        "cases": { "yes": "step_si", "no": null },
        "default": null
      }
    }
  ],
  "summary_template": "mi_flujo"
}
```

### Tipos de validación

| Tipo | Descripción | Campos adicionales |
|------|-------------|-------------------|
| `text` | Texto libre | — |
| `number` | Número entero o decimal | `min`, `max` (opcionales) |
| `date` | Fecha | `date_format` (ej: `DD/MM/YYYY`) |
| `email` | Correo electrónico | — |
| `regex` | Expresión regular | `pattern` |
| `boolean` | Sí/No con botones | `choices` |
| `options` | Lista de opciones con botones | `choices` |
| `photo` | Imagen enviada por Telegram | — |

### Tipos de `next_step`

- `"step_id"` — avanza directamente al paso indicado
- `null` — fin del flujo, dispara el resumen al admin
- Objeto condicional — bifurca según la respuesta:

```json
{
  "type": "conditional",
  "on": "id_del_paso_cuya_respuesta_se_evalua",
  "cases": {
    "yes": "paso_si_es_si",
    "no": null
  },
  "default": null
}
```

## Notas sobre fotos (evidencia)

- El bot almacena el `file_id` de Telegram, no el archivo físico.
- Al finalizar el flujo, el bot reenvía la foto directamente al `ADMIN_CHAT_ID`.
- Si el paso de foto es opcional (`"optional": true`), el usuario puede enviar `/skip` para omitirlo.

---

## Despliegue en k3s (Kubernetes ligero)

### Arquitectura del despliegue

```
Tu PC (Windows)                   Servidor (VM con k3s, sin Docker)
──────────────────                ─────────────────────────────────
docker build ...                  sudo k3s ctr images import botdaily.tar
docker save → botdaily.tar   →    kubectl apply -f k8s/
scp al servidor                   Pod corriendo ✓
```

> **¿Por qué solo 1 réplica?** El bot usa long-polling. Si corren 2 pods al mismo tiempo, ambos procesarían el mismo mensaje dos veces.

---

### Paso 1 — Preparar el servidor (una sola vez)

Conéctate por SSH al servidor y ejecuta:

```bash
# Configurar kubectl sin sudo
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(whoami):$(whoami) ~/.kube/config

# Verificar que k3s está listo
kubectl get nodes
# NAME      STATUS   ROLES                  AGE
# mi-vm     Ready    control-plane,master   5m

# Crear carpeta del proyecto y el .env
mkdir -p ~/BotDaily
cp .env.example ~/BotDaily/.env   # o créalo manualmente
nano ~/BotDaily/.env
```

Contenido del `.env` en el servidor:

```env
BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_CHAT_ID=987654321
USE_PROXY=false
```

---

### Paso 2 — Construir y subir desde tu PC (Windows)

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
# Reemplaza usuario@IP con los datos reales de tu servidor
.\build.ps1 -Server usuario@192.168.1.50
```

El script hace:
1. `docker build` — construye la imagen en tu PC
2. `docker save` — la exporta a `botdaily.tar`
3. `scp` — sube el tar y la carpeta `k8s/` al servidor
4. Te muestra el comando exacto para terminar en el servidor

---

### Paso 3 — Desplegar en el servidor

```bash
ssh usuario@192.168.1.50
cd ~/BotDaily
chmod +x deploy.sh
./deploy.sh
```

Salida esperada:

```
[INFO] Importando botdaily:latest en k3s containerd...
[OK]   Imagen importada
[OK]   Namespace 'botdaily' listo
[OK]   Secret aplicado
[OK]   ConfigMap aplicado
[OK]   Deployment aplicado
[OK]   Pod corriendo

════════════════════════════════════════
  BotDaily desplegado correctamente ✓
════════════════════════════════════════
```

---

### Actualizar después de cambios en el código

```powershell
# En tu PC — reconstruye y sube
.\build.ps1 -Server usuario@192.168.1.50
```

```bash
# En el servidor — reimporta y reinicia el pod
cd ~/BotDaily && ./deploy.sh --update
```

---

### Comandos útiles en el servidor

```bash
# Estado del pod
kubectl get pods -n botdaily

# Logs en tiempo real
kubectl logs -f deployment/botdaily -n botdaily

# Reiniciar sin cambios
kubectl rollout restart deployment/botdaily -n botdaily

# Actualizar solo config (sin nueva imagen)
kubectl apply -f k8s/configmap.yaml
kubectl rollout restart deployment/botdaily -n botdaily
```

---

### Solución de problemas

**Pod en CrashLoopBackOff:**
```bash
kubectl logs deployment/botdaily -n botdaily --previous
# Causas comunes: BOT_TOKEN incorrecto, ADMIN_CHAT_ID mal puesto
```

**Imagen no encontrada (ErrImageNeverPull):**
```bash
sudo k3s ctr images list | grep botdaily
# Si no aparece: sube el tar de nuevo y corre ./deploy.sh --update
```

**Ver todos los eventos:**
```bash
kubectl get events -n botdaily --sort-by='.lastTimestamp'
```

**Borrar todo y empezar de cero:**
```bash
kubectl delete namespace botdaily
./deploy.sh   # primer despliegue limpio
```

---

## Licencia

MIT
