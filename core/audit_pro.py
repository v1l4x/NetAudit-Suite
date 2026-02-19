import os
import subprocess
import re
import socket
import shutil
import concurrent.futures
import json
import requests
import sys
import netifaces
import argparse
import xml.etree.ElementTree as ET

# --- CONFIGURACIÓN TELEGRAM ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.panel import Panel
from rich import box

console = Console(record=True)

# --- MODOS DE ESCANEO ---
MODOS = {
    "1": {
        "nombre": "🥷 Sigiloso ",
        "desc": "Secuencial. Disfraz DNS. Top 500 puertos. Seguro y estable.",
        "workers": 1, 
        "flags": ["-sS", "-sV", "--version-light", "--script=vulners", "--top-ports", "500", "-T3", "--source-port", "53", "--max-retries", "2", "-n", "-Pn"]
    },
    "2": {
        "nombre": "🦁 Agresivo ",
        "desc": "Paralelo. 100% Puertos. Detecta SO y Versiones. No intrusivo.",
        "workers": 10, 
        "flags": ["-sS", "-sV", "-O", "--version-intensity", "5", "--script=vulners", "-p-", "--min-rate", "1000", "-T4", "-n", "-Pn"]
    },
    "3": {
        "nombre": "💣 Ofensivo (¡CUIDADO!)",
        "desc": "🔥 EXPLOITS + FUERZA BRUTA. Verifica fallos reales. Riesgo de bloqueo.",
        "workers": 10,
        "flags": ["-sS", "-sV", "-O", "--version-intensity", "5", "--script=vulners,vuln,auth", "-p-", "--min-rate", "1000", "-T4", "-n", "-Pn"]
    }
}

CRITERIOS = [
    ("Teles", ["samsung", "lg-tv", "webos", "bravia", "sony interactive", "allshare", "dlna", "airtunes"]),
    ("Windows", ["microsoft-ds", "msrpc", "netbios-ssn", "3389/tcp", "windows", "tpv"]),
    ("Routers", ["gateway", "router", "tp-link", "ubiquiti", "mikrotik", "asus", "technicolor", "livebox", "arcadyan", "zte", "sagemcom"]),
    ("Camaras", ["rtsp", "554/tcp", "37777/tcp", "8000/tcp", "dahua", "hikvision", "lorex", "zenointel", "webcam"]),
    ("Moviles", ["android", "iphone", "apple-mobile", "ipad", "phone", "xiaomi", "galaxy"]),
]

def verificar_entorno(silencioso=False):
    herramientas = ["nmap"]
    faltantes = []
    if not silencioso: console.print("[bold cyan]🔍 Comprobando dependencias...[/bold cyan]")
    
    for tool in herramientas:
        if shutil.which(tool) is None:
            faltantes.append(tool)
            if not silencioso: console.print(f"  [red]❌ {tool} no encontrado.[/red]")
        else:
            if not silencioso: console.print(f"  [green]✅ {tool} instalado.[/green]")
    
    if faltantes: 
        console.print("[bold red]Error: Faltan herramientas. Instálalas y reinicia.[/bold red]")
        sys.exit(1)
    if not silencioso: console.print(" ") 

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
    except: pass

def enviar_archivo_telegram(ruta_archivo, caption=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not os.path.exists(ruta_archivo): return
    with open(ruta_archivo, 'rb') as f:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"document": f})
        except: pass

# --- Obtener IP sin preguntar (Para modo auto) ---
def get_network_info(interface_name):
    try:
        addrs = netifaces.ifaddresses(interface_name)
        if netifaces.AF_INET in addrs:
            ip = addrs[netifaces.AF_INET][0]['addr']
            cidr = f"{ip.rsplit('.', 1)[0]}.0/24"
            return ip, cidr
    except: pass
    return None, None

def seleccionar_interfaz():
    interfaces_validas = []
    for iface in netifaces.interfaces():
        if iface == 'lo' or iface.startswith('loop'): continue
        try:
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                ip = addrs[netifaces.AF_INET][0]['addr']
                cidr = f"{ip.rsplit('.', 1)[0]}.0/24"
                interfaces_validas.append((iface, ip, cidr))
        except: continue

    if not interfaces_validas: return None, None, None

    console.print("[bold cyan]📡 Selecciona Interfaz de Red:[/bold cyan]")
    for idx, (nombre, ip, red) in enumerate(interfaces_validas):
        color = "green" if "wlan" in nombre or "eth" in nombre or "en" in nombre else "yellow"
        console.print(f"  [{idx}] [bold {color}]{nombre}[/bold {color}] \tIP: {ip} \tRed: {red}")

    while True:
        eleccion = console.input("\n[bold white]> [/bold white]")
        if eleccion.isdigit() and 0 <= int(eleccion) < len(interfaces_validas):
            interfaz_elegida = interfaces_validas[int(eleccion)]
            return interfaz_elegida[0], interfaz_elegida[1], interfaz_elegida[2]
        console.print("[red]Opción inválida.[/red]")

def elegir_modo():
    console.print("\n[bold cyan]🎭 Selecciona Nivel de Auditoría:[/bold cyan]")
    for key, data in MODOS.items():
        if key == "1": color = "green"
        elif key == "2": color = "yellow"
        else: color = "red"
        console.print(f"  [{key}] [bold {color}]{data['nombre']}[/bold {color}] - [dim]{data['desc']}[/dim]")
    
    while True:
        opcion = console.input("\n[bold white]> [/bold white]")
        if opcion in MODOS: return MODOS[opcion]
        console.print("[red]Opción inválida.[/red]")

def sanitizar_nombre(nombre):
    limpio = re.sub(r'[^\w\-\_]', '_', nombre)
    return limpio if limpio else "Auditoria_Auto"

def clasificar_dispositivo(ip, texto_nmap):
    texto = texto_nmap.lower()
    mac_info = "Desconocido"
    match = re.search(r"MAC Address: [A-F0-9:]+ \((.*?)\)", texto_nmap, re.I)
    if match: mac_info = match.group(1)
    
    if ip.endswith(".1") or "gateway" in texto: return "Routers", mac_info
    for cat, keys in CRITERIOS:
        if any(k in texto for k in keys) or any(k in mac_info.lower() for k in keys): return cat, mac_info
    return "Otros", mac_info

def analizar_xml_nmap(archivo_xml):
    vulns = []
    max_cvss = 0.0
    os_match = "N/A"
    try:
        tree = ET.parse(archivo_xml)
        root = tree.getroot()
        for os_el in root.findall(".//osmatch"):
            os_match = os_el.get('name', 'N/A')
            break 
        for host in root.findall('host'):
            for port in host.findall('.//port'):
                port_id = port.get('portid')
                service = port.find('service')
                prod = service.get('product', '') if service is not None else ''
                for script in port.findall('script'):
                    if script.get('id') in ['vulners'] or 'vuln' in script.get('id'):
                        output = script.get('output', '')
                        matches = re.findall(r'(CVE-\d{4}-\d+)\s+(\d+\.\d+)', output)
                        for cve, score in matches:
                            score_float = float(score)
                            if score_float > max_cvss: max_cvss = score_float
                            vulns.append({"port": port_id, "product": prod, "cve": cve, "cvss": score_float})
                        
                        if "VULNERABLE" in output or "State: VULNERABLE" in output:
                            if max_cvss < 9.0: max_cvss = 9.0
                            vulns.append({"port": port_id, "product": prod, "cve": "EXPLOIT-CONFIRMADO", "cvss": 9.8})
    except Exception: pass 
    
    severidad = "INFO"
    color = "green"
    if max_cvss >= 9.0: severidad = "CRÍTICA"; color = "red"
    elif max_cvss >= 7.0: severidad = "ALTA"; color = "orange3"
    elif max_cvss >= 4.0: severidad = "MEDIA"; color = "yellow"
    return vulns, max_cvss, severidad, color, os_match

def scan_host(ip, ruta_auditoria, interfaz, flags_modo):
    tmp_path = os.path.join(ruta_auditoria, f"tmp_{ip}")
    os.makedirs(tmp_path, exist_ok=True)
    fichero_xml = os.path.join(tmp_path, "scan.xml")
    fichero_txt = os.path.join(tmp_path, "services")
    
    try: hostname = socket.gethostbyaddr(ip)[0]
    except: hostname = "N/A"

    subprocess.run(["nmap", "-e", interfaz] + flags_modo + [ip, "-oX", fichero_xml, "-oN", fichero_txt], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    vulnerabilidades = []
    max_cvss = 0.0
    severidad = "SAFE"
    color_risk = "green"
    os_detected = "Desc."
    categoria, fabricante = "Otros", "Sin respuesta"

    if os.path.exists(fichero_xml):
        vulnerabilidades, max_cvss, severidad, color_risk, os_xml = analizar_xml_nmap(fichero_xml)
        if os_xml != "N/A": os_detected = os_xml
        if os.path.exists(fichero_txt):
            with open(fichero_txt, 'r', errors='ignore') as f: content = f.read()
            categoria, fabricante = clasificar_dispositivo(ip, content)
        
        final_dir = os.path.join(ruta_auditoria, categoria, ip, "nmap")
        os.makedirs(final_dir, exist_ok=True)
        shutil.move(fichero_xml, os.path.join(final_dir, "scan.xml"))
        if os.path.exists(fichero_txt): shutil.move(fichero_txt, os.path.join(final_dir, "services"))

    if os.path.exists(tmp_path): shutil.rmtree(tmp_path)
    
    return {
        "ip": ip, "categoria": categoria, "fabricante": fabricante, "hostname": hostname, "os": os_detected,
        "vulns": vulnerabilidades, "max_cvss": max_cvss, "severidad": severidad, "color": color_risk
    }

def generar_html_profesional(ruta, resultados, nombre):
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reporte: {nombre}</title>
        <style>
            body {{ font-family: 'Segoe UI', Roboto, sans-serif; background: #f4f4f4; padding: 10px; margin: 0; }}
            .card {{ background: white; padding: 15px; margin-bottom: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; font-size: 1.5rem; }}
            h3 {{ font-size: 1.1rem; margin-top: 0; display: flex; align-items: center; gap: 10px; }}
            table {{ width: 100%; border-collapse: collapse; min-width: 500px; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; font-size: 0.9rem; }}
            th {{ background-color: #2c3e50; color: white; }}
            .table-wrapper {{ overflow-x: auto; }}
            .badge {{ padding: 4px 8px; border-radius: 4px; color: white; font-weight: bold; font-size: 0.75em; }}
            .CRÍTICA {{ background-color: #e74c3c; }} .ALTA {{ background-color: #e67e22; }}
            .MEDIA {{ background-color: #f1c40f; color: black; }} .INFO, .SAFE {{ background-color: #2ecc71; }}
        </style>
    </head>
    <body>
        <h1>🛡️ Reporte Técnico: {nombre}</h1>
    """
    
    for r in sorted(resultados, key=lambda x: x['max_cvss'], reverse=True):
        if not r['vulns'] and r['severidad'] == 'SAFE': continue 
        icono = "🟢"
        if r['severidad'] == "CRÍTICA": icono = "🔴"
        elif r['severidad'] == "ALTA": icono = "🟠"
        elif r['severidad'] == "MEDIA": icono = "🟡"

        html += f"""
        <div class="card">
            <h3>{icono} {r['ip']} <span class="badge {r['severidad']}">{r['severidad']}</span></h3>
            <p><b>Host:</b> {r['hostname']} | <b>Dispositivo:</b> {r['categoria']} ({r['fabricante']}) | <b>OS:</b> {r['os']}</p>
            <div class="table-wrapper"><table>
                <tr><th>Puerto</th><th>Servicio</th><th>CVE / Exploit</th><th>CVSS</th><th>Link</th></tr>
        """
        if not r['vulns']: html += "<tr><td colspan='5'><i>Sin vulnerabilidades conocidas.</i></td></tr>"
        else:
            for v in r['vulns']:
                if "EXPLOIT" in v['cve']:
                    link = "#"
                    cve_display = "<span style='color:red'>⚠️ EXPLOIT CONFIRMADO</span>"
                else:
                    link = f"https://nvd.nist.gov/vuln/detail/{v['cve']}"
                    cve_display = f"<b>{v['cve']}</b>"
                html += f"<tr><td>{v['port']}</td><td>{v['product']}</td><td>{cve_display}</td><td>{v['cvss']}</td><td><a href='{link}' target='_blank'>Detalle</a></td></tr>"
        html += "</table></div></div>"
    html += "</body></html>"
    with open(ruta, "w", encoding='utf-8') as f: f.write(html)

def mostrar_banner():
    console.print(Panel.fit("[bold white on blue] NET-AUDIT PRO v2.0 [/bold white on blue]", box=box.SQUARE))

def main():
    # --- PARSEO DE ARGUMENTOS ---
    parser = argparse.ArgumentParser(description='Net-Audit Pro - Herramienta de Auditoría')
    parser.add_argument('-i', '--interface', help='Interfaz de red (ej: wlan0)')
    parser.add_argument('-m', '--mode', choices=['1', '2', '3'], help='1=Sigilo, 2=Agresivo, 3=Ofensivo')
    parser.add_argument('-n', '--name', help='Nombre de la auditoría')
    args = parser.parse_args()

    # --- MODO AUTOMÁTICO (CLI) ---
    if args.interface and args.mode and args.name:
        console.print(f"[bold green]🚀 Iniciando Modo Automático: {args.name}[/bold green]")
        verificar_entorno(silencioso=True)
        
        mi_ip, red_detectada = get_network_info(args.interface)
        if not mi_ip:
            console.print(f"[red]❌ Error: Interfaz {args.interface} no válida.[/red]")
            sys.exit(1)
            
        interfaz = args.interface
        modo = MODOS[args.mode]
        nombre = sanitizar_nombre(args.name)

    # --- MODO INTERACTIVO (MENÚS) ---
    else:
        console.clear()
        mostrar_banner()
        verificar_entorno()
        
        interfaz, mi_ip, red_detectada = seleccionar_interfaz()
        if not interfaz: return console.print("[red]❌ Error: No se seleccionó interfaz.[/red]")
        
        console.clear()
        mostrar_banner()
        console.print(f"[green]✔ Interfaz Activa:[/green] [bold cyan]{interfaz}[/bold cyan] ({mi_ip}) | Red: {red_detectada}")
        modo = elegir_modo()
        nombre = sanitizar_nombre(console.input("\n[bold yellow]Nombre de la auditoría: [/bold yellow]").strip())

        # Resumen visual (Solo en modo interactivo)
        console.clear()
        mostrar_banner()
        resumen = Table(show_header=False, box=box.SIMPLE)
        resumen.add_row("📂 Nombre", nombre)
        resumen.add_row("🎯 Objetivo", red_detectada)
        resumen.add_row("📡 Interfaz", interfaz)
        resumen.add_row("🎭 Estrategia", modo['nombre'])
        console.print(Panel(resumen, title="[bold]Configuración de Auditoría[/bold]", border_style="blue"))

    # --- EJECUCIÓN (COMÚN) ---
    ruta_auditoria = os.path.join(os.path.expanduser("~"), "auditorias", nombre)
    os.makedirs(ruta_auditoria, exist_ok=True)

    with console.status(f"[green]Descubriendo hosts en {red_detectada}...[/green]"):
        try:
            res = subprocess.check_output(["nmap", "-e", interfaz, "-sn", "-PR", red_detectada]).decode()
            hosts = sorted(list(set([ip for ip in re.findall(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", res) if ip != mi_ip])))
        except: return console.print("[red]Error descubrimiento.[/red]")

    if not hosts: return console.print("[red]❌ No hosts encontrados.[/red]")

    resultados = []
    mensaje = f"[cyan]Analizando {len(hosts)} dispositivos ({modo['nombre']})..."
    
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console) as progress:
        task = progress.add_task(mensaje, total=len(hosts))
        with concurrent.futures.ThreadPoolExecutor(max_workers=modo['workers']) as executor:
            futuros = {executor.submit(scan_host, ip, ruta_auditoria, interfaz, modo['flags']): ip for ip in hosts}
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
                progress.update(task, advance=1)

    resultados.sort(key=lambda x: x['max_cvss'], reverse=True)

    tabla = Table(title=f"Reporte Final: {nombre}", box=box.ROUNDED)
    tabla.add_column("IP", style="cyan"); tabla.add_column("Dispositivo"); tabla.add_column("Riesgo", justify="center")
    
    vulns_totales = 0
    for r in resultados:
        if r['vulns']: vulns_totales += len(r['vulns'])
        style_risk = r['color']
        tabla.add_row(r['ip'], r['categoria'], f"[{style_risk}]{r['severidad']} ({r['max_cvss']})[/{style_risk}]")
    console.print(tabla)

    ruta_html = os.path.join(ruta_auditoria, "reporte.html")
    generar_html_profesional(ruta_html, resultados, nombre)
    with open(os.path.join(ruta_auditoria, "reporte.json"), "w") as f: json.dump(resultados, f, indent=4)

    severidad_maxima = resultados[0]['severidad'] if resultados else 'N/A'
    msg = f"🛡️ *NetAudit Finalizado*\n📂 `{nombre}`\n🎭 `{modo['nombre']}`\n🦠 CVEs: {vulns_totales}\n🔥 Riesgo: {severidad_maxima}"
    enviar_telegram(msg)
    enviar_archivo_telegram(ruta_html, "📄 Reporte CVE")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: console.print("\n[red]Salida forzada.[/red]")
