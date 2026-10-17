import os
import sqlite3
import json
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

def inicializar_base_de_datos():
    conexion = sqlite3.connect("fontanero.db")
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario_furgoneta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_material TEXT UNIQUE,
            stock_actual INTEGER,
            stock_minimo INTEGER
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM inventario_furgoneta")
    if cursor.fetchone() == 0:
        cursor.executemany("""
            INSERT INTO inventario_furgoneta (nombre_material, stock_actual, stock_minimo)
            VALUES (?, ?, ?)
        """, [
            ("Latiguillos (unidad)", 10, 3),
            ("Tubo cobre 15mm (metros)", 30, 10),
            ("Tes y codos cobre", 25, 5),
            ("Sifón fregadero", 4, 2),
            ("Termo eléctrico 50L", 2, 1),
            ("Bote de teflón / silicona", 6, 2)
        ])
        conexion.commit()
    conexion.close()

@app.on_event("startup")
def startup_event():
    inicializar_base_de_datos()

# ==========================================
# INTERFAZ WEB MÓVIL (FRONTEND)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Asistente Fontanería Flash</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 min-h-screen p-4 flex flex-col items-center">
        <div class="w-full max-w-md bg-slate-800 rounded-2xl shadow-2xl p-6 border border-slate-700 mt-4 text-center">
            <h1 class="text-2xl font-extrabold text-blue-400 mb-1 flex items-center justify-center gap-2">🔧 Fontanería Flash</h1>
            <p class="text-slate-400 text-sm mb-6">Graba en directo o sube una nota de voz con la avería.</p>
            
            <!-- OPCIÓN 1: GRABACIÓN EN DIRECTO -->
            <div class="flex flex-col items-center gap-3 mb-6">
                <button id="recordBtn" class="w-24 h-24 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10 text-white animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </button>
                <div id="recordStatus" class="text-xs font-medium text-slate-300">Toca para grabar voz en directo</div>
            </div>

            <div class="border-t border-slate-700 my-4 pt-4">
                <p class="text-xs text-slate-400 mb-2">O bien, selecciona un archivo de audio guardado:</p>
                <input type="file" id="audioFile" accept="audio/*" class="w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-500 cursor-pointer">
                <button id="uploadBtn" class="w-full mt-3 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 px-4 rounded-xl transition text-xs shadow">
                    📂 Analizar Fichero de Audio
                </button>
            </div>
            
            <div id="loading" class="hidden text-center py-6">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mx-auto mb-2"></div>
                <p class="text-xs text-blue-300">Interpretando avería con IA...</p>
            </div>
        </div>

        <!-- CONTENEDOR DE EDICIÓN Y REVISIÓN PREVIA -->
        <div id="resultadoContainer" class="w-full max-w-md mt-4 hidden"></div>

        <script>
            let mediaRecorder, audioChunks = [], isRecording = false;

            const recordBtn = document.getElementById('recordBtn');
            const recordStatus = document.getElementById('recordStatus');
            const uploadBtn = document.getElementById('uploadBtn');

            // Grabación en directo
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
                        recordBtn.className = "w-24 h-24 bg-slate-700 rounded-full flex items-center justify-center shadow-lg transition animate-pulse border-4 border-slate-500 cursor-pointer";
                        recordStatus.textContent = "🔴 Grabando... Toca otra vez para parar.";
                    } catch (err) {
                        alert("Sin acceso al micrófono.");
                    }
                } else {
                    mediaRecorder.stop();
                    isRecording = false;
                    recordBtn.className = "w-24 h-24 bg-red-600 hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition transform active:scale-95 border-4 border-red-400/40 cursor-pointer";
                    recordStatus.textContent = "Toca para grabar voz en directo";
                }
            });

            // Subir archivo existente
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
                        alert("Error al analizar el audio.");
                    }
                } catch(err) {
                    alert("Error de conexión con el servidor.");
                } finally {
                    document.getElementById('loading').classList.add('hidden');
                }
            }

            function mostrarPi(p) { return p; }

            function mostrarPantallaEdicion(p) {
                let html = `
                    <div class="bg-slate-800 rounded-2xl shadow-xl p-5 border border-slate-700 flex flex-col gap-3 text-sm text-left">
                        <h2 class="text-lg font-bold text-blue-400 border-b border-slate-700 pb-2">🛠️ Editar Presupuesto antes de PDF</h2>
                        
                        <div>
                            <label class="text-xs text-slate-400">Cliente:</label>
                            <input type="text" id="editCliente" value="${p.cliente}" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white text-xs">
                        </div>
                        
                        <div>
                            <label class="text-xs text-slate-400">Descripción Avería / Actuación:</label>
                            <textarea id="editResumen" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white text-xs" rows="2">${p.resumen_actuacion}</textarea>
                        </div>

                        <div class="bg-slate-900/50 p-3 rounded-xl border border-slate-700">
                            <div class="font-semibold text-blue-300 mb-2 text-xs">Servicios y Mano de Obra (Modificables):</div>
                            <div id="lineasContainer">
                                ${p.desglose_lineas.map((l, index) => `
                                    <div class="flex gap-2 mb-2 items-center linea-item">
                                        <input type="text" value="${l.concepto}" class="w-2/3 bg-slate-800 border border-slate-700 rounded p-1.5 text-xs text-white concepto-input">
                                        <input type="number" value="${l.subtotal_mano_obra}" class="w-1/3 bg-slate-800 border border-slate-700 rounded p-1.5 text-xs text-white precio-input" onchange="recalcularTotal()">
                                    </div>
                                `).join('')}
                            </div>
                        </div>

                        <div>
                            <label class="text-xs text-slate-400">Total Mano de Obra (€):</label>
                            <input type="number" id="editTotal" value="${p.total_estimado_mano_obra}" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-yellow-400 font-bold text-sm">
                        </div>

                        <button onclick="generarPDFFinal(${JSON.stringify(p).replace(/"/g, '&quot;')})" class="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 px-4 rounded-xl transition shadow-lg text-sm mt-2 cursor-pointer">
                            ✨ Confirmar y Generar PDF Oficial
                        </button>
                    </div>
                `;
                document.getElementById('resultadoContainer').innerHTML = html;
                document.getElementById('resultadoContainer').classList.remove('hidden');
            }

            function recalcularTotal() {
                const precios = document.querySelectorAll('.precio-input');
                let suma = 0;
                precios.forEach(input => { suma += parseFloat(input.value) || 0; });
                document.getElementById('editTotal').value = suma.toFixed(2);
            }

            async function generarPDFFinal(originalData) {
                // Recogemos los cambios de última hora hechos por el profesional
                const clienteModificado = document.getElementById('editCliente').value;
                const resumenModificado = document.getElementById('editResumen').value;
                const totalModificado = parseFloat(document.getElementById('editTotal').value);
                
                const conceptosInputs = document.querySelectorAll('.concepto-input');
                const preciosInputs = document.querySelectorAll('.precio-input');
                
                let nuevasLineas = [];
                conceptosInputs.forEach((inp, idx) => {
                    nuevasLineas.push({
                        concepto: inp.value,
                        cantidad: 1,
                        precio_unitario_mano_obra: parseFloat(preciosInputs[idx].value) || 0,
                        subtotal_mano_obra: parseFloat(preciosInputs[idx].value) || 0
                    });
                });

                originalData.cliente = clienteModificado;
                originalData.resumen_actuacion = resumenModificado;
                originalData.total_estimado_mano_obra = totalModificado;
                originalData.desglose_lineas = nuevasLineas;

                document.getElementById('loading').classList.remove('hidden');

                try {
                    const response = await fetch('/api/generar-pdf', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(originalData)
                    });
                    const data = await response.json();
                    if (response.ok) {
                        window.open(data.pdf_url, '_blank');
                    } else {
                        alert("Error al generar el PDF.");
                    }
                } catch(err) {
                    alert("Error de conexión.");
                } finally {
                    document.getElementById('loading').classList.add('hidden');
                }
            }
        </script>
    </body>
    </html>
    """

# ==========================================
# ENDPOINTS DE LA API (CON INTELIGENCIA FONTANERO)
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
        Eres el asistente técnico de un fontanero autónomo experto. Interpreta la nota de voz teniendo en cuenta la jerga de fontanería.
        Devuelve EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
        {
          "cliente": "Nombre detectado o Cliente",
          "urgencia": "Normal o Urgente",
          "resumen_actuacion": "Descripción técnica de la avería",
          "desglose_lineas": [
            {"servicio_id": "F_01", "concepto": "Reparación de fuga", "cantidad": 1, "precio_unitario_mano_obra": 60.0, "subtotal_mano_obra": 60.0}
          ],
          "materiales_a_utilizar": [{"material": "Latiguillos (unidad)", "cantidad": 1}],
          "total_estimado_mano_obra": 60.0,
          "tiempo_total_estimado_horas": 1.0,
          "observaciones_imprevistos": null
        }
        """
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',  # <-- Sin el prefijo "models/"
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
        import traceback
        traceback.print_exc()  # Esto imprimirá el error real completo en los logs de Render
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/generar-pdf")
async def api_generar_pdf(presupuesto: dict = Body(...)):
    doc = SimpleDocTemplate("presupuesto_fontaneria.pdf", pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('TituloEmpresa', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor("#2563eb"), spaceAfter=4)
    estilo_sub = ParagraphStyle('SubHeader', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=15)
    estilo_h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor("#1e293b"), spaceBefore=12, spaceAfter=6)
    estilo_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#334155"), leading=14)
    
    story.append(Paragraph(f"🔧 {NOMBRE_COMERCIAL_DEFAULT}", estilo_titulo))
    story.append(Paragraph(f"Teléfono de contacto: {TELEFONO_DEFAULT}", estilo_sub))
    
    story.append(Paragraph("<b>Datos del Cliente y Avería</b>", estilo_h2))
    story.append(Paragraph(f"<b>Cliente:</b> {presupuesto.get('cliente', 'Cliente')}", estilo_texto))
    story.append(Paragraph(f"<b>Urgencia:</b> {presupuesto.get('urgencia', 'Normal')}", estilo_texto))
    story.append(Paragraph(f"<b>Actuación:</b> {presupuesto.get('resumen_actuacion', '')}", estilo_texto))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("<b>Desglose de Trabajos</b>", estilo_h2))
    data_tabla = [["Concepto", "Cant.", "Precio U.", "Subtotal"]]
    for linea in presupuesto.get('desglose_lineas', []):
        data_tabla.append([
            linea.get('concepto', ''), 
            str(linea.get('cantidad', 1)), 
            f"{linea.get('precio_unitario_mano_obra', 0.0):.2f} €", 
            f"{linea.get('subtotal_mano_obra', 0.0):.2f} €"
        ])
    
    t = Table(data_tabla, colWidths=[240, 50, 80, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTSIZE', (0,0), (-1,-1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    
    total_mano_obra = presupuesto.get('total_estimado_mano_obra', 0.0)
    story.append(Paragraph(f"<b>TOTAL PRESUPUESTO: {total_mano_obra:.2f} €</b>", ParagraphStyle('Total', parent=estilo_texto, fontSize=12, textColor=colors.HexColor("#166534"))))
    
    doc.build(story)
    return {"estado": "ok", "pdf_url": "/descargar-pdf"}

@app.get("/descargar-pdf")
def descargar_pdf():
    return FileResponse("presupuesto_fontaneria.pdf", media_type="application/pdf", filename="presupuesto_fontaneria.pdf")