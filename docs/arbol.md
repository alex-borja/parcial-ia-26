# Árbol de decisión

_Generado por `scripts/documentar.py` a partir de `config.yaml`._

```mermaid
flowchart TD
    N1{"N1: ¿Es mucho mayor que los demás?<br/>area_mm2 #gt; 772"}
    H1(["<b>NUEZ</b><br/><small>area_mm2 ∈ [850, 1609]</small><br/><small>solidez ∈ [0.93, 1.0]</small><br/><small>excentricidad ∈ [0.0, 0.62]</small><br/><small>rojo_rel ∈ [0.42, 0.85]</small><br/><small>entrante1_mm ∈ [0.0, 2.48]</small><br/><small>entrante2_mm ∈ [0.0, 1.61]</small>"])
    N2{"N2: ¿Es redondeado?<br/>excentricidad #lt; 0.69"}
    H2(["<b>AVELLANA</b><br/><small>area_mm2 ∈ [103, 205]</small><br/><small>solidez ∈ [0.91, 1.0]</small><br/><small>excentricidad ∈ [0.0, 0.71]</small><br/><small>rojo_rel ∈ [0.72, 0.95]</small><br/><small>entrante1_mm ∈ [0.0, 1.65]</small><br/><small>entrante2_mm ∈ [0.0, 1.5]</small>"])
    N3{"N3: ¿Es claramente rojizo respecto al tapete?<br/>rojo_rel #gt; 0.79"}
    H3(["<b>ALMENDRA</b><br/><small>area_mm2 ∈ [171, 320]</small><br/><small>solidez ∈ [0.91, 1.0]</small><br/><small>excentricidad ∈ [0.69, 0.96]</small><br/><small>rojo_rel ∈ [0.77, 0.93]</small><br/><small>entrante1_mm ∈ [0.0, 1.6]</small><br/><small>entrante2_mm ∈ [0.0, 1.23]</small>"])
    N3b{"N3b: ¿Es claramente beige?<br/>rojo_rel #lt; 0.755"}
    N4{"N4: ¿Es claramente convexo?<br/>solidez #gt; 0.895"}
    N4a{"N4a: ¿Es demasiado pequeño para ser un cacahuete?<br/>area_mm2 #lt; 235"}
    H4(["<b>ANACARDO</b><br/><small>area_mm2 ∈ [131, 360]</small><br/><small>solidez ∈ [0.73, 0.93]</small><br/><small>excentricidad ∈ [0.68, 0.96]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [2.12, 7.24]</small><br/><small>entrante2_mm ∈ [0.0, 1.24]</small>"])
    H5(["<b>CACAHUETE</b><br/><small>area_mm2 ∈ [208, 625]</small><br/><small>solidez ∈ [0.78, 1.0]</small><br/><small>excentricidad ∈ [0.68, 1.0]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [0.0, 5.03]</small><br/><small>entrante2_mm ∈ [0.0, 4.48]</small>"])
    N4a -->|sí| H4
    N4a -->|no| H5
    N4c{"N4c: ¿Tiene un solo entrante hondo (media luna)?<br/>entrante2_mm #lt; 0.78"}
    H6(["<b>ANACARDO</b><br/><small>area_mm2 ∈ [131, 360]</small><br/><small>solidez ∈ [0.73, 0.93]</small><br/><small>excentricidad ∈ [0.68, 0.96]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [2.12, 7.24]</small><br/><small>entrante2_mm ∈ [0.0, 1.24]</small>"])
    H7(["<b>CACAHUETE</b><br/><small>area_mm2 ∈ [208, 625]</small><br/><small>solidez ∈ [0.78, 1.0]</small><br/><small>excentricidad ∈ [0.68, 1.0]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [0.0, 5.03]</small><br/><small>entrante2_mm ∈ [0.0, 4.48]</small>"])
    N4c -->|sí| H6
    N4c -->|no| H7
    N4 -->|sí| N4a
    N4 -->|no| N4c
    N3c{"N3c: (zona de duda) ¿Es oscuro respecto al tapete?<br/>L_rel #lt; 0.69"}
    H8(["<b>ALMENDRA</b><br/><small>area_mm2 ∈ [171, 320]</small><br/><small>solidez ∈ [0.91, 1.0]</small><br/><small>excentricidad ∈ [0.69, 0.96]</small><br/><small>rojo_rel ∈ [0.77, 0.93]</small><br/><small>entrante1_mm ∈ [0.0, 1.6]</small><br/><small>entrante2_mm ∈ [0.0, 1.23]</small>"])
    N4b{"N4b: ¿Es claramente convexo?<br/>solidez #gt; 0.895"}
    N4ba{"N4ba: ¿Es demasiado pequeño para ser un cacahuete?<br/>area_mm2 #lt; 235"}
    H9(["<b>ANACARDO</b><br/><small>area_mm2 ∈ [131, 360]</small><br/><small>solidez ∈ [0.73, 0.93]</small><br/><small>excentricidad ∈ [0.68, 0.96]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [2.12, 7.24]</small><br/><small>entrante2_mm ∈ [0.0, 1.24]</small>"])
    H10(["<b>CACAHUETE</b><br/><small>area_mm2 ∈ [208, 625]</small><br/><small>solidez ∈ [0.78, 1.0]</small><br/><small>excentricidad ∈ [0.68, 1.0]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [0.0, 5.03]</small><br/><small>entrante2_mm ∈ [0.0, 4.48]</small>"])
    N4ba -->|sí| H9
    N4ba -->|no| H10
    N4bc{"N4bc: ¿Tiene un solo entrante hondo (media luna)?<br/>entrante2_mm #lt; 0.78"}
    H11(["<b>ANACARDO</b><br/><small>area_mm2 ∈ [131, 360]</small><br/><small>solidez ∈ [0.73, 0.93]</small><br/><small>excentricidad ∈ [0.68, 0.96]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [2.12, 7.24]</small><br/><small>entrante2_mm ∈ [0.0, 1.24]</small>"])
    H12(["<b>CACAHUETE</b><br/><small>area_mm2 ∈ [208, 625]</small><br/><small>solidez ∈ [0.78, 1.0]</small><br/><small>excentricidad ∈ [0.68, 1.0]</small><br/><small>rojo_rel ∈ [0.42, 0.79]</small><br/><small>entrante1_mm ∈ [0.0, 5.03]</small><br/><small>entrante2_mm ∈ [0.0, 4.48]</small>"])
    N4bc -->|sí| H11
    N4bc -->|no| H12
    N4b -->|sí| N4ba
    N4b -->|no| N4bc
    N3c -->|sí| H8
    N3c -->|no| N4b
    N3b -->|sí| N4
    N3b -->|no| N3c
    N3 -->|sí| H3
    N3 -->|no| N3b
    N2 -->|sí| H2
    N2 -->|no| N3
    N1 -->|sí| H1
    N1 -->|no| N2
```

## Nodos

| nodo | pregunta | regla (sí →) | justificación |
|---|---|---|---|
| N1 | ¿Es mucho mayor que los demás? | `area_mm2 > 772` | El área en mm² (escala calibrada) separa la nuez (Ø ~35 mm) de todas las demás clases con mucho margen (hueco de 456 mm²); no depende de la luz (la segmentación ExG no suma la sombra) ni de la distancia (se mide en mm). |
| N2 | ¿Es redondeado? | `excentricidad < 0.69` | La avellana es casi redonda. La excentricidad de la elipse de momentos usa todos los píxeles del objeto y es más estable que la relación de aspecto del rectángulo mínimo (sensible al ruido del borde). |
| N3 | ¿Es claramente rojizo respecto al tapete? | `rojo_rel > 0.79` | Piel marrón rojiza (almendra) frente a beige (anacardo, cacahuete), medida como cromaticidad del color RELATIVO al tapete (von Kries): no depende de la intensidad, del color ni del ángulo de la luz. En las fotos reales hay un hueco de 0,064 entre clases; por encima de 0,79 (casi toda almendra medida) es almendra SIN duda. |
| N3b | ¿Es claramente beige? | `rojo_rel < 0.755` | Por debajo de 0,755 están todos los beige medidos y ninguna almendra: es beige sin duda. Entre 0,755 y 0,79 (el hueco entre clases, donde no se midió ningún fruto) está la ZONA DE DUDA, que decide N3c con otra característica por si otra luz desplaza un poco el color. |
| N4 | ¿Es claramente convexo? | `solidez > 0.895` | El anacardo es curvo y deja mucho hueco en su envolvente convexa; la vaina del cacahuete suele ser casi convexa: por encima de 0,895 no hay ningún anacardo curvo y es cacahuete (salvo el anacardo de canto, N4a). Por debajo la solidez NO decide: los cacahuetes con mucha cintura o en gancho bajan a 0,83-0,88, dentro del rango del anacardo [0,778, 0,884]; decide N4c. |
| N4a | ¿Es demasiado pequeño para ser un cacahuete? | `area_mm2 < 235` | Un anacardo visto de canto apenas enseña su curva y sale convexo (solidez 0,91 en la demo con flash, por encima de N4), pero es mucho más pequeño que la vaina de cacahuete más pequeña medida (259 mm²). Su hoja sigue exigiendo el entrante de media luna (>= 2,12 mm). |
| N4c | ¿Tiene un solo entrante hondo (media luna)? | `entrante2_mm < 0.78` | El anacardo tiene UN entrante hondo (la media luna) y el segundo es casi nulo; el cacahuete cóncavo lo es por la cintura, que entra por AMBOS lados (o por un gancho), así que su segundo entrante es hondo. Un cacahuete de una semilla no tiene cintura, pero es muy convexo y ya lo decide N4. |
| N3c | (zona de duda) ¿Es oscuro respecto al tapete? | `L_rel < 0.69` | En la zona de duda del color decide la luminancia RELATIVA al tapete (almendra oscura, beige claro). L_rel separa con mucho margen pero se desplaza con luz muy rasante, por eso solo se usa aquí, para los pocos frutos de la banda dudosa. |
| N4b | ¿Es claramente convexo? | `solidez > 0.895` | Igual que N4 (anacardo frente a cacahuete), para los beige que llegan por la zona de duda del color. |
| N4ba | ¿Es demasiado pequeño para ser un cacahuete? | `area_mm2 < 235` | Igual que N4a. |
| N4bc | ¿Tiene un solo entrante hondo (media luna)? | `entrante2_mm < 0.78` | Igual que N4c. |

## Hojas y rangos de validación

Si un objeto llega a una hoja pero alguna característica cae fuera del rango medido de esa clase, se clasifica como **desconocido**.

| clase | validar |
|---|---|
| nuez | area_mm2 ∈ [850, 1609], solidez ∈ [0.93, 1.0], excentricidad ∈ [0.0, 0.62], rojo_rel ∈ [0.42, 0.85], entrante1_mm ∈ [0.0, 2.48], entrante2_mm ∈ [0.0, 1.61] |
| avellana | area_mm2 ∈ [103, 205], solidez ∈ [0.91, 1.0], excentricidad ∈ [0.0, 0.71], rojo_rel ∈ [0.72, 0.95], entrante1_mm ∈ [0.0, 1.65], entrante2_mm ∈ [0.0, 1.5] |
| almendra | area_mm2 ∈ [171, 320], solidez ∈ [0.91, 1.0], excentricidad ∈ [0.69, 0.96], rojo_rel ∈ [0.77, 0.93], entrante1_mm ∈ [0.0, 1.6], entrante2_mm ∈ [0.0, 1.23] |
| anacardo | area_mm2 ∈ [131, 360], solidez ∈ [0.73, 0.93], excentricidad ∈ [0.68, 0.96], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [2.12, 7.24], entrante2_mm ∈ [0.0, 1.24] |
| cacahuete | area_mm2 ∈ [208, 625], solidez ∈ [0.78, 1.0], excentricidad ∈ [0.68, 1.0], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [0.0, 5.03], entrante2_mm ∈ [0.0, 4.48] |
| anacardo | area_mm2 ∈ [131, 360], solidez ∈ [0.73, 0.93], excentricidad ∈ [0.68, 0.96], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [2.12, 7.24], entrante2_mm ∈ [0.0, 1.24] |
| cacahuete | area_mm2 ∈ [208, 625], solidez ∈ [0.78, 1.0], excentricidad ∈ [0.68, 1.0], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [0.0, 5.03], entrante2_mm ∈ [0.0, 4.48] |
| almendra | area_mm2 ∈ [171, 320], solidez ∈ [0.91, 1.0], excentricidad ∈ [0.69, 0.96], rojo_rel ∈ [0.77, 0.93], entrante1_mm ∈ [0.0, 1.6], entrante2_mm ∈ [0.0, 1.23] |
| anacardo | area_mm2 ∈ [131, 360], solidez ∈ [0.73, 0.93], excentricidad ∈ [0.68, 0.96], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [2.12, 7.24], entrante2_mm ∈ [0.0, 1.24] |
| cacahuete | area_mm2 ∈ [208, 625], solidez ∈ [0.78, 1.0], excentricidad ∈ [0.68, 1.0], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [0.0, 5.03], entrante2_mm ∈ [0.0, 4.48] |
| anacardo | area_mm2 ∈ [131, 360], solidez ∈ [0.73, 0.93], excentricidad ∈ [0.68, 0.96], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [2.12, 7.24], entrante2_mm ∈ [0.0, 1.24] |
| cacahuete | area_mm2 ∈ [208, 625], solidez ∈ [0.78, 1.0], excentricidad ∈ [0.68, 1.0], rojo_rel ∈ [0.42, 0.79], entrante1_mm ∈ [0.0, 5.03], entrante2_mm ∈ [0.0, 4.48] |
