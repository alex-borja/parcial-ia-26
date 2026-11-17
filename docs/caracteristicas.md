# Características extraídas

_Generado por `scripts/documentar.py` a partir de `src/caracteristicas.py`._

Tamaños en mm/mm² usando la escala de la calibración. Color medido en la máscara erosionada (sin borde mezclado con el tapete).

| característica | unidad | cálculo | qué separa | en el árbol |
|---|---|---|---|---|
| `area_mm2` | mm² | nº de píxeles de la máscara · (mm/px)² | Tamaño. Separa la nuez (muy grande) del resto. | **sí** |
| `perimetro_mm` | mm | longitud del contorno externo (cv2.arcLength) · mm/px | Tamaño del borde; entra en la circularidad. |  |
| `diametro_equiv_mm` | mm | √(4·área/π) | Diámetro del círculo de igual área. |  |
| `longitud_mm` | mm | lado mayor del rectángulo mínimo girado (cv2.minAreaRect) | Dimensión mayor, independiente de la orientación. |  |
| `anchura_mm` | mm | lado menor del rectángulo mínimo girado | Dimensión menor. |  |
| `relacion_aspecto` | — | longitud / anchura | Alargamiento. Avellana ~1,1 vs. almendra/cacahuete > 1,5. |  |
| `circularidad` | — | 4π·área / perímetro² | 1 = círculo; baja con contornos alargados o rugosos. |  |
| `excentricidad` | — | √(1 − λ₂/λ₁), λ = autovalores de los momentos centrales de 2º orden | 0 = círculo, →1 = muy alargado (elipse equivalente). | **sí** |
| `solidez` | — | área / área de la envolvente convexa | Concavidad. El anacardo (media luna) deja mucho hueco. | **sí** |
| `extension` | — | área / área del rectángulo mínimo girado | Cuánto llena su caja: elipse ~0,79, rectángulo ~1. |  |
| `cuello_relativo` | — | radio del cuello entre máximos / radio menor (transformada de distancia) | Cintura: 1 = sin cintura; el cacahuete ~0,7. |  |
| `entrante1_mm` | mm | profundidad del defecto de convexidad más hondo del contorno (cv2.convexityDefects) | Concavidad principal: ~0 en nuez/avellana/almendra, moderada en cacahuete (cintura), alta en anacardo (media luna). |  |
| `entrante2_mm` | mm | profundidad del SEGUNDO defecto de convexidad más hondo | Integridad: un fruto tiene como mucho un entrante hondo (o dos suaves, el cacahuete); dos frutos pegados dejan DOS entrantes hondos en el contacto. | **sí** |
| `contraste_interno` | ΔE | mayor distancia CIELAB entre los colores medios de los máximos internos | Uniformidad de color del objeto; valores altos = dos frutos pegados. |  |
| `orientacion_grados` | ° | ½·atan2(2μ₁₁, μ₂₀ − μ₀₂) | Dirección del eje mayor (solo informativa). |  |
| `hu1` | — | −log₁₀|φ₁| (1er momento invariante de Hu) | Forma invariante a rotación/escala (informativa). |  |
| `L_media` | 0-100 | media de L* (CIELAB) dentro de la máscara erosionada | Luminosidad. Almendra/avellana oscuras vs. anacardo/cacahuete claros. |  |
| `a_media` | ± | media de a* (verde− / rojo+) | Tono rojizo. |  |
| `b_media` | ± | media de b* (azul− / amarillo+) | Tono amarillento. |  |
| `L_desv` | 0-100 | desviación típica de L* dentro de la máscara | Textura: la cáscara de la nuez es rugosa y con sombras internas. |  |
| `H_media` | 0-179 | media circular del tono H (HSV OpenCV) | Tono (informativo). |  |
| `S_media` | 0-255 | media de la saturación S (HSV) | Viveza del color. |  |
| `rojo_rel` | — | q_R/(q_R+q_G+q_B), q = RGB lineal fruto / RGB lineal tapete iluminado de alrededor | Rojez respecto al tapete; INVARIANTE a intensidad, color y ángulo de la luz. Almendra/avellana (piel rojiza) > anacardo/cacahuete (beige). | **sí** |
| `azul_rel` | — | q_B/(q_R+q_G+q_B) | Componente azul relativa (informativa). |  |
| `L_rel` | — | luminancia lineal fruto / luminancia tapete de alrededor | Claridad respecto al tapete; invariante a la intensidad de la luz, pero NO a su color ni a su ángulo (con luz rasante el tapete recibe menos luz que el fruto). | **sí** |
