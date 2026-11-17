# frutos-secos-cv — Visión artificial clásica, reto «Frutos secos»

Sistema experto que analiza una foto cenital de frutos secos sobre un tapete
verde: **detecta** cada unidad, la **identifica** con un árbol de decisión
explícito y **interpreta** la escena (conteo por clase, distribución, peso
estimado y comprobación de lote). Sin aprendizaje automático: solo
características geométricas y de color con umbrales medidos.

**Clases (5):** nuez (con cáscara) · avellana (con cáscara) · almendra (con
piel) · anacardo · cacahuete (con cáscara).

Pipeline: `RGB → preprocesado → segmentación → detección → características →
árbol de decisión → identificación → interpretación` (ver [docs/pipeline.md](docs/pipeline.md)).

## Instalación

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest            # tests con escenas sintéticas
```

## Flujo de trabajo

1. **Montaje**: tapete verde de **400×300 mm** (`config.yaml → escala.tapete_mm`;
   si cambias de tapete, mídelo y actualízalo ahí) y cámara cenital fija con el
   tapete ENTERO en el encuadre y un pequeño margen de mesa alrededor (campo
   ~480×360 mm → ~0,3 mm/px). La escala sale del área del tapete.
2. **Calibrar** (cada sesión, con la luz del aula), foto del tapete VACÍO:
   ```bash
   .venv/bin/python scripts/calibrar.py data/calibracion/vacio.jpg
   ```
   Imprime mm/px, campo de visión y cuántos px ocupa el objeto más pequeño
   (justificación experimental de la resolución).
3. **Fotos de desarrollo** (una clase por foto, frutos sueltos, posiciones y
   orientaciones variadas; ~3-5 fotos × 8-10 unidades por clase):
   `data/desarrollo/<clase>/*.jpg`. Opcional: `data/desarrollo/contacto/`
   con frutos tocándose, para justificar el umbral de separación.
4. **Comprobar la segmentación**: `scripts/ver_mascara.py data/desarrollo/*/*.jpg`
5. **Medir y fijar umbrales**:
   ```bash
   .venv/bin/python scripts/medir_umbrales.py
   ```
   Genera `salidas/umbrales/resumen.md` con estadísticas por clase,
   histogramas, el umbral propuesto por nodo (mínimo error, máximo margen) y
   qué otras características separarían ese nodo. Copia a mano a
   `config.yaml` los umbrales que decidas y quita los `TODO: medir`.
6. **Documentar** el árbol y las características: `scripts/documentar.py`
   → `docs/arbol.md`, `docs/caracteristicas.md`.
7. **Escenas de prueba** (mezcladas, nunca usadas para ajustar):
   `data/test/*.jpg`, etiquetadas con `scripts/etiquetar.py`.
8. **Evaluar**: `scripts/evaluar.py` → `salidas/evaluacion/informe.md` con
   precisión/exhaustividad de detección, matriz de confusión, exactitud y %
   de escenas con inventario exacto.
9. **Demo**:
   ```bash
   .venv/bin/python scripts/demo.py escena.jpg --traza --mostrar
   .venv/bin/python scripts/demo.py --ipwebcam 192.168.1.20   # móvil (ver abajo)
   .venv/bin/python scripts/demo.py --camara 0                # webcam del PC
   ```
   Teclas: `c` calibrar (tapete vacío) · `espacio` analizar · `m` ver máscara ·
   `g` guardar foto · `q` salir.

## Usar la cámara del móvil

El móvil emite su cámara por wifi con una app y el PC la recibe (misma red).

| App | Móvil | Comando |
|---|---|---|
| **IP Webcam** (recomendada) | Android | `scripts/demo.py --ipwebcam IP` |
| DroidCam | Android / iOS | `scripts/demo.py --droidcam IP` |
| Otra app MJPEG | — | `scripts/demo.py --camara http://IP:PUERTO/video [--foto-url ...]` |
| Webcam virtual por USB (cliente DroidCam/Iriun en el PC) | — | `scripts/demo.py --camara 1` |

1. Instala la app, pulsa «Iniciar servidor» y apunta la IP que muestra
   (p. ej. `http://192.168.1.20:8080`). Comprueba que esa dirección abre en
   el navegador del PC.
2. Coloca el móvil **cenital y fijo** (soporte o trípode), con todo el tapete
   en el encuadre. Desactiva el bloqueo de pantalla y, si la app lo permite,
   fija el enfoque y la exposición: si cambian solos, cambian los colores.
3. `scripts/demo.py --ipwebcam 192.168.1.20` → con el tapete vacío pulsa `c`.
4. Fotos de desarrollo con la misma cámara: `--guardar-en data/desarrollo/nuez`
   y pulsa `g` en cada colocación distinta (repite por clase y para `test/`).

Con IP Webcam, `c`, `espacio` y `g` descargan una **foto fija a resolución
completa** (`/photo.jpg`), con más detalle que el vídeo de la vista previa.
Calibración, fotos de desarrollo y análisis salen así de la misma fuente y
la escala mm/px es coherente. Si la imagen llega girada, usa `--rotar 90`.
Si el móvil se mueve o cambias de resolución, recalibra con `c`.

## Estructura

| Ruta | Contenido |
|---|---|
| `config.yaml` | **Todos** los parámetros, el árbol de decisión y las clases. Los `TODO: medir` son provisionales. |
| `src/` | cámara (webcam / móvil), preprocesado, calibración, segmentación, detección, características, árbol, interpretación, evaluación, visualización, pipeline |
| `scripts/` | calibrar, ver_mascara, medir_umbrales, documentar, etiquetar, evaluar, demo, generar_sintetico, evaluar_sesiones, evaluar_luz (robustez a la luz sobre fotos reales) |
| `tests/` | ~80 tests con escenas **sintéticas** (solo prueban el código; no justifican umbrales) |
| `simulador/` | render fotorrealista sencillo (relieve 3D, luz con ángulo, sombras, cámara) para probar la robustez a la luz |
| `docs/` | pipeline, árbol y tabla de características (estos dos, generados) |
| `data/` | `calibracion/`, `desarrollo/<clase>/`, `desarrollo/contacto/`, `test/` + `etiquetas.json` |

## Decisiones de diseño

- **Familia elegida: frutos secos.** Marrón/beige sobre verde → la
  segmentación por tono (H) es muy robusta; no se estropean (mismos objetos
  en desarrollo y examen); las 5 clases difieren en tamaño, forma y luminosidad.
- **Tamaños en mm**, no en px: la escala sale de la calibración (área del
  tapete conocida, o `--mm-por-px` medido con regla). El árbol no depende de
  la altura de la cámara.
- **Robustez a la luz**:
  - segmentación por **exceso de verde (ExG)** sobre la cromaticidad en RGB
    lineal, con umbral adaptativo por imagen: las sombras, los focos y los
    cambios de color de la luz no la afectan;
  - **color relativo al tapete** (von Kries) y cromaticidad `rojo_rel`, que
    no depende ni de la intensidad, ni del color, ni del ángulo de la luz;
  - en 8 iluminaciones simuladas (de cenital a rasante a 15°, foco, cálida,
    luz mixta), las escenas con inventario exacto pasan del 14 % al 78 % y la
    clasificación del 77 % al 97 %, calibrando o no con la misma luz.
- **Frutos en contacto y racimos**:
  transformada de distancia → máximos prominentes → cuello + color →
  watershed por niveles; y un **bucle de verificación con el árbol**: cada
  pieza debe cumplir el rango medido de su clase, incluidos los rasgos de
  integridad (profundidad de los dos entrantes más hondos: un fruto tiene
  como mucho uno hondo, dos pegados dejan dos). Si no, se generan
  hipótesis (particiones a varias escalas + cortes por entrantes) y se
  elige la que deja menos área sin explicar con menos piezas. Después se
  **unen** piezas vecinas cuya unión es un fruto válido (una nuez partida
  por su sutura) y se **ajustan las fronteras** a la imagen con un
  watershed de color desde el núcleo de cada pieza. El relleno de huecos
  solo cierra huecos pequeños: el tapete que encierra un racimo no es fruto.
  `scripts/diagnosticar_estres.py` clasifica cada error con la verdad por
  píxel del simulador (mezcla, troceado, clasificación).
- **Distancia de la cámara**: todos los tamaños (también los kernels
  morfológicos y el anillo de color) van en mm; el color se mide en el
  núcleo del fruto para que no lo contamine el borde con poca resolución.
- **Árbol declarativo** en `config.yaml`: cada nodo con característica,
  umbral y justificación; el código solo lo recorre y devuelve la traza.
  Hojas con rango `validar` → objetos extraños salen como `desconocido`.
- **Interpretación configurable**: `interpretacion.lote_esperado` permite
  comprobar en el examen una composición dada sin tocar código.

## Banco de estrés (racimos, distancias, luces extremas)

```bash
.venv/bin/python scripts/generar_estres.py                          # data/estres/ (validación)
.venv/bin/python scripts/generar_estres.py --desarrollo --salida data/desarrollo_estres
.venv/bin/python scripts/evaluar_estres.py --nombre prueba          # desglose por racimo/cámara/luz/clase
```

## Pruebas de robustez con imágenes sintéticas

```bash
.venv/bin/python scripts/generar_sintetico.py              # 8 sesiones de luz en data/sintetico/
D=data/sintetico
.venv/bin/python scripts/medir_umbrales.py --sesion $D/cenital_difusa --sesion $D/lateral_45 --sesion $D/calida_tenue
.venv/bin/python scripts/evaluar_sesiones.py $D/*/ --referencia $D/cenital_difusa --nombre prueba
```
`evaluar_sesiones.py` da una tabla por luz con dos protocolos: calibrando en
cada sesión, o calibrando una vez y cambiando la luz. Los umbrales actuales
de `config.yaml` salen de estos datos sintéticos: **hay que volver a medirlos
con fotos reales**.

## Limitaciones conocidas

- Racimos de 3–4 frutos muy apretados pueden quedar sin separar del todo
  (salen como «desconocido»).
- Frutos **apilados** (uno encima de otro) no se resuelven (visión 2D).
- Si la cámara cambia de altura o resolución tras calibrar, hay que recalibrar
  (el sistema avisa si la resolución de la foto no coincide).
