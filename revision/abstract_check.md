# Bloque A(5): verificacion del abstract contra el cuerpo

Fecha: 2026-09-19. Metodo: cada afirmacion del abstract se contrasto con las
secciones 1, 2, 3, 5, 6 y 7 del manuscrito. Regla aplicada: si hay diferencia,
se reporta aqui con propuesta, NO se reescribe el abstract (los cambios a
afirmaciones centrales del abstract requieren decision del usuario).

| # | Frase del abstract | Respaldo en el cuerpo | Veredicto |
|---|---|---|---|
| 1 | "the first to site bases and water refill points jointly with cycle-endogenous productivity" | Seccion 1 (contribucion 1) y seccion 2: "joint siting appears in no prior model; and no work combines cycle-dependent productivity with strategic, uncertainty-aware siting", sustentado en la Tabla 1. | CONSISTENTE, con la salvedad heredada de que dos filas candidatas del borrador previo (Wang et al. 2026; Huang y Zhao 2025) siguen sin poder localizarse y estan excluidas de la Tabla 1; la afirmacion "first" descansa en la cobertura de esa tabla. Ver el resultado de la busqueda de Huang y Zhao en VERIFICATION_REPORT.md. |
| 2 | "as a two-stage mean-risk (CVaR) stochastic program" | Seccion 3.3, ecuacion (5) y \citep{rockafellar2000}. | CONSISTENTE. La sigla CVaR no estaba definida en el abstract; se corrigio como parte del bloque E (definicion "conditional value-at-risk (CVaR)" en el propio abstract), sin tocar el contenido de la afirmacion. |
| 3 | "with an exact linearization" | Seccion 3.3 ("McCormick envelope that is exact, not a relaxation, because z is binary and x <= M is valid") y seccion 6.1 (objetivos identicos MILP vs bilineal en toda instancia probada). | CONSISTENTE. |
| 4 | "a fix-and-optimize matheuristic whose reduced subproblems are exact" | Seccion 5: "solves the reduced sub-MILP exactly over the full scenario set... Dropping a site that is closed in the incumbent and outside the neighborhood is exact, not an approximation". | CONSISTENTE. La exactitud afirmada es la del subproblema (evaluacion verificada del objetivo verdadero), no optimalidad global del metodo; el cuerpo lo dice igual. |
| 5 | "sequential bases-first planning matches the integrated optimum wherever certification is possible" | Seccion 6.3: "the best sequential solution matches the integrated optimum to solver tolerance" en toda configuracion certificable (uno y dos aviones). | CONSISTENTE. Matiz menor: el cuerpo dice "to solver tolerance" (incluye el caso 90G donde el secuencial cae 0.005 por ciento por debajo del incumbente, ruido de tolerancia); el abstract dice "matches" a secas. Aceptable, pero si se quiere precision total: "matches the integrated optimum (to solver tolerance) wherever certification is possible". |
| 6 | "tractability collapses exactly where fleets and budget slack grow, which the matheuristic crosses" | Secciones 6.2 y 6.3: a 300 G el MILP directo queda con gap ~100 por ciento; el matheuristico si opera en ese regimen y en el catalogo completo, y sus soluciones coinciden con el mejor valor conocido por cuatro vias independientes (14,478.11), PERO sin certificado de optimalidad: son cotas superiores. | PARCIALMENTE RESPALDADA. "Crosses" puede leerse como "resuelve a traves del colapso", y eso el cuerpo NO lo respalda: lo que respalda es que el matheuristico sigue produciendo soluciones de la mejor calidad conocida en el regimen donde el MILP directo pierde el certificado. PROPUESTA (para decision del usuario, no aplicada): "...which the matheuristic negotiates, returning solutions that match the best known bounds, though without optimality certificates" o, mas corto, "...a regime the matheuristic still searches effectively, albeit without certificates". |

## Nota sobre conteo de palabras

El abstract queda en ~138 palabras tras la expansion de CVaR (limite ITOR: 150).
Cualquiera de las propuestas del punto 6 lo mantiene por debajo de 150; la
version corta suma ~6 palabras.

## Decision pendiente del usuario

Punto 6: aprobar una de las dos redacciones propuestas (o mantener "which the
matheuristic crosses"). Recomendacion: la version corta, porque "crosses" sin
matiz sobrevende un regimen donde el propio manuscrito insiste en que falta el
certificado, y un referee de ITOR va a leer el abstract contra la seccion 6.3.
