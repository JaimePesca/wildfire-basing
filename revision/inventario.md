# Fase 0: inventario del manuscrito (rama revision-citas-acronimos)

Fecha: 2026-09-19. Archivos: paper/main.tex (1060 lineas), paper/references.bib
(429 lineas). Las lineas citadas corresponden al estado del manuscrito ANTES de
cualquier edicion de esta revision (commit 81b8fd4).

## 1. Citas con anio anterior a 2000

Decision del usuario (mensaje 2026-09-19, durante esta revision): las citas que
aparecen en la Tabla 1 (revision de literatura) quedan EXENTAS de la regla de
antiguedad por su importancia contextual. Eso cubre hodgson1978 y maclellan1996.
La regla sigue aplicando a toda cita fuera de la Tabla 1.

| Cita | Anio | Apariciones (archivo:linea) | Estado |
|---|---|---|---|
| hakimi1964 | 1964 | main.tex:92 | REEMPLAZAR (bloque C6) |
| shaw1998 | 1998 | main.tex:111, main.tex:618 | REEMPLAZAR (bloque C8) |
| hodgson1978 | 1978 | main.tex:162, main.tex:237 (Tabla 1) | EXENTA (fila de Tabla 1, decision del usuario) |
| maclellan1996 | 1996 | main.tex:164, main.tex:238 (Tabla 1) | EXENTA (fila de Tabla 1, decision del usuario) |
| ramachandran1986 | 1986 | main.tex:376 | REEMPLAZAR (bloque C15) |
| vanwagner1969 | 1969 | main.tex:378 | REEMPLAZAR (bloque C21) |
| horn1981 | 1981 | main.tex:532 | REEMPLAZAR (bloque C18) |
| anderson1982 | 1982 | main.tex:535 | REEMPLAZAR (bloque C22) |
| rothermel1972 | 1972 | main.tex:539 | REEMPLAZAR (bloque C22) |
| dantzig1955 | 1955 | solo references.bib:12 (sin \cite en el texto) | entrada sin usar, eliminar del .bib en Fase 2 |
| beale1955 | 1955 | solo references.bib:22 (sin \cite en el texto) | entrada sin usar, eliminar del .bib en Fase 2 |

Nota: las entradas sin usar no aparecen en la lista de referencias compilada
(natbib sin \nocite), pero se eliminan para dejar el .bib limpio.

## 2. Siglas y acronimos

"Definida" = aparece el nombre completo seguido de la sigla en su primera
aparicion en el cuerpo. El abstract cuenta por separado.

| Sigla | Primera aparicion | Definida ahi? | Accion |
|---|---|---|---|
| COP | main.tex:76 (intro) | NO (definida tarde, en main.tex:287, seccion 3.1) | definir en intro (bloque B4); en 3.1 queda solo la sigla |
| CVaR | abstract main.tex:48; cuerpo main.tex:102 (spelled) / main.tex:206 (sigla) | NO en abstract; en el cuerpo el nombre completo aparece en 102 sin la sigla | definir en abstract y en main.tex:102 "conditional value-at-risk (CVaR)" |
| MILP | main.tex:113 ("sub-MILP") | NO | definir "mixed-integer linear program (MILP)" antes de sub-MILP (punto 9) |
| MIP | main.tex:616 | NO | definir "mixed-integer programming (MIP)" |
| MIQCP | main.tex:464 | NO | definir "mixed-integer quadratically constrained program (MIQCP)" (punto 17; la primera aparicion es 464, no 685) |
| MINLP | no aparece | - | nada |
| SAA | main.tex:301 (tabla de notacion) | NO | quitar la sigla de la fila de la tabla; definir en la primera aparicion en prosa (main.tex:514) |
| LNS | nunca como sigla (siempre "large neighborhood search") | - | nada |
| ALNS | nunca como sigla (siempre "adaptive large neighborhood search") | - | nada |
| NASA | main.tex:122 | NO | definir (punto 11) |
| FIRMS | main.tex:122 | NO | definir "Fire Information for Resource Management System (FIRMS)" |
| VIIRS | main.tex:495 | NO | definir "Visible Infrared Imaging Radiometer Suite (VIIRS)" |
| ST-DBSCAN | main.tex:123 | NO | definir (punto 16) |
| DBSCAN | solo dentro de "ST-DBSCAN" | - | cubierto por la definicion de ST-DBSCAN |
| ESA | main.tex:124 | NO | definir "European Space Agency (ESA)" |
| SRTM | main.tex:124 | NO | definir "Shuttle Radar Topography Mission (SRTM)" (punto 18) |
| POWER | main.tex:124 | NO | definir "Prediction of Worldwide Energy Resources (POWER)" |
| MERRA-2 | solo references.bib:377 | NO | expandir en la nota del .bib |
| CRS | main.tex:286 (seccion 3.1, su primera aparicion real) | NO ("CRS" sin expandir) | definir ahi "coordinate reference system (CRS)" (punto 19) |
| EPSG | main.tex:286 | NO | expandir ahi (European Petroleum Survey Group, registro EPSG) |
| FAC | main.tex:75 | SI ("Colombian Aerospace Force (FAC)") | mejorar con el nombre oficial en espanol (bloque B4) |
| UNGRD | main.tex:75 | PARCIAL ("the national disaster risk management unit (UNGRD)", generico y en minuscula) | definir con nombre oficial (bloque B4) |
| CAR | main.tex:980 (seccion 6.7) | NO (en main.tex:549-550 se dice "regional water authority" sin sigla) | definir en main.tex:550 |
| DANE | solo references.bib:392 | NO | expandir en la nota del .bib |
| OSM | nunca como sigla en el texto (siempre "OpenStreetMap"); clave del .bib | - | nada en el texto |
| NWCG | main.tex:583 (Tabla 3) y notas | NO | expandir en la nota general de la Tabla 3 |
| AIP | solo references.bib:401 (titulo de aerocivil2025) | NO | expandir en la nota del .bib (Aeronautical Information Publication) |
| ODbL | solo references.bib:411 | NO | expandir (Open Database License) |
| CP | references.bib:55 (booktitle de shaw1998, "CP98") | - | desaparece si shaw1998 se reemplaza |
| ISCRAM | main.tex:259 (nota b de Tabla 1) | NO | expandir (Information Systems for Crisis Response and Management) |
| S-70i | main.tex:76 | - | designacion de modelo, no sigla; sin accion |
| G, M (unidades) | Tabla 3 (celdas desde main.tex:582; nota en main.tex:596) | definidas en la nota pero en espanol ("millones") | reescribir la nota en ingles (bloque B4); el primer uso de G/M es la propia Tabla 3, que precede a todos los usos de la seccion 6 |

## 3. Apariciones de "millones" / "millon"

| Archivo:linea | Contexto |
|---|---|
| main.tex:76 | "committed 150{,}000 millones COP" (intro) |
| main.tex:552 | "75{,}000 millones COP per unit" (seccion 4.3) |
| main.tex:553 | "150{,}000 millones for two" (seccion 4.3) |
| main.tex:596 | nota de Tabla 3: "M denotes millones (millions); G denotes thousands of millones" |
| references.bib:427 | nota de fac2026: "Program cost of 150,000 millones COP" |

No hay apariciones de "millon" ni "million" en espanol fuera de estas.

## 4. Tablas y figuras: primera referencia vs definicion del float

Todos los floats usan hoy el especificador [t]. El orden EN EL CODIGO FUENTE ya
es correcto (definicion despues de la primera \ref) en todos los casos; el
riesgo es de compilacion: un float [t] puede caer en la parte superior de la
misma pagina, visualmente ANTES del parrafo que lo referencia. Accion (bloque
G): cambiar a [!htbp] y verificar el PDF pagina por pagina.

| Float | Label | Primera \ref (linea) | Definicion (linea) | Seccion de la ref |
|---|---|---|---|---|
| Table 1 | tab:gap | 197 | 215 | 2 |
| Table 2 | tab:notation | 285 | 289 | 3.1 |
| Figure 1 | fig:studyarea | 482 | 484 | 4 |
| Table 3 | tab:params | 563 | 570 | 4.4 |
| Table 4 | tab:exp1 | 684 | 694 | 6.1 |
| Figure 2 | fig:runtime | 715 | 732 | 6.2 |
| Figure 3 | fig:tuning | 759 | 765 | 6.2 |
| Figure 4 | fig:exp4 | 841 | 858 | 6.4 |
| Figure 5 | fig:exp6 | 914 | 959 | 6.6 (definida 45 lineas despues de la ref, al final de la subseccion) |

Nota: el enunciado del encargo menciona "Table 4 y Figure 2 (secciones 6.1 y
6.2)"; en el fuente actual Table 4 es tab:exp1 (seccion 6.1) y Figure 2 es
fig:runtime (seccion 6.2), consistente con esa lectura.
