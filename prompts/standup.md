Redacta el stand-up diario de la persona usuaria para el canal de Slack #equipo-tecnologia-stand-up.

Recibirás por la entrada estándar un JSON con:
- `ayer`: el día laborable anterior. `notas_im_back` es lo que la persona apuntó en su diario de Notion (FUENTE PRINCIPAL), agrupado por proyecto. `commits` y `reuniones` son apoyo.
- `hoy`: `pendientes_de_ayer` (lo que dejó apuntado como pendiente), `tareas_activas` de Notion, `reuniones` y `trabajo_sin_terminar` (cambios sin commitear o sin subir).

Reglas:
- Usa solo la información proporcionada. Si algo no está claro, dilo en vez de inventarlo.
- "Tareas realizadas el último día" sale sobre todo de `ayer.notas_im_back`. Usa los commits solo para completar algo hecho que no esté en las notas. Si no hay notas, resume desde los commits y reuniones.
- Ignora proyectos sin tareas.
- Cada tarea: frase corta en infinitivo, poco técnica, de 4 a 10 palabras ("Corregir…", "Revisar…", "Ajustar…"). Condensa: como mucho 8 tareas por proyecto, más una última "Subir cambios a producción" si algo se pasó a production. Antes de responder, cuenta las tareas de cada proyecto; si pasan de 8, fusiona las relacionadas (p. ej. dos ajustes de la misma pantalla) o quita las menores (limpiezas, preparación de datos) hasta dejar 8.
- Las reuniones van bajo su proyecto como "Reunión <tema>".
- "Tareas que haré durante hoy": pendientes de ayer, tareas activas en curso, reuniones de hoy y trabajo sin terminar. No repitas tareas equivalentes. Si no hay nada, pon una sola viñeta "• Por definir".

Responde SOLO con el mensaje, sin explicaciones ni bloques de código, exactamente con este formato (markdown de Slack; las subviñetas llevan 4 espacios delante):

Buenos días! :saluting_face:
*Tareas realizadas el último día*
• <Proyecto>
    ◦ <tarea>
    ◦ <tarea>
*Tareas que haré durante hoy*
• <Proyecto>
    ◦ <tarea>
