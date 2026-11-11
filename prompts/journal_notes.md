Completa la entrada de un día del diario de trabajo de la persona usuaria en Notion: conserva lo que ya escribió y añade lo que falte a partir de sus commits de ese día.

Recibirás por la entrada estándar un JSON con:
- `encabezado_dia`: el título del día, p. ej. «Martes 10/11/2026».
- `ya_escrito`: lo que la persona ya apuntó ese día en su diario, en Markdown (puede estar vacío).
- `commits`: los commits del día agrupados por proyecto, en orden (hora, repo, mensaje en inglés, tamaño del cambio).

Pasos (en este orden):
1. Lee `ya_escrito`. Todo lo que ya está escrito es importante y se **conserva completo y literal**: mismos textos, mismos proyectos, mismo orden, mismas subviñetas y el mismo apartado «Pendiente:». No lo reescribas, no lo resumas, no lo reordenes ni lo corrijas.
2. Repasa los commits y decide, uno a uno, si lo que hacen **ya está mencionado** en lo escrito (aunque sea con otras palabras o de forma más general). Si ya lo está, no añadas nada por él.
3. Redacta solo lo que **falte** y añádelo en su proyecto: al final de la lista de ese proyecto, antes de su «Pendiente:» si lo tiene; o en un proyecto nuevo al final si no existía.
4. Si no falta nada, devuelve lo escrito tal cual.

Cómo redactar lo que añadas (imita el estilo de lo ya escrito si lo hay):
- En español, en primera persona y en pasado: «Corregí…», «Añadí…», «Revisé…», «Quité…».
- Poco técnico: el efecto para quien usa la aplicación, no el código. Nada de ficheros, funciones ni hashes.
- Junta los commits relacionados en una viñeta; si un tema tiene varios cambios, viñeta con el tema y dos puntos y subviñetas debajo.
- Frases completas y concretas, terminadas en punto. Usa solo la información de los commits; no inventes ni digas que algo se pasó a producción salvo que un commit lo indique.

Responde SOLO con Markdown, sin explicaciones ni bloques de código, con esta forma (las subviñetas llevan dos espacios delante):

# <encabezado_dia>
### <Proyecto>
- <lo ya escrito, tal cual>
- <lo que faltaba>.
- Pendiente:
  - <pendiente ya escrito>
### <Otro proyecto>
- <…>
