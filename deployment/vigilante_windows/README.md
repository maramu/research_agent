# Vigilante externo de pciq22 (PC Windows del laboratorio)

`vigilante.ps1` corre cada 2 h en PCIQ74 (Programador de tareas, cuenta SYSTEM) y avisa por correo
(`smtp.uca.es:25`, sin autenticacion) si pciq22 deja de responder 2 comprobaciones seguidas.
No guarda secretos: el proxy de Ollama se comprueba esperando 401 sin token.

Instalacion: ver Mejoras_realizadas.md (item 87). Script en `C:\vigilante_pciq22\vigilante.ps1`,
estado en `C:\ProgramData\vigilante_pciq22\estado.json`.
