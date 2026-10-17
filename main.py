import os
import sqlite3
import json
import traceback
import time  # <-- Asegúrate de tener este import al principio del archivo
from dotenv import load_dotenv
from google import genai
from fastapi import FastAPI, UploadFile, File, Body, HTTPException
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

NOMBRE_COMERCIAL_DEFAULT = "Fontanería y Servicios Manolo"
TELEFONO_DEFAULT = "600987654"

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
            <p class="text-slate-400 text-xs mb-6">Habla con naturalidad usando tu jerga habitual. La IA transcribirá y desglosará tareas, materiales, herramientas e IVA.</p>
            
            <!-- GRABACIÓN EN DIRECTO -->
            <div class="flex flex-col items-center gap-3 mb-5">
                <button id="recordBtn" class="w-20 h-20 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-9 w-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </button>
                <div id="recordStatus" class="text-xs font-medium text-slate-300">Toca el micrófono para describir la obra</div>
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
                <p class="text-xs text-blue-300">Transcribiendo jerga técnica y calculando presupuesto...</p>
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
                        // Configuración de audio optimizada para voz clara
                        const stream = await navigator.mediaDevices.getUserMedia({ 
                            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } 
                        });
                        mediaRecorder = new MediaRecorder(stream);
                        audioChunks = [];
                        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                        mediaRecorder.onstop = async () => {
                            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
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
                    recordStatus.textContent = "Toca el micrófono para describir la obra";
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
                        
                        <!-- Transcripción editable por si quiere matizar algo -->
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

                        <!-- 3. HERRAMIENTAS RECOMENDADAS -->
                        <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-700">
                            <label class="font-bold text-purple-300 block mb-1">🧰 Herramientas para llevar a la obra (uso interno):</label>
                            <input type="text" id="editHerramientas" value="${(p.herramientas || []).join(', ')}" class="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-200" placeholder="Separadas por comas...">
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

                        <button onclick="generarPDFFinal()" class="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 px-4 rounded-xl transition shadow-lg text-sm cursor-pointer">
                            📄 Confirmar y Descargar Presupuesto PDF
                        </button>
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

                const herramientasStr = document.getElementById('editHerramientas').value;
                const herramientas = herramientasStr.split(',').map(s => s.trim()).filter(Boolean);

                const payload = {
                    cliente: document.getElementById('editCliente').value,
                    urgencia: document.getElementById('editUrgencia').value,
                    resumen_actuacion: document.getElementById('editResumen').value,
                    tareas_mano_obra: tareas,
                    materiales: materiales,
                    herramientas: herramientas,
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
# 2. ENDPOINT IA: EXPERTO EN JERGA DE FONTANERÍA
# ==========================================
@app.post("/api/analizar")
async def api_analizar(file: UploadFile = File(...)):
    contenido = await file.read()
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contenido)
    
    try:
        audio_file = client.files.upload(file=temp_path)
        
        prompt = """
        Eres un maestro fontanero e instalador autorizado en España con 30 años de experiencia.
        Vas a escuchar una nota de voz grabada por un compañero fontanero en plena obra. El profesional hablará de forma coloquial, rápida y usando jerga del oficio.

        DICCIONARIO DE JERGA Y RECONOCIMIENTO FONÉTICO OBLIGATORIO:
        Si el audio suena parecido a alguno de estos términos, interprétalo siempre dentro del contexto de fontanería:
        - "Latiguillo", "flexible" -> Latiguillo flexible trenzado de acero inox (1/2", 3/8").
        - "Llave de escuadra", "llave de corte", "llave de paso", "detentor" -> Válvula de escuadra / llave de corte cromada.
        - "Machón", "manguito", "racor", "tuerca loca", "entronque", "reducción", "codo", "te" -> Piecerío y racorería de latón o cobre.
        - "Multicapa", "PEX", "polietileno", "cobre de 15 / 18 / 22", "PVC de 40 / 50 / 110" -> Tuberías de conducción o evacuación.
        - "Bote sifónico", "sifón botella", "sifón curvo", "válvula de desagüe" -> Elementos de evacuación y desagüe.
        - "Pasar la guía", "meter el muelle", "karcher", "camión cuba", "chupón" -> Desatasco mecánico o limpieza de tuberías con máquina de tambor / agua a presión.
        - "Picar la pared", "hacer una roza", "descubrir el tubo", "tapar con perlita / yeso / mortero" -> Apertura de cala/roza en albañilería para localizar avería y posterior tapado.
        - "Descargador", "mecanismo de cisterna", "flotador", "boya", "tanque bajo" -> Reparación de cisterna de inodoro.
        - "Termo", "calentador estanco", "grupo de seguridad", "vaso de expansión", "ánodo" -> Agua Caliente Sanitaria (ACS).
        - "Teflón", "cáñamo", "estopa", "pasta verde", "masilla", "soldar con estaño-plata" -> Materiales de sellado y unión.
        - Medidas habladas: "de media" (1/2"), "de tres octavos" (3/8"), "de tres cuartos" (3/4"), "de una pulgada" (1").

        INSTRUCCIONES DE SALIDA:
        1. Transcribe el audio corrigiendo errores fonéticos evidentes para que tenga sentido 100% de fontanería.
        2. Redacta un resumen técnico formal para el cliente (transformando la jerga coloquial en lenguaje profesional).
        3. Desglosa todas las TAREAS de mano de obra (incluyendo si menciona picar pared, cortar suministro, desmontar, instalar o probar presión).
        4. Lista todos los MATERIALES mencionados o necesarios implícitamente (ej. si dice "cambiar grifo y llaves", incluye el grifo, las llaves de escuadra y teflón/juntas).
        5. Lista las HERRAMIENTAS necesarias para el operario (ej. prensadora multicapa, cortatubos, soplete, llave Stillson/grifa, llave inglesa, taladro percutor/cincel si hay que picar, guía desatascadora, etc.).

        Devuelve EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
        {
          "transcripcion": "Transcripción fiel con los términos de fontanería bien escritos",
          "cliente": "Nombre del cliente si se dice, o 'Cliente'",
          "urgencia": "Normal o Urgente",
          "resumen_actuacion": "Descripción técnica y formal del trabajo para presentar en el presupuesto",
          "tareas_mano_obra": [
            {"concepto": "Localización de fuga, apertura de roza y sustitución de tramo en tubo multicapa", "precio": 85.0}
          ],
          "materiales": [
            {"material": "Tubería multicapa 16mm (metros)", "cantidad": 2, "precio_unitario": 4.50},
            {"material": "Codo prensado multicapa 16mm", "cantidad": 2, "precio_unitario": 6.00}
          ],
          "herramientas": [
            "Prensadora de multicapa (mordaza U16)",
            "Cortatubos y abocardador/calibrador",
            "Martillo percutor con cincel para roza",
            "Llave inglesa y llave grifa"
          ]
        }
        """
        
        # Sistema anti-caídas (Reintentos automáticos ante error 503 de alta demanda)
        modelos_a_probar = [
            'gemini-3.8-flash',
            'gemini-3.8-flash',  # Segundo intento tras breve pausa
            'gemini-3.8-pro'     # Respaldo si el modelo Flash sigue saturado
        ]
        
        response = None
        ultimo_error = None
        
        for intento, modelo_actual in enumerate(modelos_a_probar):
            try:
                response = client.models.generate_content(
                    model=modelo_actual,
                    contents=[audio_file, prompt],
                    config={'response_mime_type': 'application/json'}
                )
                break  # Si funciona a la primera, salimos del bucle inmediatamente
            except Exception as err:
                ultimo_error = err
                if "503" in str(err) or "UNAVAILABLE" in str(err):
                    time.sleep(2 * (intento + 1))  # Espera 2s en el 1er fallo, 4s en el 2º
                    continue
                else:
                    raise err  # Si es otro tipo de error, lo lanza normal
                    
        if response is None:
            raise ultimo_error
        
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio[7:]
        if texto_limpio.endswith("```"):
            texto_limpio = texto_limpio[:-3]
            
        return {"presupuesto": json.loads(texto_limpio.strip())}
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ==========================================
# 3. GENERADOR DE PDF CON DESGLOSE DE IVA
# ==========================================
@app.post("/api/generar-pdf")
async def api_generar_pdf(presupuesto: dict = Body(...)):
    ruta_pdf = "presupuesto_fontaneria.pdf"
    doc = SimpleDocTemplate(ruta_pdf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor("#1d4ed8"), spaceAfter=4)
    estilo_sub = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#64748b"), spaceAfter=14)
    estilo_h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=6)
    estilo_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#334155"), leading=14)
    
    story.append(Paragraph(f"🔧 {NOMBRE_COMERCIAL_DEFAULT}", estilo_titulo))
    story.append(Paragraph(f"Teléfono: {TELEFONO_DEFAULT} | Presupuesto Oficial y Hoja de Trabajo", estilo_sub))
    
    story.append(Paragraph("<b>1. Datos del Cliente y Memoria de Actuación</b>", estilo_h2))
    story.append(Paragraph(f"<b>Cliente:</b> {presupuesto.get('cliente', 'Cliente')} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Tipo de servicio:</b> {presupuesto.get('urgencia', 'Normal')}", estilo_texto))
    story.append(Paragraph(f"<b>Actuación:</b> {presupuesto.get('resumen_actuacion', '')}", estilo_texto))
    story.append(Spacer(1, 8))
    
    # Tabla de Mano de Obra
    story.append(Paragraph("<b>2. Desglose de Tareas y Mano de Obra</b>", estilo_h2))
    data_tareas = [["Concepto / Tarea de Fontanería", "Importe"]]
    for t in presupuesto.get('tareas_mano_obra', []):
        data_tareas.append([t.get('concepto', ''), f"{float(t.get('precio', 0)):.2f} €"])
    
    tabla_t = Table(data_tareas, colWidths=[380, 90])
    tabla_t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e3a8a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_t)
    story.append(Spacer(1, 8))

    # Tabla de Materiales
    story.append(Paragraph("<b>3. Materiales y Piecerío</b>", estilo_h2))
    data_mat = [["Material / Pieza", "Cant.", "Precio U.", "Subtotal"]]
    for m in presupuesto.get('materiales', []):
        cant = float(m.get('cantidad', 1))
        pu = float(m.get('precio_unitario', 0))
        sub = cant * pu
        data_mat.append([m.get('material', ''), str(int(cant) if cant.is_integer() else cant), f"{pu:.2f} €", f"{sub:.2f} €"])
    
    tabla_m = Table(data_mat, colWidths=[250, 50, 80, 90])
    tabla_m.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_m)
    story.append(Spacer(1, 14))

    # Tabla Resumen Económico con IVA
    subtotal = float(presupuesto.get('subtotal', 0.0))
    iva_porc = int(float(presupuesto.get('iva_porcentaje', 21)))
    iva_imp = float(presupuesto.get('iva_importe', 0.0))
    total = float(presupuesto.get('total_presupuesto', 0.0))

    data_totales = [
        ["Base Imponible (Mano de Obra + Materiales):", f"{subtotal:.2f} €"],
        [f"IVA ({iva_porc}%):", f"{iva_imp:.2f} €"],
        ["TOTAL PRESUPUESTO (IVA Incluido):", f"{total:.2f} €"]
    ]
    tabla_totales = Table(data_totales, colWidths=[350, 120])
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
    story.append(Spacer(1, 14))

    # Herramientas para el profesional
    herramientas = presupuesto.get('herramientas', [])
    if herramientas:
        story.append(Paragraph("<b>Anexo Interno: Herramientas recomendadas para la furgoneta</b>", estilo_h2))
        story.append(Paragraph(", ".join(herramientas), estilo_texto))
    
    doc.build(story)
    return {"estado": "ok", "pdf_url": "/descargar-pdf"}

@app.get("/descargar-pdf")
def descargar_pdf():
    return FileResponse("presupuesto_fontaneria.pdf", media_type="application/pdf", filename="presupuesto_fontaneria.pdf")