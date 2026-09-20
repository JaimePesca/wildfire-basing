# Reporte de verificacion academica, rama revision-citas-acronimos

Fecha: 2026-09-19/20. Alcance: fases 0-2 del encargo de revision (citas,
acronimos, redaccion, floats) sobre paper/main.tex y paper/references.bib.
Metodo: seis pasadas de verificacion web independientes (metadatos contra
Crossref/doi.org campo por campo; texto completo donde fue accesible, con
citas textuales y pagina/seccion; nivel de acceso reportado por fuente, sin
excepcion). Regla del usuario 2026-09-19 aplicada: las citas de la Tabla 1
quedan exentas de la regla de antiguedad pre-2000.

Convencion de acceso: TEXTO COMPLETO (la fuente completa o la seccion que
respalda la afirmacion fue leida); ABSTRACT (solo resumen o registro
bibliografico); METADATOS (existencia y ficha verificadas, contenido no
leido); NO ACCESIBLE.

Estado de commits (uno por bloque, como se pidio; el orden difiere del
alfabetico porque B, C y D esperaron verificacion de fuentes):
Fase 0 (74659b9), A (f08757d), E (c76522a), F (8b089f1), G (ed54d7a),
D (1191145), B (b053fdd), C (d55f7cc), Fase 2 (commit final de esta rama).
El PDF compila en 21 paginas, cero referencias indefinidas, cero overfull
boxes, y las 50 claves citadas coinciden 1:1 con las 50 entradas del .bib.

---

## 1. Tabla de citas por lugar de uso

Una fila por referencia y lugar de uso. "Seccion" usa la numeracion del
manuscrito (1 intro, 2 related work, 3 modelo, 4 datos, 5 metodo, 6
experimentos, 7 conclusiones).

### 1.1 Metodologia de optimizacion

| Referencia | Uso | Afirmacion | Evidencia | Acceso | Veredicto | Accion |
|---|---|---|---|---|---|---|
| rockafellar2000 | Secs. 1 y 3.3 | reformulacion lineal media-riesgo/CVaR | ec. (4), Teoremas 1-2, ec. (9)-(10) del paper (preprint del autor, U. Washington) | TEXTO COMPLETO | Respaldada | DOI 10.21314/JOR.2000.038 anadido. Nota: el paper usa beta para el nivel y alpha para la variable auxiliar; el manuscrito usa alpha/eta como notacion propia, sin atribuirla a la fuente |
| kleywegt2001 (anio 2002) | Secs. 4.1 y 6.5 | SAA; protocolo de replicacion, cotas inferior/superior y gap | Sec. 3.3 "Performance Bounds", ec. (3.1) (preprint) | TEXTO COMPLETO | Respaldada | Anio 2002 confirmado en Crossref/SIAM (el preprint de oct-2000 explica el error historico); DOI anadido |
| gupte2013 (NUEVA) | Secs. 1 y 3.3 | McCormick exacto para binaria por variable acotada | Sec. 2.1 p. 724: "the linearization of v_i = x z_i is exact because z_i in {0,1}", Prop. 2.1; Sec. 3 p. 728 (version publicada, repositorio U. Edimburgo) | TEXTO COMPLETO | Respaldada | Anadida (bloque D); enunciado cubre x acotada (el caso entero acotado es subcaso, sin sobreclamo) |
| helber2010 | Secs. 1 y 5 | fix-and-optimize | abstract verbatim (RePEc): "iterative fix-and-optimize algorithm... only a small subset of binary setup variables" | ABSTRACT | Respaldada (el manuscrito atribuye, no reclama prioridad) | DOI anadido |
| fischetti2003 | Sec. 5 | fix-and-optimize es distinto de local branching | metadatos exactos; abstract (cortes de local branching como soft-fixing por distancia) | METADATOS/ABSTRACT | Respaldada para el uso minimo | DOI anadido |
| pisinger2010 (NUEVA) | Secs. 1 y 5 (x2) | LNS y principio de relatedness (destroy relacionado) de Shaw | cap. 2010 pp. 399-419: "The LNS metaheuristic was proposed by Shaw"; sec. 2.2: "This related destroy neighborhood was introduced by Shaw" (preprint de autor, DTU Orbit, estructura identica a la ed. 2010) | TEXTO COMPLETO | Respaldada | Reemplaza a Shaw 1998. La ed. 2019 (pp. 99-127, DOI verificado) quedo descartada: paywalled, contenido no verificable directamente |
| ropke2006 | Secs. 1 y 5 | destroy aleatorio como practica ALNS estandar | Sec. 3.1.2: "The random removal algorithm simply selects q requests at random..." (version tech report DTU) | TEXTO COMPLETO | Respaldada | Sin cambios |
| mladenovic2007 (NUEVA) | Sec. 1 | familia p-median | Sec. 2 "Formulation" (definicion completa del PMP), abstract "basic discrete location problem" (version de autor) | TEXTO COMPLETO | Respaldada | Reemplaza a Hakimi 1964 |

### 1.2 Ciencia del fuego y metodos geoespaciales

| Referencia | Uso | Afirmacion | Evidencia | Acceso | Veredicto | Accion |
|---|---|---|---|---|---|---|
| nilsson2014 (NUEVA) | Sec. 3.2 | curvas de crecimiento aceleradas como descripcion estandar de diseno en ingenieria de fuego estructural | p. 517: "A common approach in fire safety engineering... exponential fire growth rate... alpha-t2 fire curve" (PDF oficial IAFSS) | TEXTO COMPLETO | Respaldada | Reemplaza a Ramachandran 1986. PERDIDA DE PRECISION DIVULGADA: la fuente llama "exponencial" a la curva alfa-t2 (polinomica); la frase del manuscrito se reescribio a "accelerating phenomenological growth curves" para decir solo lo que la fuente respalda. La linea especificamente exponencial (Ramachandran y Charters 2011, cap. 6 "Design Fire Size", ToC verificada) no pudo inspeccionarse; ver seccion 6 |
| sullivan2009 (NUEVA) | Sec. 3.2 | modelos de crecimiento forestal tipicamente elipticos | sec. 2.1 (Huygens): "the ellipse shape has been found to adequately described the propagation of wildland fires..." (arXiv 0706.4130 = IJWF 18(4):387-403, DOI 10.1071/WF06144) | TEXTO COMPLETO | Respaldada | Reemplaza a Van Wagner 1969 |
| balch2024 (NUEVA) | Sec. 3.2 | el crecimiento observado varia ordenes de magnitud con combustible y clima | pp. 426-427: "Maximum FGR ranged from 21 to 214,200 ha/day"; "mean and maximum FGRs vary by land cover and ecoregion... fastest... grasslands" (Science 386:425-431) | TEXTO COMPLETO | Respaldada | Anadida |
| scott2005 (NUEVA) | Sec. 4.2 | ordenamiento ordinal de tasas por tipo de combustible | GTR-153 pp. 9-11 (clases de tasa por modelo GR/SH/TL), p. 19 (NB "wildland fire will not spread"), pp. 25, 56 (espejo oficial NIFC) | TEXTO COMPLETO | Respaldada | Reemplaza a Anderson 1982; se anadio el matiz "strongly load-dependent" para shrub (SH1 very low a SH5 very high) |
| sharples2008 (NUEVA) | Sec. 4.2 | correccion exponencial de pendiente tipo McArthur | p. 181, ec. (1): "R_w exp(0.069 gamma_s)... doubles for every 10 deg" (PDF con maqueta CSIRO) | TEXTO COMPLETO | Respaldada | CORRECCION DE FONDO: la frase previa atribuia la forma exponencial a Rothermel 1972 y era FALSA |
| andrews2018 (NUEVA) | Sec. 4.2 | el factor de pendiente de Rothermel es tangente-cuadrado | GTR-371 pp. 10 y 14, ec. 51: "phi_s = 5.275 beta^-0.3 (tan phi)^2" (copia byte-identica Wayback del PDF oficial) | TEXTO COMPLETO | Respaldada | Sustituye la atribucion erronea a Rothermel 1972 |
| tang2011 (NUEVA) | Sec. 4.2 | metodo de Horn (diferencias finitas 3x3) para pendiente | lista de algoritmos con la formula exacta de Horn y ref [5] = Horn 1981 (PDF oficial WIT Press) | TEXTO COMPLETO | Respaldada | Reemplaza a Horn 1981. Dato adicional verificado: GDAL (gdaldem, codigo fuente) y GRASS (r.slope.aspect) usan Horn por defecto y lo citan; ArcGIS Pro ya NO cita a Horn |
| farr2007 (NUEVA) | Sec. 4.2 | cita de mision SRTM | Crossref exacto (Rev. Geophys. 45, RG2004) | METADATOS | Respaldada como cita canonica de producto | Texto completo no leido (Wiley 403); es la cita que la comunidad y NASA usan para la mision |
| birant2007 | Secs. 1 y 4.1 | ST-DBSCAN original y nuestra adaptacion | Secs. 3.1 (Eps1 espacial, Eps2 NO espacial), 3.3 (regla Delta-epsilon contra la media del cluster), 4.1 pp. 213-215 (prefiltro temporal discreto por dias consecutivos; borde al primer cluster descubierto) | TEXTO COMPLETO (copia hospedada, autenticada por cabecera/DOI/paginacion) | Respaldada | Frase de adaptacion reescrita (bloque D) para corresponder exactamente al texto leido; "standard across public ST-DBSCAN implementations" respaldado leyendo el codigo de tres implementaciones publicas (st-dbscan PyPI, stdbscan CRAN 0.2.0, py-st-dbscan eubr-bigsea): las tres usan dos radios continuos intersectados y ninguna implementa Delta-epsilon |
| korkola2024 | nota Tabla 3 | los estandares de ataque inicial difieren entre agencias (control a 24 h; Alberta 10:00 dia siguiente) | Introduccion: "a fire must be controlled within the first 24 h" (BC/NWT); "contained by 10:00 hours the following day" (Alberta, ademas 2 ha) (CSIRO, acceso abierto) | TEXTO COMPLETO | Respaldada | Metadatos corregidos: nombres completos de autores y volumen 33(12) |
| nwcg2026 | nota Tabla 3 | contencion en dos horas (ataque inicial NWCG) | definicion "Initial Attack Fire" confirmada verbatim solo via snippet de buscador; la pagina esta viva pero devuelve 403 a acceso automatizado (WAF) | NO ACCESIBLE (automatizado) | Pendiente-leve | Recomendacion: una visita manual de navegador antes del envio; URL del termino especifico disponible en la seccion 6 |

### 1.3 Caso de estudio (fuentes institucionales y de datos)

| Referencia | Uso | Afirmacion | Evidencia | Acceso | Veredicto | Accion |
|---|---|---|---|---|---|---|
| ungrdnd (NUEVA) | Sec. 1 | Cundinamarca lidera reportes historicos: 7,908 (1921-abr 2020), casi el doble del segundo | PDF oficial UNGRD (repositorio, handle 20.500.11762/36815): "Cundinamarca, Boyaca, Tolima y Huila... 7.908, 4.107, 3.052 y 2.345 registros" | TEXTO COMPLETO | Respaldada; la frase del manuscrito ahora dice indicador (reportes) y periodo exactos | Documento sin anio de publicacion (citado n.d.); el hosting es fragil (solo la URL directa del PDF por puerto 80 sirve contenido): ARCHIVAR en web.archive.org antes del envio (el intento automatico dio 429/500) |
| decreto2024 (NUEVA) | Sec. 1 | magnitud del episodio enero 2024: declaratoria de desastre nacional | Decreto 0037 del 27-ene-2024, Diario Oficial 52651, PDF UNGRD leido completo (art. 1; considerandos con 323 incendios, 6.723 ha, alertas IDEAM en 954 municipios) | TEXTO COMPLETO | Respaldada | El decreto NO menciona medios aereos: por eso la afirmacion se dividio en dos |
| ungrd2024 (NUEVA) | Sec. 1 | los medios aereos cargaron la respuesta: 755 h de vuelo, 2,170 descargas a fines de febrero | balance UNGRD 25-feb-2024: "755:02 horas de vuelo... 2.170 descargas realizadas por la FAC, el Ejercito, la Policia Nacional y la UNGRD" | TEXTO COMPLETO (fetch) | Respaldada | Nueva cita; el vinculo episodio-Firehawk quedo redactado como temporal ("in its wake"), no causal: ningun documento oficial documenta la causalidad |
| fac2025 (corregida, antes fac2026) | Secs. 1 y 4.3 | convenio COP 150 mil millones, dos Firehawk, con UNGRD; tanque 1,000 gal, recarga <60 s, 45 cm | articulo FAC del 11-jul-2025 (URL especifica): "un convenio por $150.000 millones para adquirir dos helicopteros tipo Firehawk"; "Su tanque tiene capacidad para 1.000 galones y puede recargarse en menos de 60 segundos desde fuentes de agua de 45 cm de profundidad" | TEXTO COMPLETO (fetch) | Respaldada en (a),(b),(d),(e) | La entrada apunta ahora a la URL del articulo, no a la portada; anio corregido a 2025. No existe articulo en presidencia.gov.co (atribucion retirada). "S-70i" NO aparece en ninguna fuente oficial (solo "tipo Firehawk"; prensa: "S-70"): el manuscrito dice ahora "S-70" |
| infodefensa2025 (NUEVA) | Sec. 1 | "first of their class in Latin America" | Infodefensa 16-jul-2025: "Fuera de Estados Unidos, Colombia sera el primer pais en incorporar este modelo para lucha contra incendios forestales" | TEXTO COMPLETO (fetch) | Respaldada solo por prensa especializada | La afirmacion quedo atribuida ("reported as..."); OJO: "primero fuera de EEUU" esta contradicho por el comunicado Lockheed de nov-2025 sobre la flota checa, por eso el manuscrito mantiene solo la version "en America Latina" |
| lockheedfirehawk (NUEVA) | Sec. 4.3 | tanque 1,000 gal y snorkel <1 min (corroboracion del fabricante) | pagina de producto ("Siphon, carry and release up to 8,000 pounds of water (1,000 gallons)") y comunicado 2019 ("retractable snorkel that can refill the tank in less than one minute") | TEXTO COMPLETO (fetch) | Respaldada | La profundidad de 45 cm NO esta en Lockheed (solo FAC); la velocidad crucero NO la publica el fabricante: el manuscrito lo divulga ("nominal 150 knot cruise... secondary sources") |
| firms + schroeder2014 (NUEVA) | Sec. 4.1 | producto VIIRS 375 m | cita de paper recomendada por el proveedor (FAQ FIRMS); Schroeder et al. 2014 RSE 143:85-96 verificado en Crossref | METADATOS (recomendacion del proveedor leida) | Respaldada | schroeder2014 anadida junto a firms; reconocimiento FIRMS/ESDIS anadido en "Data acknowledgment" |
| worldcover (ahora Zanaga et al. 2022) | Sec. 4.2 | ESA WorldCover 10 m v200 | cita solicitada por el proveedor, verificada contra el registro Zenodo (16 autores en orden, DOI 10.5281/zenodo.7254221, CC BY 4.0) | TEXTO COMPLETO (registro) | Respaldada | Entrada convertida a la cita oficial |
| worldpop (ahora Bondarenko et al. 2020) | Sec. 4.2 | raster Colombia 2020 constrained 100 m | pagina del dataset (id 49765) y API del hub: DOI 10.5258/SOTON/WP00684 y cita solicitada | TEXTO COMPLETO (registro) | Respaldada | CORRECCION: el DOI WP00645 anotado antes en el proyecto es el del proyecto paraguas, no el del raster |
| nasapower | Sec. 4.2 | viento diario MERRA-2 | guia oficial de citacion (power.larc.nasa.gov/docs/referencing): sin DOI; piden dos declaraciones | TEXTO COMPLETO (guia) | Respaldada | Declaracion del proyecto POWER anadida a la nota del .bib y al "Data acknowledgment" |
| srtm | Sec. 4.2 | producto SRTMGL1 V003 | handle API: el DOI con guion (MEaSUREs-SRTM) NO existe; el registrado es 10.5067/MEaSUREs/SRTM/SRTMGL1.003 (con barra), verificado ademas en NASA CMR y en la pagina Earthdata con la cita recomendada "NASA JPL (2013)" | TEXTO COMPLETO (registros) | Respaldada | DOI correcto anadido a la entrada; autor cambiado a NASA JPL y archivo LP DAAC |
| dane2018 | Sec. 4.2 | cross-check censal (campo STP27_PERS) | geoportal.dane.gov.co vivo; campo ya verificado contra el diccionario primario DANE (2026-08-30, CLAUDE.md) | METADATOS (liveness) | Respaldada | Sigla DANE expandida en la nota |
| aerocivil2025 | Sec. 4.3 | indice de aerodromos AD 1.3 | pagina "Conjunto de datos AIP" viva (hospeda "AD 1 3 Indice de aerodromos no controlados.xlsx", publicado 2025-06-16); los deep links versionados del eAIP se pudren | TEXTO COMPLETO (pagina) | Respaldada | URL cambiada a la pagina estable documentos/1118; Aerocivil y AIP expandidas |
| osm | Sec. 4.3 | cuerpos de agua OSM | sin cambios; ODbL expandida | METADATOS | Respaldada | - |
| car2026 | Sec. 4.3 | capa de lagunas CAR | la raiz sig.car.gov.co sirve una pagina IIS por defecto; el servicio real vive en /arcgis/rest/services | TEXTO COMPLETO (directorio REST) | Respaldada | URL corregida al path del servicio |

### 1.4 Filas de la Tabla 1 (detalle en la seccion 3)

wei2015 (TEXTO COMPLETO, Treesearch; desambiguacion frente al paper
chance-constrained hermano confirmada por DOIs distintos: 14-182 vs 14-112),
haight2007 (TEXTO COMPLETO, Treesearch), ntaimo2013 (ABSTRACT, OUP),
mendes2023 (ABSTRACT; redaccion de la prosa ajustada: ILS contrastado contra
soluciones MIP exactas), mendes2025 (ABSTRACT), skold2024 (TEXTO COMPLETO,
PDF ISCRAM; celda Bases corregida a Partial), alfaro2024 (TEXTO COMPLETO,
MDPI), ramalho2021 y ramalho2024 (ABSTRACT completo verbatim via Europe
PMC/FRAMES; listas de autores completadas con Crossref), rodriguezveiga2018
(ABSTRACT, OUP), rodriguezbarreiro2026 (arXiv TEXTO COMPLETO; version
publicada SEPS verificada en Crossref y adoptada en el .bib),
skorinkapov2024 (metadatos exactos; celdas confirmadas via el TEXTO COMPLETO
de la tesis de maestria publica del segundo autor; version de registro
sigue sin leerse), maras2023 (TEXTO COMPLETO, MDPI; "sequential" ->
"separate"), tasias2026 (ABSTRACT via Semantic Scholar; early view sin
volumen/paginas, correcto en el .bib), hodgson1978 y maclellan1996
(ABSTRACT; metadatos exactos; EXENTAS por decision del usuario).

---

## 2. Reemplazos de citas pre-2000

| Cita antigua | Reemplazo | Que respalda el reemplazo | Perdida de precision |
|---|---|---|---|
| hakimi1964 | mladenovic2007 (EJOR 179(3):927-939) | definicion y encuadre del p-median como problema basico de localizacion discreta (Sec. 2 de la fuente, leida) | Ninguna para el uso dado (el manuscrito no hace afirmacion historica sobre el origen) |
| shaw1998 | pisinger2010 (Handbook of Metaheuristics, pp. 399-419) | origen del LNS en Shaw y principio de relatedness/related destroy, ambos verbatim en el capitulo | Se deja de citar la fuente primaria; mitigado: el capitulo atribuye explicitamente a Shaw y el manuscrito conserva el nombre ("Shaw's relatedness principle") |
| ramachandran1986 | nilsson2014 (Fire Safety Science 11:517-530) | las curvas de crecimiento aceleradas (alfa-t2, llamadas "exponential fire growth rate" en esa literatura) son la descripcion estandar de diseno en fuego estructural | SI hay matiz, divulgado: alfa-t2 es polinomica, no exponencial pura; la frase del manuscrito se reescribio a "accelerating phenomenological growth curves" para no sobreclamar. La linea exponencial estricta (Ramachandran y Charters 2011) quedo sin inspeccionar (seccion 6) |
| vanwagner1969 | sullivan2009 (IJWF 18(4):387-403) | la elipse como plantilla estandar de los modelos de propagacion forestal (revision leida completa) | Ninguna; se gana una revision que cubre 1990-2007 |
| horn1981 | tang2011 (WIT Trans. Ecol. Environ. 146:143-154) | formula exacta de Horn (3FDWRSD) con la referencia a Horn 1981 | Se deja de citar el primario; mitigado: la formula esta verbatim en la fuente leida y coincide con src/scenarios/slope.py |
| anderson1982 | scott2005 (RMRS-GTR-153) | ordenamiento GR > SH > TL > NB con las clases de tasa del propio informe | Ninguna; se gano el matiz de carga en shrub, ahora en el texto |
| rothermel1972 | sharples2008 + andrews2018 | CORRECCION, no solo reemplazo: la respuesta exponencial a la pendiente es de los modelos tipo McArthur (2^(theta/10), Sharples ec. 1); el factor de Rothermel es tan^2 (Andrews GTR-371 ec. 51) | La frase anterior era incorrecta; la nueva es mas precisa |
| hodgson1978, maclellan1996 | SIN REEMPLAZO | filas de la Tabla 1 | EXENTAS por decision del usuario (2026-09-19); metadatos verificados (issue 2 anadido a Hodgson) |
| dantzig1955, beale1955 | eliminadas del .bib | nunca citadas en el texto (no aparecian en la lista compilada) | Ninguna |

---

## 3. Tabla 1: evidencia por celda

Definiciones de celdas como en el caption. Evidencia = fuente y lugar.

| Fila | Bases | Water | Joint | Cyclic | Strategic | Uncertainty | Evidencia y acceso |
|---|---|---|---|---|---|---|---|
| hodgson1978 | Yes | No | No | No | Yes | No | ABSTRACT (reconstruccion OpenAlex; editor 403): dos modelos de localizacion-asignacion de grupos de airtankers a bases potenciales, datos Alberta 1971-74; "one-strike initial attack" en el titulo verificado. EXENTA de la regla pre-2000 |
| maclellan1996 | Yes | No | No | No | Yes | No | ABSTRACT: home-basing de nueve CL-215 minimizando costo esperado anual sobre temporadas historicas; "without recourse" (nota a) es caracterizacion nuestra consistente con el abstract. EXENTA |
| skold2024 | Partial (CORREGIDA, antes Yes) | No | No | No | Yes | No | TEXTO COMPLETO (PDF ISCRAM): BIP p-median que posiciona recursos reposicionables en 286 puntos municipales para un dia especifico ("The model is solved for a specific day"); no construye infraestructura; sin agua, sin ciclo, deterministico. Nota b ampliada. DOI 10.59297/bvpahd97 anadido; sin numeros de pagina (no existen) |
| haight2007 | Partial | No | No | No | Yes | SP | TEXTO COMPLETO (Treesearch): "position up to 22 engines among 15 stations" (estaciones existentes); estructura de dos etapas por escenarios declarada en el texto |
| ntaimo2013 | Partial | No | No | No | Yes | SP | ABSTRACT (OUP): simulacion + SIP de dos etapas (EFGRM), posiciona dozers en Texas D12 |
| wei2015 | Partial | No | No | No | Yes | SP | TEXTO COMPLETO (Treesearch PDF): despliegue en estaciones fijas de crews/engines/water tenders + reglas de despacho; respuesta estandar, sin agua, sin ciclo. DOI 10.5849/forsci.14-182; el hermano chance-constrained es 14-112 |
| mendes2025 | Partial | No | No | No | Yes | RO | ABSTRACT (S2): "position the suppression resources... robust optimisation counterpart" |
| alfaro2024 | No | Yes | No | No | Yes | No | TEXTO COMPLETO (MDPI): p-median de reservorios (x_i "whether a water reservoir is installed"); helicopteros solo como motivacion; "strategic location of reservoirs"; deterministico (fuegos historicos 2017) |
| ramalho2021 | No | Yes | No | No | Yes | No | ABSTRACT verbatim (Europe PMC): asignacion de 21 reservorios por riesgo con fuzzy/distancia/analisis de redes; sin bases, sin incertidumbre |
| ramalho2024 | No | Yes | No | No | Yes | No | ABSTRACT verbatim (FRAMES): reservorios estrategicos para vehiculos terrestres (724) y aereos (42), geotecnologico, deterministico |
| rodriguezveiga2018 | No | Partial | No | Yes | No | No | ABSTRACT (OUP): "allocation of aerial resources to flight routes (circular paths... common loading and discharge points) and refueling points", minimiza tiempo de contencion; operacional |
| rodriguezbarreiro2026 | No | Partial | No | Yes | No | No | TEXTO COMPLETO del arXiv 2409.07937: selecciona puntos de carga de una lista dada (Sec. 2.2), circuitos/viajes endogenos con variables indexadas en tiempo y estado de carga (ecs. 4-7), bases de descanso dadas, deterministico. VERSION PUBLICADA adoptada: SEPS 105:102475 (2026), DOI 10.1016/j.seps.2026.102475, mismo equipo autor, titulo distinto; nota c de la tabla divulga que la clasificacion se verifico sobre el texto arXiv |
| skorinkapov2024 | No | Partial | No | No | No | No | metadatos Crossref exactos (Omega 122:102941). Celdas Water/Cyclic confirmadas via TEXTO COMPLETO de la tesis publica del segundo autor (repositorio GitHub del autor), que reformula el mismo ILP: "water points... predetermined and not a part of the schedule"; drops "given as problem input parameters" (D_kf^t); demanda de agua por frente W_f^t. Version de registro paywalled sin leer; nota d actualizada con esta cadena y su limite |
| maras2023 | Yes | Yes | No | No | Yes | No | TEXTO COMPLETO (MDPI): modelo 1 (heliportos, X_j, ecs. 1-4) y modelo 2 (fuentes de agua, Y_j, ecs. 5-8) SEPARADOS e independientes (el modelo 2 no consume la salida del 1: por eso "sequential" se cambio a "separate" en texto); umbrales k1/k2 fijos; sorties solo post hoc; sin incertidumbre |
| This paper | Yes | Yes | Yes | Yes | Yes | SP | por construccion (Secs. 3-4) |

---

## 4. Siglas: donde quedaron definidas

| Sigla | Definida en |
|---|---|
| CVaR | abstract ("conditional value-at-risk (CVaR)") y Sec. 1 |
| COP | Sec. 1 ("150 billion Colombian pesos (COP, with billion denoting 10^9 throughout)"); en 3.1 queda solo la sigla |
| FAC | Sec. 1 ("Colombian Aerospace Force (FAC, Fuerza Aeroespacial Colombiana)") |
| UNGRD | Sec. 1 ("National Unit for Disaster Risk Management (UNGRD, Unidad Nacional para la Gestion del Riesgo de Desastres)") |
| MILP | Sec. 1, antes de "sub-MILP" |
| FIRMS, NASA | Sec. 1 (contribucion 3) |
| ST-DBSCAN | Sec. 1 (expansion completa pedida) |
| ESA, SRTM, POWER | Sec. 1 (contribucion 3) |
| MIQCP | Sec. 3.3 (primera aparicion real) |
| CRS, EPSG | Sec. 3.1 (primera aparicion real) |
| SAA | Sec. 4.1 (primera aparicion en prosa; la sigla se retiro de la tabla de notacion) |
| VIIRS | Sec. 4.1 |
| CAR | Sec. 4.3 |
| MIP | Sec. 5 |
| NWCG | nota general de la Tabla 3 |
| ISCRAM | nota b de la Tabla 1 |
| ESDIS | parrafo "Data acknowledgment" |
| G, M (unidades) | nota de la Tabla 3, en ingles ("M denotes millions of COP (10^6); G denotes billions of COP (10^9)") |
| MERRA-2, DANE, AIP/Aerocivil, ODbL | notas del .bib (solo aparecen alli) |
| LNS, ALNS, MINLP, OSM, S-70(i) | no se usan como sigla en el texto: sin accion |

## 5. Revision del abstract (punto 5)

Detalle completo en revision/abstract_check.md. Resumen: 5 de 6 afirmaciones
consistentes con el cuerpo; la unica parcialmente respaldada es "which the
matheuristic crosses" (el cuerpo respalda que el matheuristico sigue
produciendo soluciones que igualan el mejor valor conocido por cuatro vias
en el regimen intractable, pero SIN certificado; "crosses" puede leerse como
"lo resuelve"). NO se cambio (afirmacion central: decision tuya); propuesta
recomendada: "...a regime the matheuristic still searches effectively,
albeit without certificates". La sigla CVaR quedo definida en el abstract
(~140 palabras, bajo el limite ITOR de 150). La afirmacion "the first to
site bases and water refill points jointly" sigue descansando en la
cobertura de la Tabla 1; ver Huang y Zhao abajo.

## 6. Pendientes que requieren tu decision (con recomendacion)

1. **Abstract, "which the matheuristic crosses"**: aplicar la redaccion
   propuesta arriba. RECOMENDACION: si, un referee leera el abstract contra
   la seccion 6.3 y "crosses" sobrevende.
2. **Huang y Zhao (2025), LOCALIZADO tras tres busquedas fallidas previas**:
   "Data driven multi-objective optimization of sustainable aviation
   emergency network for forest fire rescue", Sustainable Operations and
   Computers 6:116-129, DOI 10.1016/j.susoc.2025.04.001, acceso abierto
   CC BY-NC-ND (Beihang University). El abstract (verbatim via DOAJ)
   confirma: dos etapas, multiobjetivo estocastico, NSGA-II + SAA, datos de
   percepcion remota, caso Hainan. Las celdas Water/Cyclic/tipos de
   aeronave NO son clasificables desde el abstract, y el texto completo
   esta tras el bot-wall de ScienceDirect (se abre normal en navegador).
   FILA PROPUESTA (provisional, cada celda por confirmar sobre el texto):
   Bases Yes o Partial (red de rescate aereo), Water No, Joint No, Cyclic
   No, Strategic Yes, Uncertainty SP. RECOMENDACION: abre el articulo en tu
   navegador, confirma esas tres celdas y, si se sostienen, lo agrego a la
   Tabla 1 y al parrafo de literatura (no amenaza el gap: el abstract no
   menciona agua). Hasta entonces NO esta citado en el manuscrito.
3. **"S-70i" vs "S-70"**: el manuscrito dice ahora "S-70" (ninguna fuente
   oficial da la variante "i"; prensa dice "S-70"). CLAUDE.md (seccion 8,
   FROZEN) y src/model/aircraft.py siguen diciendo "S-70i": actualizarlos
   es tu decision (no toque CLAUDE.md). RECOMENDACION: alinear a "S-70
   Firehawk" o conseguir una fuente para la "i".
4. **NWCG PMS 205**: la pagina esta viva pero bloquea el acceso
   automatizado; la definicion se confirmo solo via snippet. RECOMENDACION:
   una visita manual antes del envio; el termino especifico esta en
   nwcg.gov/publications/pms205/nwcg-glossary-of-wildland-fire-pms-205/initial-attack-fire-iaf-8.
5. **PDF de la UNGRD (ungrdnd)**: hosting fragil; el guardado automatico en
   web.archive.org fallo por rate limit. RECOMENDACION: archivarlo
   manualmente (web.archive.org/save) antes del envio.
6. **Skorin-Kapov et al. (2024)**: la version de registro sigue paywalled;
   las celdas estan confirmadas via la tesis publica del segundo autor
   (cadena documentada en la nota d). Si tienes acceso de biblioteca a
   Omega, una lectura directa permitiria retirar la salvedad.
7. **Linea "exponencial" estructural**: si prefieres recuperar la
   referencia especificamente exponencial (no alfa-t2), la candidata es
   Ramachandran y Charters (2011), cap. 6 "Design Fire Size" (existencia y
   ToC verificadas; contenido no inspeccionable sin biblioteca).
   RECOMENDACION: dejar la redaccion actual, que es exacta.
8. **Verificadas pero no usadas** (para constancia): Daskin 2013 y Marin y
   Pelegrin 2019 (p-median, no accesibles a texto completo), ed. 2019 del
   capitulo de Pisinger y Ropke, libro Matheuristics 2021 (no verificable
   para "fix-and-optimize" por nombre), Vielma 2015, Zhou y Liu 2004,
   Hengl y Reuter 2009, Holborn et al. 2004, Karlsson y Quintiere
   2000/2022, Finney RMRS-RP-4 (leida, disponible como refuerzo del punto
   eliptico si se quiere una segunda cita).

## 7. Notas de forma

- Estilo de referencias: apalike (Harvard alfabetico), lo que ITOR exige
  segun la verificacion de guias del 2026-09-13 registrada en CLAUDE.md;
  keywords: 8 (limite 10); abstract ~140 palabras (limite 150).
- Floats: los 9 caen despues de su primera referencia (verificado sobre el
  PDF con pypdf, pagina y posicion); ninguno se separa mas de una pagina de
  su referencia; costo total del ordenamiento estricto: 18 -> 19 paginas
  (las 2 restantes hasta 21 son las referencias y textos nuevos).
- Sin guiones em/en en la prosa anadida. La unica aparicion de en dash en
  metadatos (titulo Crossref de Birant y Kut, "spatial-temporal") se
  reproduce con guion simple en el .bib, consistente con el resto.
- El grep final de "millones|millon" devuelve cero en main.tex y
  references.bib.
