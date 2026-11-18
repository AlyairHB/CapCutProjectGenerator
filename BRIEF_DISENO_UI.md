# Brief de diseño — Edición Studio

## Solicitud

Diseñar una interfaz de escritorio moderna para **Edición Studio**, una aplicación que corta narraciones por párrafos y genera borradores editables de proyectos de CapCut. El diseño debe reflejar las funciones descritas aquí y permitir completar el flujo con claridad, desde seleccionar los archivos hasta encontrar el resultado.

Se busca una propuesta visual y de experiencia de usuario aplicable a la aplicación existente. No se solicita crear funciones nuevas de procesamiento.

## Contexto del producto

La aplicación está dirigida a personas que producen videos con narraciones TTS y necesitan organizar capítulos y videos sin montar cada segmento manualmente.

Está desarrollada en Python con Tkinter/ttk. La interfaz reside en `app.py`; la coordinación del trabajo, en `workflow.py`; los motores de corte y montaje, en `engines/`. Se prefiere un diseño realizable con la tecnología actual. Si una propuesta requiere otra biblioteca, debe indicarse como recomendación separada.

## Flujos de trabajo

### 1. Cortar audio y generar CapCut

Flujo principal:

1. Elegir una o dos partes de narración.
2. Cargar cada documento y su audio correspondiente.
3. Seleccionar todos los videos principales.
4. Elegir destino y nombre del proyecto.
5. Configurar las opciones necesarias.
6. Pulsar una sola vez el botón de inicio.
7. La aplicación corta cada narración con su documento y utiliza los cortes para generar un único borrador de CapCut.

No se deben solicitar los audios cortados de nuevo entre ambos pasos.

### 2. Solo cortar audio

Se cargan uno o dos pares de documento y narración. Se generan archivos de audio por párrafo y reportes de alineación. No se requieren videos ni se genera un borrador de CapCut.

### 3. Generar CapCut con audios existentes

Se seleccionan videos y narraciones ya divididas. No se solicitan documentos ni narraciones completas y no se ejecuta la transcripción.

## Entradas y controles

### Documentos y narraciones

Selector explícito de **Una parte** o **Dos partes**.

| Opción | Entradas | Comportamiento |
| --- | --- | --- |
| Una parte | Documento 1 y audio 1 | Solo se procesa el primer par. Los archivos previamente elegidos para Parte 2 se ignoran. |
| Dos partes | Documento 1, audio 1, documento 2 y audio 2 | Se procesa cada audio con su texto. Primero todos los capítulos de Parte 1 y después los de Parte 2. |

- Documentos: TXT o DOCX.
- En TXT, los párrafos se separan con una línea vacía.
- En DOCX, se usan párrafos reales.
- Cada párrafo no vacío corresponde a un capítulo.
- Narraciones: MP3, WAV, M4A, FLAC, OGG o AAC.
- La relación entre cada documento y su audio debe ser evidente.
- Las rutas pueden seleccionarse con un explorador o escribirse en los campos existentes.

### Videos y audios existentes

- Selección múltiple de videos: MP4, WEBM, MOV o MKV.
- Selección múltiple de audios existentes: MP3, WAV, M4A, AAC, FLAC u OGG.
- Mostrar la cantidad de archivos seleccionados.
- Los medios se ordenan por nombre en orden natural: 1, 2, 10.
- Todos los videos principales se seleccionan juntos, incluso si se utilizan dos partes.
- Los nombres de los videos deben reflejar el orden del proyecto completo.
- Los audios existentes se solicitan únicamente en el flujo de generación sin corte.

### Destino

- Carpeta de salida.
- Nombre de la carpeta del proyecto; valor inicial: `Proyecto_CapCut`.
- No se permite sobrescribir una carpeta de proyecto existente.
- El nombre no puede contener rutas ni caracteres especiales inválidos.

### Ajustes del cortador

| Control | Opciones o rango | Valor inicial |
| --- | --- | --- |
| Formato de salida | MP3 o WAV | MP3 |
| Modelo de transcripción | tiny, base, small o medium | small |
| Margen entre cortes | De 0 a 2 segundos | 0.08 s |

El margen puede producir una pequeña superposición entre audios consecutivos. Un valor de 0 la evita. Los modelos se descargan cuando son necesarios; el procesamiento puede tardar.

### Ajustes del montaje

| Control | Opciones o rango | Valor inicial |
| --- | --- | --- |
| Videos por capítulo | Entero mayor que cero | 4 |
| Recortar inicio de videos | Segundos, mayor o igual a 0 | 0.5 s |
| Exigir exactamente 40 capítulos | Activado o desactivado | Desactivado |

Reglas que la interfaz debe ayudar a comprender:

- Cantidad de videos requerida = capítulos totales × videos por capítulo.
- Con dos documentos, se suman los capítulos de ambos.
- Ejemplo: 20 + 20 capítulos, con 4 videos por capítulo, requieren 160 videos.
- La duración de cada narración se distribuye por igual entre sus videos.
- Los videos se silencian y se ajustan mediante ralentización o recorte.
- La narración conserva su velocidad normal.

### Stickers de CapCut (opcional)

- Campo para pegar IDs de stickers de CapCut separados por comas.
- Intervalo en segundos entre apariciones; valor inicial: 10 s.
- Duración de cada aparición; valor inicial: 3 s.
- El primero se coloca en 0:00; la lista de IDs se repite en orden.
- La duración no puede superar el intervalo.
- Si no se indican IDs, no se agregan stickers y se eliminan los de la plantilla.
- Estos controles pertenecen a los flujos que generan CapCut.

### Bloques genéricos opcionales

Cuatro selectores:

1. Video para después del capítulo 7.
2. Audio para después del capítulo 7.
3. Video final.
4. Audio final.

Cada bloque es opcional e independiente: selecciona su video y audio juntos, o deja ambos vacíos.

- El bloque intermedio se inserta después del capítulo 7 del proyecto completo.
- Si hay 7 capítulos o menos, el bloque intermedio no se inserta.
- Cada bloque incluye 3 segundos de imagen sin narración antes y después de su audio.
- El video del bloque se ajusta a la duración total y se silencia.
- Estos controles pertenecen a los flujos que generan CapCut.

## Organización de la interfaz

La versión actual utiliza navegación lateral para los tres flujos y tres pestañas:

- **Archivos:** partes de narración, documentos, medios y destino.
- **Ajustes:** opciones del cortador, montaje, stickers y bloques genéricos.
- **Actividad:** registro de procesamiento.

Puede proponerse una organización distinta si facilita la tarea y conserva todas las funciones. Debe mantenerse una acción principal clara y el acceso al estado del procesamiento.

Mostrar únicamente las secciones pertinentes para cada flujo. Con una sola parte, desactivar u ocultar la segunda. Evitar que la configuración avanzada opaque la selección de archivos.

## Estados que deben diseñarse

### Inicio y selección

- Estado inicial sin archivos.
- Una parte seleccionada.
- Dos partes seleccionadas, con relación clara entre documento y audio.
- Archivos seleccionados y cantidades visibles.
- Variantes correspondientes a los tres flujos.

### Validación

Presentar mensajes comprensibles para:

- Documento o audio obligatorio ausente.
- Segunda parte incompleta al elegir Dos partes.
- Documento sin párrafos.
- Cantidad de videos distinta de la requerida.
- Selección incompatible con la exigencia de 40 capítulos.
- Archivos inexistentes, repetidos o con formato no admitido.
- Valores numéricos inválidos.
- Bloques genéricos incompletos.
- Destino inválido o nombre ya existente.
- FFmpeg o FFprobe no disponible.

La aplicación valida los datos antes de iniciar el procesamiento. La presentación actual usa diálogos; puede proponerse validación junto a los campos como mejora de interfaz, señalándola como trabajo adicional.

### Procesamiento

- Botón principal desactivado para evitar ejecuciones simultáneas.
- Indicador de actividad indeterminado: actualmente no existe un porcentaje global fiable.
- Acceso automático al registro de Actividad al iniciar.
- Mensajes de transcripción, alineación, exportación y generación del borrador.
- Indicación de la parte que se está procesando cuando hay dos narraciones.
- No se permite cerrar la ventana durante el procesamiento; se muestra un aviso para esperar.

No representar un porcentaje exacto, tiempo restante o botón de cancelar como si ya estuvieran implementados.

### Finalización correcta

- Confirmación clara.
- Ruta de la carpeta generada.
- Acción principal habilitada de nuevo.
- Registro disponible para consulta.

### Error durante el procesamiento

- Mensaje de error legible y consultable en Actividad.
- Acción principal habilitada de nuevo.
- Explicación de que los archivos parciales se conservan para revisión.
- Indicación de usar otro nombre al reintentar si ya se creó la carpeta.

## Resultado del proceso

```text
Carpeta de salida / Nombre del proyecto /
  audios/                         # si se ejecutó el cortador
    audio_001.mp3
    audio_002.mp3
    ...
    reporte.json                  # con una sola parte
    parte_001/reporte.json        # con dos partes
    parte_002/reporte.json        # con dos partes
  CapCut/                         # si se generó el borrador
    draft_content.json
    draft_meta_info.json
    timeline_report.json
```

El formato de los cortes también puede ser WAV. Con dos partes, los audios tienen numeración continua.

La salida es un **borrador editable**, no un video renderizado. La aplicación no abre CapCut ni instala el proyecto automáticamente. La apertura del borrador todavía requiere validación manual en CapCut. Los audios y videos referenciados deben conservar sus ubicaciones.

## Dirección visual

- Estética de herramienta de edición moderna, sobria y fácil de usar.
- Jerarquía clara entre títulos, instrucciones, campos y acciones.
- Espaciado consistente y agrupaciones reconocibles.
- Rutas largas legibles dentro de los campos.
- Estados seleccionados, desactivados, de progreso, error y éxito distinguibles.
- Contraste suficiente y foco de teclado visible.
- No depender solo del color para comunicar información.
- Textos y etiquetas en español.
- Mantener el contenido accesible mediante desplazamiento en ventanas pequeñas.

La versión actual tiene fondo claro, panel lateral azul oscuro y acentos violeta. Esta paleta es una referencia, no una restricción; puede proponerse otra con justificación.

La ventana inicial mide aproximadamente 1120 × 820 y admite un mínimo de 960 × 740. El diseño debe funcionar en ambos tamaños. Priorizar escritorio Windows y Linux, incluidos los exploradores nativos de archivos.

## Entregables solicitados

1. Propuesta visual de la pantalla principal.
2. Vistas de los tres flujos con sus controles pertinentes.
3. Variantes de Una parte y Dos partes.
4. Diseño de Ajustes y Actividad.
5. Estados vacíos, validación, procesamiento, éxito y error.
6. Guía breve de colores, tipografía, espaciado y componentes.
7. Especificaciones suficientes para implementar la propuesta en Tkinter/ttk.
8. Lista separada de mejoras sugeridas que requieran funciones nuevas.

## Criterios de aceptación

- Se entiende cómo cargar un audio con su documento y cómo usar dos pares.
- Se distingue el corte de narraciones del montaje con audios existentes.
- Se entiende cuántos videos hacen falta y en qué orden se utilizan.
- El flujo completo requiere una sola acción de inicio.
- Todos los ajustes actuales siguen disponibles.
- El progreso y los errores son legibles.
- La finalización comunica dónde se guardaron los archivos y qué resultado se produjo.
- No se prometen renderizado, apertura automática de CapCut ni funciones inexistentes.
- La propuesta es utilizable en el tamaño mínimo de ventana.

## Texto breve para acompañar la solicitud

> Necesito rediseñar la interfaz de escritorio de Edición Studio, una aplicación Python/Tkinter que corta narraciones con documentos TXT/DOCX y genera borradores de CapCut. Adjunto este brief con sus funciones reales. Diseña una experiencia moderna en español para sus tres flujos, con soporte para uno o dos pares de documento y audio, selección de videos, ajustes, destino y seguimiento del proceso. Conserva las funciones descritas, incluye los estados principales y entrega especificaciones viables para Tkinter/ttk. Presenta cualquier función nueva como una sugerencia separada.
