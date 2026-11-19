# Repositorios open-source evaluados (19 noviembre 2026)

Se comprobó que los repositorios siguientes existen y no están archivados en GitHub. La verificación NO implica auditoría de seguridad, compatibilidad ni licencia.

| Repositorio | Uso posible en ImageTrace | Decisión |
|---|---|---|
| https://github.com/JohannesBuchner/imagehash | SHA-independent perceptual hashing / Hamming distance | Ya utilizado en backend |
| https://github.com/opencv/opencv | ORB, homografía, alineación y diferencias localizadas; validar cortes y reescalados | Prioridad 1 para comparador |
| https://github.com/idealo/imagededup | Duplicados y similitud en repositorios de imágenes permitidas | Evaluar escalabilidad y licencia |
| https://github.com/exiftool/exiftool | Metadatos ampliados y extracción confiable; sandbox de comandos | Prioridad 2 |
| https://github.com/tesseract-ocr/tesseract | OCR local | Ya utilizado opcionalmente |
| https://github.com/JaidedAI/EasyOCR | OCR alternativo si Tesseract falla | Evaluar memoria y rendimiento |
| https://github.com/photoprism/photoprism | Arquitectura de indexación y organización de imágenes | Referencia, NO copiar código sin revisión de licencia |

## Propuesta de integración incremental

1. Evaluar ORB de OpenCV para reencuadres y detectar regiones similares sin identificar personas.
2. ExifTool mediante un subprocess aislado, límite de tiempo, no confiar en la salida y suprimir coordenadas GPS por defecto.
3. Evaluar imagededup con corpus de imágenes autorizadas, métricas de precisión y licencias.
4. Añadir evaluaciones con imágenes recortadas y modificadas, y resultados negativos.
5. Conectores de proveedores públicos solo tras validar términos y autorización. Ningún falso positivo presentado como fuente web real.

## Restricciones

- Prohibido indexar identidades o buscar otras fotos mediante un rostro.
- No obtener datos privados ni hacer scraping contra términos.
- No introducir resultados simulados, claves de pago o dependencia de servicios comerciales sin autorización.
- Comparaciones de hashes son heurísticas y nunca certifican manipulación.
