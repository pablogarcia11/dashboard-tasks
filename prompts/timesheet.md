Prepara las tareas del parte de horas de la persona usuaria para un día. Las horas NO las calculas tú: solo agrupas y titulas.

Recibirás por la entrada estándar un JSON con:
- `commits`: commits del día en orden (sha, hora, proyecto, repo, mensaje, tamaño del cambio).
- `notas_im_back`: lo que la persona apuntó ese día en su diario de Notion, por proyecto (FUENTE PRINCIPAL para entender qué hizo).
- `reuniones`: reuniones del calendario (ya se colocan solas; NO las conviertas en tareas).
- `categorias`: las únicas categorías válidas.

Qué hacer:
1. Agrupa los commits en tareas. Una tarea junta varios commits seguidos y relacionados (mismo tema o misma entrada de las notas), no un commit por tarea. Los commits del mismo cambio en API y frontend van juntos. No juntes temas distintos (p. ej. rendimiento, permisos, evidencias, menú) aunque sean seguidos. Lo normal es de 7 a 10 tareas en un día completo.
2. Cada commit va en exactamente una tarea. Ordena las tareas por la hora de su primer commit.
3. Añade como tareas sin commits lo que aparezca en las notas y no esté cubierto por ningún commit (revisiones, documentación, informes, preparar datos de prueba…), con una estimación en `minutos`. No añadas reuniones que ya estén en `reuniones`.
4. Título: `<Proyecto> - <tarea>`, en español, frase corta en infinitivo y poco técnica (p. ej. "AI Risk - Permisos de Soporte e incidencias por rol", "AI Risk - Corregir los hallazgos de roles"). Usa el nombre de proyecto recibido.
5. Categoría: desarrollo o cambios de código → "Desarrollo de negocio"; documentación, informes o redacción → "Documentación"; gestiones internas → "Tareas administrativas"; aprender o cursos → "Formación". "Reunión" solo para reuniones apuntadas en las notas que no estén en `reuniones`.
6. Usa solo la información proporcionada. No inventes tareas.

Responde SOLO con JSON válido, sin texto alrededor, con esta forma:
{"tareas": [
  {"id": "t1", "proyecto": "AI Risk", "titulo": "AI Risk - …", "categoria": "Desarrollo de negocio", "commits": ["abcd1234", "ef567890"], "minutos": null},
  {"id": "t2", "proyecto": "AI Risk", "titulo": "AI Risk - …", "categoria": "Documentación", "commits": [], "minutos": 45}
]}
