# AudioSplit + CapCut

Aplicación de escritorio que reúne AudioSplit TTS y CapCut Generator. Esta carpeta contiene una copia de sus motores y plantillas; no necesita las carpetas originales para funcionar.

## Instalación

Usa Python 3.10 o 3.11 (recomendado 3.11), Tkinter y FFmpeg con `ffmpeg` y `ffprobe` disponibles en PATH.

```bash
python -m venv .venv
```

Activa el entorno:

- Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

```bash
python -m pip install -r requirements.txt
python app.py
```

En algunas distribuciones Linux hay que instalar `python3-tk`. WhisperX descarga modelos la primera vez y puede requerir varios GB de memoria y disco. El generador con audios existentes funciona con la biblioteca estándar de Python y FFprobe, sin instalar WhisperX.

## Uso

Selecciona uno de los tres flujos:

- **Cortar audio y generar CapCut:** selecciona el documento TXT/DOCX, la narración completa y los videos. Los cortes se usan automáticamente como narraciones del proyecto.
- **Solo cortar audio:** selecciona documento y narración para obtener audios por párrafo y reporte.
- **Generar CapCut con audios existentes:** selecciona videos y audios ya preparados.

El selector **Documentos y narraciones** permite elegir **Una parte** (un documento y un audio) o **Dos partes**. Con Una parte solo se procesa Parte 1, incluso si antes cargaste archivos en Parte 2.

Para **dos audios con documentos distintos**, elige **Dos partes** y carga el primer documento y su audio en la pestaña **Parte 1** y el segundo documento y su audio en **Parte 2**. Pulsa **Iniciar** una sola vez: se corta cada audio con su propio texto y se genera un único proyecto, primero con todos los capítulos de la parte 1 y después los de la parte 2. Si solo tienes un par, elige **Una parte**.

La cantidad de videos se calcula con la suma de párrafos de ambos documentos. Por ejemplo, 20 párrafos + 20 párrafos, con 4 videos por capítulo, requieren 160 videos. Selecciona todos los videos principales juntos, con nombres que reflejen su orden a lo largo del proyecto completo. Los bloques genéricos se insertan según la numeración del proyecto completo.

Elige una carpeta de salida y un nombre nuevo. En TXT, separa párrafos con una línea vacía; en DOCX utiliza párrafos reales. Cada párrafo corresponde a un capítulo. Selecciona exactamente `capítulos × videos por capítulo` videos. Los medios se ordenan por nombre en orden natural (1, 2, 10). El valor predeterminado es 4 videos por capítulo; puedes exigir 40 capítulos si lo necesitas.

La aplicación conserva las opciones de formato, modelo y margen de corte, recorte inicial de videos y dos bloques genéricos con audio propio. Cada bloque es opcional e independiente: selecciona su video y audio juntos, o deja ambos vacíos. El bloque intermedio se inserta después del capítulo 7; si hay 7 capítulos o menos no se agrega. El bloque final se agrega al terminar el proyecto. Cada bloque conserva 3 segundos sin narración antes y después de su audio.

En **Ajustes > Stickers de CapCut** puedes pegar IDs de stickers de CapCut separados por comas. La app crea una pista de stickers, coloca el primero en 0:00 y luego uno cada X segundos, rotando la lista en orden; cada aparición dura el tiempo indicado. La duración no puede superar el intervalo. Si dejas los IDs vacíos, se eliminan los 3 stickers de la plantilla. CapCut resuelve estos stickers por `resource_id`; si uno no aparece, usa el ID de un proyecto donde ya lo hayas colocado. La integración todavía no se ha validado abriendo el borrador en CapCut: prueba primero con un proyecto pequeño.

La duración de cada narración se divide por igual entre sus videos. Se silencian los videos; se ralentizan si son cortos y se recortan si son largos. El margen del cortador añade una pequeña superposición entre audios contiguos; usa 0 si no la deseas.

## Archivos generados

```text
Carpeta de salida/Nombre elegido/
  audios/                 # en los modos con corte
    audio_001.mp3
    audio_002.mp3
    reporte.json
  CapCut/                 # en los modos con generación
    draft_content.json
    draft_meta_info.json
    timeline_report.json
```

Con dos partes, los cortes se guardan juntos con numeración continua (`audio_001`, `audio_002`, …). Los reportes de alineación se conservan por separado en `audios/parte_001/reporte.json` y `audios/parte_002/reporte.json`.

No muevas ni borres los audios o videos referenciados por el borrador. En el modo de audios existentes se mantienen las referencias a sus ubicaciones originales. La aplicación rechaza nombres de salida existentes para evitar sobrescrituras. Si el proceso falla, conserva la carpeta parcial para revisión; usa otro nombre al reintentar.

El formato de CapCut es privado. Las plantillas proceden del generador original para CapCut Desktop 9.6.0 y **la apertura del resultado en CapCut no está validada**. Prueba primero con un proyecto pequeño. Con CapCut cerrado y copia de seguridad de tus proyectos, puedes probar la carpeta `CapCut` en `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`. Puede ser necesario revincular medios. No se renderiza un video final ni se convierten codecs incompatibles.

## Verificación

```bash
python -m unittest discover -s tests -v
```

Las pruebas verifican la conexión entre ambos motores con cortes simulados y audios WAV reales analizados por FFprobe. No descargan modelos ni sustituyen la revisión de cortes con una narración real o la apertura manual en CapCut.

## Interfaz

La navegación lateral cambia entre el flujo completo, corte de audio y montaje con audios existentes. La pestaña **Archivos** reúne documentos, narraciones, videos y destino; **Ajustes** contiene las opciones del cortador, montaje, stickers y bloques genéricos. Los controles se adaptan al flujo elegido. **Actividad** muestra el registro y se abre automáticamente al iniciar. Puedes desplazarte por las secciones con la rueda o la barra lateral en ventanas pequeñas.

La interfaz usa Tkinter/ttk con un tema claro, navegación oscura y botones de acción violeta, sin dependencias gráficas adicionales.
