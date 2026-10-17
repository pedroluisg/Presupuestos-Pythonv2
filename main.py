import os
import sqlite3
import json
import traceback
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
            <p class="text-slate-400 text-xs mb-6">Describe la obra en voz alta o sube un audio para extraer tareas, materiales, herramientas y presupuesto.</p>
            
            <!-- GRABACIÓN EN DIRECTO -->
            <div class="flex flex-col items-center gap-3 mb-5">
                <button id="recordBtn" class="w-20 h-20 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-9 w-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </button>
                <div id="recordStatus" class="text-xs font-medium text-slate-300">Toca el micrófono para grabar en vivo</div>
            </div>

            <!-- SUBIDA DE ARCHIVO -->
            <div class="border-t border-slate-700 pt-4">
                <p class="text-xs text-slate-400 mb-2">O adjunta una grabación guardada:</p>
                <div class="flex gap-2">
                    <input type="file" id="audioFile" accept="audio/*" class="w-full text-xs text-slate-400 file:mr-2 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-700 file:text-blue-300 hover:file:bg-slate-600 cursor-pointer">
                    <button id="uploadBtn" class="bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-4 rounded-lg transition text-xs whitespace-nowrap shadow">
                        📂 Analizar Audio
                    </button>
                </div>
            </div>
            
            <div id="loading" class="hidden text-center py-6">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mx-auto mb-2"></div>
                <p class="text-xs text-blue-300">Analizando obra, materiales y herramientas con IA...</p>
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
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
                        recordStatus.textContent = "🔴 Grabando... Toca de nuevo para terminar.";
                    } catch (err) {
                        alert("No se pudo acceder al micrófono. Revisa los permisos.");
                    }
                } else {
                    mediaRecorder.stop();
                    isRecording = false;
                    recordBtn.className = "w-20 h-20 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer";
                    recordStatus.textContent = "Toca el micrófono para grabar en vivo";
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
                        <h2 class="text-base font-bold text-blue-400 border-b border-slate-700 pb-2">📋 Revisión y Cambios de Última Hora</h2>
                        
                        <!-- Transcripción detectada -->
                        <div class="bg-slate-900/80 p-3 rounded-lg border border-slate-700 text-slate-300 italic">
                            <strong class="text-slate-400 not-italic block mb-1">🎤 Transcripción del audio:</strong>
                            "${p.transcripcion || 'Audio procesado'}"
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
                            <label class="text-slate-400 block mb-1">Resumen de la obra:</label>
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
                                <span class="font-bold text-amber-300">📦 Materiales (Cant. | Material | Precio €)</span>
                                <button onclick="agregarMaterial()" class="bg-amber-600/30 hover:bg-amber-600/50 text-amber-300 px-2 py-1 rounded text-[11px]">+ Añadir material</button>
                            </div>
                            <div id="materialesContainer" class="flex flex-col gap-2">
                                ${(p.materiales || []).map(m => `
                                    <div class="flex gap-1.5 items-center material-row">
                                        <input type="number" value="${m.cantidad}" class="w-12 bg-slate-800 border border-slate-700 rounded p-1.5 text-center text-white mat-cant" onchange="recalcularTotal()">
                                        <input type="text" value="${m.material}" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mat-nombre" placeholder="Material">
                                        <input type="number" step="0.01" value="${m.precio_unitario}" class="w-20 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-amber-300 font-semibold mat-precio" onchange="recalcularTotal()">
                                        <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <!-- 3. HERRAMIENTAS RECOMENDADAS -->
                        <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-700">
                            <label class="font-bold text-purple-300 block mb-1">🧰 Herramientas a llevar a la obra (Checklist):</label>
                            <input type="text" id="editHerramientas" value="${(p.herramientas || []).join(', ')}" class="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-200" placeholder="Separadas por comas...">
                        </div>

                        <!-- TOTAL PRESUPUESTO -->
                        <div class="flex justify-between items-center bg-slate-900 p-3 rounded-xl border border-green-500/30">
                            <span class="font-bold text-slate-300 text-sm">TOTAL PRESUPUESTO (€):</span>
                            <input type="number" step="0.01" id="editTotal" value="0" class="w-28 bg-slate-800 border border-slate-600 rounded-lg p-2 text-right text-yellow-400 font-extrabold text-base">
                        </div>

                        <button onclick="generarPDFFinal()" class="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 px-4 rounded-xl transition shadow-lg text-sm cursor-pointer">
                            📄 Confirmar Cambios y Descargar PDF
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
                    <input type="text" value="Nueva tarea" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white tarea-concepto">
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
                    <input type="number" value="1" class="w-12 bg-slate-800 border border-slate-700 rounded p-1.5 text-center text-white mat-cant" onchange="recalcularTotal()">
                    <input type="text" value="Nuevo material" class="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mat-nombre">
                    <input type="number" step="0.01" value="10.00" class="w-20 bg-slate-800 border border-slate-700 rounded p-1.5 text-right text-amber-300 font-semibold mat-precio" onchange="recalcularTotal()">
                    <button onclick="this.parentElement.remove(); recalcularTotal();" class="text-red-400 hover:text-red-300 px-1">✕</button>
                `;
                document.getElementById('materialesContainer').appendChild(div);
                recalcularTotal();
            }

            function recalcularTotal() {
                let suma = 0;
                document.querySelectorAll('.tarea-precio').forEach(inp => {
                    suma += parseFloat(inp.value) || 0;
                });
                document.querySelectorAll('.material-row').forEach(row => {
                    const cant = parseFloat(row.querySelector('.mat-cant').value) || 0;
                    const precio = parseFloat(row.querySelector('.mat-precio').value) || 0;
                    suma += (cant * precio);
                });
                document.getElementById('editTotal').value = suma.toFixed(2);
            }

            async function generarPDFFinal() {
                const tareas = [];
                document.querySelectorAll('.tarea-row').forEach(row => {
                    tareas.push({
                        concepto: row.querySelector('.tarea-concepto').value,
                        precio: parseFloat(row.querySelector('.tarea-precio').value) || 0
                    });
                });

                const materiales = [];
                document.querySelectorAll('.material-row').forEach(row => {
                    const cant = parseFloat(row.querySelector('.mat-cant').value) || 1;
                    const precio = parseFloat(row.querySelector('.mat-precio').value) || 0;
                    materiales.push({
                        cantidad: cant,
                        material: row.querySelector('.mat-nombre').value,
                        precio_unitario: precio,
                        subtotal: cant * precio
                    });
                });

                const herramientasStr = document.getElementById('editHerramientas').value;
                const herramientas = herramientasStr.split(',').map(s => s.trim()).filter(Boolean);

                const payload = {
                    cliente: document.getElementById('editCliente').value,
                    urgencia: document.getElementById('editUrgencia').value,
                    resumen_actuacion: document.getElementById('editResumen').value,
                    tareas_mano_obra: tareas,
                    materiales: materiales,
                    herramientas: herramientas,
                    total_presupuesto: parseFloat(document.getElementById('editTotal').value) || 0
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
# 2. ENDPOINT IA: TRANSCRIPCIÓN Y RELACIÓN DE FONTANERÍA
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
        Eres un maestro fontanero experto realizando presupuestos y planificando obras en España.
        Escucha el audio y realiza lo siguiente:
        1. Transcribe lo que dice el fontanero o cliente.
        2. Deduce todas las TAREAS de mano de obra necesarias (incluso pasos lógicos implícitos como corte de agua, desmontaje, sellado o pruebas de estanqueidad) con su precio estimado de mano de obra.
        3. Deduce la lista de MATERIALES de fontanería necesarios (tuberías de cobre/PEX/PVC, latiguillos, grifería, juntas, teflón, sifón, llaves de escuadra, etc.) con cantidades y precio unitario aproximado.
        4. Deduce las HERRAMIENTAS específicas que el fontanero debe llevar en la caja de herramientas para esta intervención (ej. llave grifa, llave inglesa, cortatubos, soplete, máquina de presurización, desatascador de tambor, teflón, etc.).

        Devuelve EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
        {
          "transcripcion": "Texto literal transcrito del audio",
          "cliente": "Nombre del cliente si se menciona, o Cliente",
          "urgencia": "Normal o Urgente",
          "resumen_actuacion": "Resumen técnico profesional del trabajo a realizar",
          "tareas_mano_obra": [
            {"concepto": "Desmontaje de sanitario o tubería afectada y preparación", "precio": 45.0},
            {"concepto": "Instalación y sellado de nueva pieza", "precio": 60.0}
          ],
          "materiales": [
            {"material": "Latiguillo flexible reforzado 1/2", "cantidad": 2, "precio_unitario": 8.50},
            {"material": "Llave de escuadra antirretorno", "cantidad": 2, "precio_unitario": 12.00}
          ],
          "herramientas": [
            "Llave inglesa ajustable",
            "Llave grifa / Stillson",
            "Cortatubos",
            "Cinta de teflón / cáñamo"
          ]
        }
        """
        
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[audio_file, prompt],
            config={'response_mime_type': 'application/json'}
        )
        
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
# 3. GENERADOR DE PDF COMPLETO
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
    story.append(Paragraph(f"Teléfono: {TELEFONO_DEFAULT} | Presupuesto y Hoja de Trabajo", estilo_sub))
    
    story.append(Paragraph("<b>1. Datos del Cliente y Obra</b>", estilo_h2))
    story.append(Paragraph(f"<b>Cliente:</b> {presupuesto.get('cliente', 'Cliente')} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Urgencia:</b> {presupuesto.get('urgencia', 'Normal')}", estilo_texto))
    story.append(Paragraph(f"<b>Descripción:</b> {presupuesto.get('resumen_actuacion', '')}", estilo_texto))
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
    story.append(Paragraph("<b>3. Materiales Necesarios</b>", estilo_h2))
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
    story.append(Spacer(1, 10))

    # Herramientas para el profesional
    herramientas = presupuesto.get('herramientas', [])
    if herramientas:
        story.append(Paragraph("<b>4. Herramientas Recomendadas para la Intervención</b>", estilo_h2))
        story.append(Paragraph(", ".join(herramientas), estilo_texto))
        story.append(Spacer(1, 12))
    
    total = float(presupuesto.get('total_presupuesto', 0.0))
    story.append(Paragraph(f"<b>TOTAL PRESUPUESTO (Mano de Obra + Materiales): {total:.2f} €</b>", 
                           ParagraphStyle('Total', parent=estilo_texto, fontSize=13, textColor=colors.HexColor("#15803d"))))
    
    doc.build(story)
    return {"estado": "ok", "pdf_url": "/descargar-pdf"}

@app.get("/descargar-pdf")
def descargar_pdf():
    return FileResponse("presupuesto_fontaneria.pdf", media_type="application/pdf", filename="presupuesto_fontaneria.pdf")