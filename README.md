# 🛡️ NetAudit-Suite

> **Suite de auditoría de red automatizada y modular.**

NetAudit-Suite es un conjunto de herramientas diseñadas para **descubrir activos**, **identificar fabricantes** y **detectar vulnerabilidades (CVEs)** en redes locales. 

Incluye versiones optimizadas para hardware de alto rendimiento (PC) y dispositivos IoT de bajo consumo (Raspberry Pi Zero), con integración directa a **Telegram** para reportes en tiempo real.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20RPi-orange)

## 🚀 Módulos Incluidos

| Módulo | Ruta | Descripción | Hardware Recomendado |
| :--- | :--- | :--- | :--- |
| **Core Pro** | `core/audit_pro.py` | Escaneo multi-hilo agresivo. | PC / Laptop / RPi 4 |
| **Lite IoT** | `lite/audit_pi.py` | Optimizado para bajo consumo y selección de interfaz. | Raspberry Pi Zero / Zero 2W |

## 📦 Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/v1l4x/NetAudit-Suite.git](https://github.com/v1l4x/NetAudit-Suite.git)
   cd NetAudit-Suite
   ```

2. **Instalar dependencias:**
   ```bash
    pip3 install -r requirements.txt
    sudo apt install nmap
   ```
3. **Configuración (Opcional para Telegram):**
   ```bash
    mv config.py.example config.py
    nano config.py
    # Pega tu Token y Chat ID dentro
   ```

## 🎮 Uso

### Modo PC (Potencia Máxima):
```bash
sudo python3 core/audit_pro.py
```
### Modo Raspberry Pi zero 2w (Portable):
```bash
sudo python3 lite/audit_pi.py
```
---

**Disclaimer:** Herramienta creada con fines educativos y de auditoría ética. El autor no se hace responsable del mal uso.
