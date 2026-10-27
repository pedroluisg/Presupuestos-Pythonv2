import os
import sqlite3
import json
import time
import traceback
import urllib.request
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, UploadFile, File, Body, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("❌ Error: No se ha encontrado la variable GEMINI_API_KEY en tu archivo .env")

client = genai.Client(api_key=api_key)
app = FastAPI()

NOMBRE_COMERCIAL_DEFAULT = "Fontanería y Desatascos El Rápido"
TELEFONO_DEFAULT = "600123456"

def registrar_uso_sheets(gremio: str, urgencia: str, user_agent: str, ip_cliente: str, pais_base: str):
    """Envía el registro anónimo de uso con ciudad y provincia a Google Sheets en segundo plano."""
    webhook_url = os.environ.get("SHEETS_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    ua_lower = user_agent.lower()
    if "iphone" in ua_lower or "ipad" in ua_lower:
        dispositivo = "iPhone / iPad"
    elif "android" in ua_lower:
        dispositivo = "Móvil Android"
    else:
        dispositivo = "Ordenador / Otro"

    ubicacion = pais_base
    if ip_cliente:
        try:
            geo_url = f"http://ip-api.com/json/{ip_cliente}?fields=status,countryCode,regionName,city&lang=es"
            with urllib.request.urlopen(geo_url, timeout=3) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))
                if geo_data.get("status") == "success":
                    ciudad = geo_data.get("city", "")
                    region = geo_data.get("regionName", "")
                    pais = geo_data.get("countryCode", pais_base)
                    if ciudad and region:
                        ubicacion = f"{ciudad}, {region} ({pais})"
                    elif ciudad:
                        ubicacion = f"{ciudad} ({pais})"
        except Exception:
            pass

    datos = {
        "gremio": gremio,
        "urgencia": urgencia,
        "dispositivo": dispositivo,
        "ubicacion": ubicacion,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(datos).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Aviso: No se pudo guardar la estadística en Sheets: {e}")

# ==========================================
# 1. INTERFAZ WEB MÓVIL (FRONTEND COMPLETO)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Asistente Técnico de Fontanería</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 min-h-screen p-4 flex flex-col items-center pb-12">
        <div class="w-full max-w-lg bg-slate-800 rounded-2xl shadow-2xl p-6 border border-slate-700 mt-2 text-center">
            <h1 class="text-2xl font-extrabold text-blue-400 mb-1 flex items-center justify-center gap-2">🔧 Asistente de Fontanería</h1>
            <p class="text-slate-400 text-xs mb-6">Habla con naturalidad usando tu jerga de obra. La IA transcribirá y desglosará tareas, materiales e IVA.</p>
            
            <!-- GRABACIÓN EN DIRECTO -->
            <div class="flex flex-col items-center gap-3 mb-5">
                <button id="recordBtn" class="w-20 h-20 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-9 w-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </button>
                <div id="recordStatus" class="text-xs font-medium text-slate-300">Toca el micrófono para describir la avería o instalación</div>
            </div>

            <!-- SUBIDA DE ARCHIVO -->
            <div class="border-t border-slate-700 pt-4">
                <p class="text-xs text-slate-400 mb-2">O adjunta una nota de voz guardada:</p>
                <div class="flex gap-2">
                    <input type="file" id="audioFile" accept="audio/*" class="w-full text-xs text-slate-400 file:mr-2 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-700 file:text-blue-300 hover:file:bg-slate-600 cursor-pointer">
                    <button id="uploadBtn" class="bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-4 rounded-lg transition text-xs whitespace-nowrap shadow">
                        📂 Analizar Audio
                    </button>
                </div>
            </div>
            
            <div id="loading" class="hidden text-center py-6">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mx-auto mb-2"></div>
                <p class="text-xs text-blue-300">Transcribiendo jerga de fontanería y calculando presupuesto...</p>
            </div>
        </div>

        <!-- PANTALLA DE REVISIÓN Y EDICIÓN -->
        <div id="resultadoContainer" class="w-full max-w-lg mt-4 hidden"></div>

        <script>
            let mediaRecorder, audioChunks = [], isRecording = false;
            const recordBtn = document.getElementById('recordBtn');
            const recordStatus = document.getElementById('recordStatus');
            const uploadBtn = document.getElementById('uploadBtn');

            recordBtn.addEventListener('click', async () => {
                if (!isRecording) {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ 
                            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } 
                        });
                        mediaRecorder = new MediaRecorder(stream);
                        audioChunks = [];
                        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                        mediaRecorder.onstop = async () => {
                            const mimeType = mediaRecorder.mimeType || 'audio/webm';
                            const audioBlob = new Blob(audioChunks, { type: mimeType });
                            await enviarAudioServidor(audioBlob, 'grabacion_directa.webm');
                        };
                        mediaRecorder.start();
                        isRecording = true;
                        recordBtn.className = "w-20 h-20 bg-slate-700 rounded-full flex items-center justify-center shadow-lg transition animate-pulse border-4 border-red-500 cursor-pointer";
                        recordStatus.textContent = "🔴 Escuchando... Toca para terminar.";
                    } catch (err) {
                        alert("No se pudo acceder al micrófono. Revisa los permisos del navegador.");
                    }
                } else {
                    mediaRecorder.stop();
                    isRecording = false;
                    recordBtn.className = "w-20 h-20 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer";
                    recordStatus.textContent = "Toca el micrófono para describir la avería o instalación";
                }
            });

            uploadBtn.addEventListener('click', async () => {
                const fileInput = document.getElementById('audioFile');
                if(fileInput.files.length === 0) {
                    alert("Selecciona un archivo de audio primero.");
                    return;
                }
                await enviarAudioServidor(fileInput.files[0], fileInput.files[0].name);
            });

            async function enviarAudioServidor(blobOrFile, filename) {
                const formData = new FormData();
                formData.append('file', blobOrFile, filename);

                document.getElementById('loading').classList.remove('hidden');
                document.getElementById('resultadoContainer').classList.add('hidden');

                try {
                    const response = await fetch('/api/analizar', { method: 'POST', body: formData });
                    const data = await response.json();
                    if (response.ok) {
                        mostrarPantallaEdicion(data.presupuesto);
                    } else {
                        alert("Error al analizar el audio: " + (data.detail || "Error desconocido"));
                    }
                } catch(err) {
                    alert("Error de conexión con el servidor.");
                } finally {
                    document.getElementById('loading').classList.add('hidden');
                }
            }

            function mostrarPantallaEdicion(p) {
                const container = document.getElementById('resultadoContainer');
                container.innerHTML = `
                    <div class="bg-slate-800 rounded-2xl shadow-xl p-5 border border-slate-700 flex flex-col gap-4 text-xs text-left">
                        <h2 class="text-base font-bold text-blue-400 border-b border-slate-700 pb-2">📋 Revisión y Ajustes de Última Hora</h2>
                        
                        <div class="bg-slate-900/80 p-3 rounded-lg border border-slate-700">
                            <strong class="text-blue-300 block mb-1">🎤 Transcripción interpretada (jerga corregida):</strong>
                            <p class="text-slate-300 italic">"${p.transcripcion || 'Audio procesado'}"</p>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="text-slate-400 block mb-1">Cliente:</label>
                                <input type="text" id="editCliente" value="${p.cliente || 'Cliente'}" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white">
                            </div>
                            <div>
                                <label class="text-slate-400 block mb-1">Urgencia:</label>
                                <input type="text" id="editUrgencia" value="${p.urgencia || 'Normal'}" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white">
                            </div>
                        </div>

                        <div>
                            <label class="text-slate-400 block mb-1">Memoria técnica de la actuación:</label>
                            <textarea id="editResumen" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white" rows="2">${p.resumen_actuacion || ''}</textarea>
                        </div>

                        <!-- 1. TAREAS Y MANO DE OBRA -->
                        <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-700">
                            <div class="flex justify-between items-center mb-2">
                                <span class="font-bold text-blue-300">🛠️ Tareas y Mano de Obra (€)</span>
                                <button onclick="agregarTarea()" class="bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 px-2 py-1 rounded text-[11px]">+ Añadir tarea</button>
                            </div>
                            <div id="tareasContainer" class="flex flex-col gap-2">
                                ${(p.tareas_mano_obra || []).map(t => `
                                    <div class="flex gap-2 items-center tarea-row">
                                        <input type="text" value="${t.concepto}" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white tarea-concepto" placeholder="Descripción de tarea">
                                        <input type="number" step="0.01" value="${t.precio}" class="w-24 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-green-300 font-semibold tarea-precio" onchange="recalcularTotal()">
                                        <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <!-- 2. MATERIALES NECESARIOS -->
                        <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-700">
                            <div class="flex justify-between items-center mb-2">
                                <span class="font-bold text-amber-300">📦 Materiales (Cant. | Material | Precio U. €)</span>
                                <button onclick="agregarMaterial()" class="bg-amber-600/30 hover:bg-amber-600/50 text-amber-300 px-2 py-1 rounded text-[11px]">+ Añadir material</button>
                            </div>
                            <div id="materialesContainer" class="flex flex-col gap-2">
                                ${(p.materiales || []).map(m => `
                                    <div class="flex gap-1.5 items-center material-row">
                                        <input type="number" step="0.5" value="${m.cantidad}" class="w-14 bg-slate-800 border border-slate-700 rounded p-1.5 text-center text-white mat-cant" onchange="recalcularTotal()">
                                        <input type="text" value="${m.material}" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mat-nombre" placeholder="Material">
                                        <input type="number" step="0.01" value="${m.precio_unitario}" class="w-20 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-amber-300 font-semibold mat-precio" onchange="recalcularTotal()">
                                        <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <!-- DESGLOSE ECONÓMICO E IVA -->
                        <div class="bg-slate-900 p-4 rounded-xl border border-slate-700 flex flex-col gap-2">
                            <div class="flex justify-between items-center text-slate-300">
                                <span>Subtotal (Base Imponible):</span>
                                <span id="spanSubtotal" class="font-semibold">0.00 €</span>
                            </div>
                            <div class="flex justify-between items-center text-slate-300">
                                <div class="flex items-center gap-2">
                                    <span>IVA aplicable:</span>
                                    <select id="selectIva" onchange="recalcularTotal()" class="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-white">
                                        <option value="21" selected>21% (Estándar)</option>
                                        <option value="10">10% (Reforma vivienda)</option>
                                        <option value="0">0% (Sin IVA)</option>
                                    </select>
                                </div>
                                <span id="spanIva" class="font-semibold text-blue-300">0.00 €</span>
                            </div>
                            <div class="flex justify-between items-center border-t border-slate-700 pt-2 mt-1">
                                <span class="font-bold text-white text-sm">TOTAL PRESUPUESTO (IVA incl.):</span>
                                <span id="spanTotal" class="font-extrabold text-yellow-400 text-lg">0.00 €</span>
                            </div>
                        </div>

                        <!-- BOTONES DE ACCIÓN: PDF Y WHATSAPP -->
                        <div class="flex flex-col gap-2.5 mt-1">
                            <button onclick="generarPDFFinal()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded-xl transition shadow-lg text-sm cursor-pointer">
                                📄 1. Confirmar y Descargar Presupuesto PDF
                            </button>
                            
                            <button onclick="enviarPorWhatsApp()" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 px-4 rounded-xl transition shadow-lg text-sm cursor-pointer flex items-center justify-center gap-2">
                                📲 2. Enviar Resumen por WhatsApp al Cliente
                            </button>
                        </div>
                    </div>
                `;
                container.classList.remove('hidden');
                recalcularTotal();
            }

            function agregarTarea() {
                const div = document.createElement('div');
                div.className = "flex gap-2 items-center tarea-row";
                div.innerHTML = `
                    <input type="text" value="Mano de obra adicional" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white tarea-concepto">
                    <input type="number" step="0.01" value="40.00" class="w-24 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-green-300 font-semibold tarea-precio" onchange="recalcularTotal()">
                    <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                `;
                document.getElementById('tareasContainer').appendChild(div);
                recalcularTotal();
            }

            function agregarMaterial() {
                const div = document.createElement('div');
                div.className = "flex gap-1.5 items-center material-row";
                div.innerHTML = `
                    <input type="number" step="0.5" value="1" class="w-14 bg-slate-800 border border-slate-700 rounded p-1.5 text-center text-white mat-cant" onchange="recalcularTotal()">
                    <input type="text" value="Pieza / Material" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mat-nombre">
                    <input type="number" step="0.01" value="12.00" class="w-20 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-amber-300 font-semibold mat-precio" onchange="recalcularTotal()">
                    <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                `;
                document.getElementById('materialesContainer').appendChild(div);
                recalcularTotal();
            }

            function recalcularTotal() {
                let subtotal = 0;
                document.querySelectorAll('.tarea-precio').forEach(inp => {
                    subtotal += parseFloat(inp.value) || 0;
                });
                document.querySelectorAll('.material-row').forEach(row => {
                    const cant = parseFloat(row.querySelector('.mat-cant').value) || 0;
                    const precio = parseFloat(row.querySelector('.mat-precio').value) || 0;
                    subtotal += (cant * precio);
                });
                
                const ivaPorcentaje = parseFloat(document.getElementById('selectIva').value) || 0;
                const importeIva = subtotal * (ivaPorcentaje / 100);
                const totalConIva = subtotal + importeIva;

                document.getElementById('spanSubtotal').textContent = subtotal.toFixed(2) + " €";
                document.getElementById('spanIva').textContent = importeIva.toFixed(2) + " €";
                document.getElementById('spanTotal').textContent = totalConIva.toFixed(2) + " €";
            }

            function enviarPorWhatsApp() {
                const cliente = document.getElementById('editCliente').value;
                const resumen = document.getElementById('editResumen').value;
                const subtotal = document.getElementById('spanSubtotal').textContent;
                const ivaPorc = document.getElementById('selectIva').value;
                const total = document.getElementById('spanTotal').textContent;

                const mensaje = `Hola *${cliente}*, te envío el resumen del presupuesto de fontanería:\n\n` +
                                `🔧 *Trabajo:* ${resumen}\n` +
                                `💶 *Base Imponible:* ${subtotal}\n` +
                                `🧾 *IVA (${ivaPorc}%):* Incluido\n` +
                                `✅ *TOTAL PRESUPUESTO:* *${total}*\n\n` +
                                `_(Te adjunto a continuación el documento PDF detallado)_`;

                const url = `https://wa.me/?text=${encodeURIComponent(mensaje)}`;
                window.open(url, '_blank');
            }

            async function generarPDFFinal() {
                let subtotal = 0;
                const tareas = [];
                document.querySelectorAll('.tarea-row').forEach(row => {
                    const pr = parseFloat(row.querySelector('.tarea-precio').value) || 0;
                    subtotal += pr;
                    tareas.push({
                        concepto: row.querySelector('.tarea-concepto').value,
                        precio: pr
                    });
                });

                const materiales = [];
                document.querySelectorAll('.material-row').forEach(row => {
                    const cant = parseFloat(row.querySelector('.mat-cant').value) || 1;
                    const precio = parseFloat(row.querySelector('.mat-precio').value) || 0;
                    const subMat = cant * precio;
                    subtotal += subMat;
                    materiales.push({
                        cantidad: cant,
                        material: row.querySelector('.mat-nombre').value,
                        precio_unitario: precio,
                        subtotal: subMat
                    });
                });

                const ivaPorcentaje = parseFloat(document.getElementById('selectIva').value) || 0;
                const importeIva = subtotal * (ivaPorcentaje / 100);
                const totalConIva = subtotal + importeIva;

                const payload = {
                    cliente: document.getElementById('editCliente').value,
                    urgencia: document.getElementById('editUrgencia').value,
                    resumen_actuacion: document.getElementById('editResumen').value,
                    tareas_mano_obra: tareas,
                    materiales: materiales,
                    subtotal: subtotal,
                    iva_porcentaje: ivaPorcentaje,
                    iva_importe: importeIva,
                    total_presupuesto: totalConIva
                };

                document.getElementById('loading').classList.remove('hidden');
                try {
                    const response = await fetch('/api/generar-pdf', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await response.json();
                    if (response.ok) {
                        window.open(data.pdf_url, '_blank');
                    } else {
                        alert("Error al generar el PDF.");
                    }
                } catch(err) {
                    alert("Error de conexión al generar PDF.");
                } finally {
                    document.getElementById('loading').classList.add('hidden');
                }
            }
        </script>
    </body>
    </html>
    """

# ==========================================
# 2. ENDPOINT IA: PROCESAMIENTO DE AUDIO (FONTANERÍA)
# ==========================================
@app.post("/api/analizar")
async def api_analizar(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    try:
        contenido = await file.read()
        if not contenido:
            raise ValueError("El archivo de audio está vacío. Intenta grabar de nuevo.")

        mime_tipo = file.content_type.split(";")[0].strip() if file.content_type else "audio/webm"
        if not mime_tipo.startswith("audio/") and not mime_tipo.startswith("video/"):
            mime_tipo = "audio/webm"

        audio_part = types.Part.from_bytes(
            data=contenido,
            mime_type=mime_tipo
        )
        
        prompt = """
        Eres un maestro fontanero e instalador autorizado en fontanería y saneamiento en España con 30 años de experiencia.
        Vas a escuchar una nota de voz grabada por un compañero fontanero en plena obra o avería. Hablará de forma coloquial y usando jerga del oficio.

        DICCIONARIO DE JERGA Y RECONOCIMIENTO FONÉTICO OBLIGATORIO (FONTANERÍA):
        Si el audio suena parecido a alguno de estos términos, interprétalo siempre dentro del contexto de fontanería:
        - "Cobre", "multicapa", "PEX", "PVC", "latiguillo" -> Tuberías, accesorios de unión y manguitos flexibles.
        - "Llave de escuadra", "grifo", "monomando", "fluxor", "bide" -> Grifería y llaves de corte.
        - "Bote sifónico", "sifón", "arqueta", "desagüe", "bajante" -> Evacuación de aguas y saneamiento.
        - "Termo", "calentador", "acumulador", "calderín" -> Producción de agua caliente sanitaria (ACS).
        - "Desatranco", "muelle", "hidrolimpiadora", "sonda" -> Desatasco y limpieza de tuberías.
        - "Llave de paso", "contador", "reductora de presión" -> Elementos de acometida general.

        INSTRUCCIONES DE SALIDA:
        1. Transcribe el audio corrigiendo errores fonéticos evidentes para que tenga sentido 100% de fontanería.
        2. Redacta un resumen técnico formal para el cliente.
        3. Desglosa TODAS las TAREAS de mano de obra mencionadas sin omitir ninguna (reparación de fuga, sustitución de termo, desatranco, soldadura, etc.).
        4. Lista TODOS los MATERIALES mencionados o necesarios implícitamente (metros de tubo, accesorios de compresión, llaves, juntas, etc.).

        Devuelve EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
        {
          "transcripcion": "Transcripción fiel con los términos de fontanería bien escritos",
          "cliente": "Nombre del cliente si se dice, o 'Cliente'",
          "urgencia": "Normal o Urgente",
          "resumen_actuacion": "Descripción técnica y formal del trabajo de fontanería para el presupuesto",
          "tareas_mano_obra": [
            {"concepto": "Localización y reparación de fuga en tubería de cobre y reposición de azulejos", "precio": 110.0}
          ],
          "materiales": [
            {"material": "Tubo de cobre de 15mm (metros)", "cantidad": 3, "precio_unitario": 6.50},
            {"material": "Accesorio codo de cobre 15mm", "cantidad": 4, "precio_unitario": 1.80}
          ]
        }
        """
        
        modelos_a_probar = [
            'gemini-3.8-flash',
            'gemini-3.8-flash',
            'gemini-3.8-pro'
        ]
        
        response = None
        errores_acumulados = []
        
        for intento, modelo_actual in enumerate(modelos_a_probar):
            try:
                response = client.models.generate_content(
                    model=modelo_actual,
                    contents=[audio_part, prompt],
                    config={'response_mime_type': 'application/json'}
                )
                break
            except Exception as err:
                err_str = str(err)
                errores_acumulados.append(f"[{modelo_actual}: {err_str}]")
                if any(cod in err_str.upper() for cod in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND"]):
                    time.sleep(2 * (intento + 1))
                    continue
                else:
                    raise err
                    
        if response is None:
            raise Exception(f"No se pudo conectar tras varios intentos. Error: {errores_acumulados[0]}")
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio[7:]
        if texto_limpio.endswith("```"):
            texto_limpio = texto_limpio[:-3]
            
        presupuesto_dict = json.loads(texto_limpio.strip())

        # --- REGISTRO DE ESTADÍSTICAS EN GOOGLE SHEETS ---
        user_agent = request.headers.get("user-agent", "Desconocido")
        pais = request.headers.get("cf-ipcountry", "ES")
        forwarded = request.headers.get("x-forwarded-for", "")
        ip_cliente = forwarded.split(",")[0].strip() if forwarded else ""

        background_tasks.add_task(
            registrar_uso_sheets,
            "Fontanería",
            presupuesto_dict.get("urgencia", "Normal"),
            user_agent,
            ip_cliente,
            pais
        )

        return {"presupuesto": presupuesto_dict}
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 3. GENERADOR DE PDF PARA FONTANERÍA
# ==========================================
@app.post("/api/generar-pdf")
async def api_generar_pdf(presupuesto: dict = Body(...)):
    ruta_pdf = "presupuesto_fontaneria.pdf"
    doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    ahora = datetime.now()
    fecha_str = ahora.strftime("%d/%m/%Y")
    num_presupuesto = f"PRE-{ahora.strftime('%Y%m%d-%H%M')}"
    
    estilo_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor("#1d4ed8"), spaceAfter=4)
    estilo_sub = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#64748b"), spaceAfter=14)
    estilo_h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=6)
    estilo_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#334155"), leading=14)
    estilo_celda = ParagraphStyle('Celda', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#1e293b"), leading=12)
    estilo_legal = ParagraphStyle('Legal', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor("#94a3b8"), spaceBefore=20)
    
    story.append(Paragraph(f"🔧 {NOMBRE_COMERCIAL_DEFAULT}", estilo_titulo))
    story.append(Paragraph(
        f"Teléfono: {TELEFONO_DEFAULT} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Nº Presupuesto:</b> {num_presupuesto} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fecha:</b> {fecha_str}", 
        estilo_sub
    ))
    
    story.append(Paragraph("<b>1. Datos del Cliente y Memoria de Actuación</b>", estilo_h2))
    story.append(Paragraph(f"<b>Cliente:</b> {presupuesto.get('cliente', 'Cliente')} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Tipo de servicio:</b> {presupuesto.get('urgencia', 'Normal')}", estilo_texto))
    story.append(Paragraph(f"<b>Actuación:</b> {presupuesto.get('resumen_actuacion', '')}", estilo_texto))
    story.append(Spacer(1, 8))
    
    # Tabla de Tareas
    story.append(Paragraph("<b>2. Desglose de Tareas y Mano de Obra</b>", estilo_h2))
    data_tareas = [["Concepto / Tarea de Fontanería", "Importe"]]
    for t in presupuesto.get('tareas_mano_obra', []):
        concepto_ajustado = Paragraph(str(t.get('concepto', '')), estilo_celda)
        data_tareas.append([concepto_ajustado, f"{float(t.get('precio', 0)):.2f} €"])
    
    tabla_t = Table(data_tareas, colWidths=[410, 90])
    tabla_t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e3a8a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_t)
    story.append(Spacer(1, 8))

    # Tabla de Materiales
    story.append(Paragraph("<b>3. Materiales y Suministros</b>", estilo_h2))
    data_mat = [["Material / Pieza", "Cant.", "Precio U.", "Subtotal"]]
    for m in presupuesto.get('materiales', []):
        cant = float(m.get('cantidad', 1))
        pu = float(m.get('precio_unitario', 0))
        sub = cant * pu
        mat_ajustado = Paragraph(str(m.get('material', '')), estilo_celda)
        data_mat.append([mat_ajustado, str(int(cant) if cant.is_integer() else cant), f"{pu:.2f} €", f"{sub:.2f} €"])
    
    tabla_m = Table(data_mat, colWidths=[280, 50, 80, 90])
    tabla_m.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_m)
    story.append(Spacer(1, 14))

    # Tabla Totales
    subtotal = float(presupuesto.get('subtotal', 0.0))
    iva_porc = int(float(presupuesto.get('iva_porcentaje', 21)))
    iva_imp = float(presupuesto.get('iva_importe', 0.0))
    total = float(presupuesto.get('total_presupuesto', 0.0))

    data_totales = [
        ["Base Imponible (Mano de Obra + Materiales):", f"{subtotal:.2f} €"],
        [f"IVA ({iva_porc}%):", f"{iva_imp:.2f} €"],
        ["TOTAL PRESUPUESTO (IVA Incluido):", f"{total:.2f} €"]
    ]
    tabla_totales = Table(data_totales, colWidths=[380, 120])
    tabla_totales.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,2), (-1,2), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,1), 10),
        ('FONTSIZE', (0,2), (-1,2), 12),
        ('TEXTCOLOR', (0,2), (-1,2), colors.HexColor("#15803d")),
        ('LINEABOVE', (0,2), (-1,2), 1, colors.HexColor("#cbd5e1")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tabla_totales)
    
    # Pie legal
    story.append(Paragraph(
        "Condiciones: Este presupuesto tiene una validez de 15 días naturales desde su fecha de emisión. "
        "Las reparaciones en tuberías ocultas o elementos bajo suelo quedan sujetas a posibles variaciones si se descubren vicios ocultos.",
        estilo_legal
    ))

    doc.build(story)
    return {"estado": "ok", "pdf_url": "/descargar-pdf"}

@app.get("/descargar-pdf")
def descargar_pdf():
    return FileResponse("presupuesto_fontaneria.pdf", media_type="application/pdf", filename="presupuesto_fontaneria.pdf")