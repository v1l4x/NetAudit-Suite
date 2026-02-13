import os
import subprocess
import re
import socket
import shutil
import concurrent.futures
import json
import requests
import sys

# Intentamos importar la configuración
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

CRITERIOS = [
    ("Teles", ["samsung", "lg-tv", "webos", "bravia", "sony interactive", "allshare", "dlna", "airtunes"]),
    ("Windows", ["microsoft-ds", "msrpc", "netbios-ssn", "3389/tcp", "windows", "tpv"]),
    ("Routers", ["gateway", "router", "tp-link", "ubiquiti", "mikrotik", "asus", "technicolor", "livebox", "arcadyan"]),
    ("Camaras", ["rtsp", "554/tcp", "37777/tcp", "8000/tcp", "dahua", "hikvision", "lorex", "zenointel", "webcam"]),
    ("Moviles", ["android", "iphone", "apple-mobile", "ipad", "phone", "xiaomi"]),
]

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or "TU_TOKEN" in TELEGRAM_TOKEN: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"})
    except: pass

def enviar_archivo_telegram(ruta_archivo, caption=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or "TU_TOKEN" in TELEGRAM_TOKEN: return
    if not os.path.exists(ruta_archivo): return
    with open(ruta_archivo, 'rb') as f:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"document": f})
        except: pass

def obtener_red_automatica():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        mi_ip = s.getsockname()[0]
        s.close()
        return mi_ip, f"{mi_ip.rsplit('.', 1)[0]}.0/24"
    except: return None, None

def clasificar_dispositivo(ip, texto_nmap):
    texto = texto_nmap.lower()
    mac_info = "Desconocido"
    match = re.search(r"MAC Address: [A-F0-9:]+ \((.*?)\)", texto_nmap, re.I)
    if match: mac_info = match.group(1)
    if ip.endswith(".1") or "gateway" in texto: return "Routers", mac_info
    for cat, keys in CRITERIOS:
        if any(k in texto for k in keys) or any(k in mac_info.lower() for k in keys): return cat, mac_info
    return "Otros", mac_info

def scan_host(ip, ruta_auditoria):
    tmp_path = os.path.join(ruta_auditoria, f"tmp_{ip}")
    os.makedirs(tmp_path, exist_ok=True)
    fichero_salida = os.path.join(tmp_path, "services")
    
    try: hostname = socket.gethostbyaddr(ip)[0]
    except: hostname = "N/A"

    subprocess.run(["nmap", "-sS", "-sV", "--script=vulners", "-p-", "--open", "-n", "-Pn", "--min-rate", "5000", ip, "-oN", fichero_salida], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    vulnerable = False
    categoria, fabricante = "Otros", "Sin respuesta"
    if os.path.exists(fichero_salida):
        with open(fichero_salida, 'r', errors='ignore') as f: content = f.read()
        if "cvss" in content.lower(): vulnerable = True
        categoria, fabricante = clasificar_dispositivo(ip, content)
        final_dir = os.path.join(ruta_auditoria, categoria, ip, "nmap")
        os.makedirs(final_dir, exist_ok=True)
        shutil.move(fichero_salida, os.path.join(final_dir, "services"))
    
    if os.path.exists(tmp_path): shutil.rmtree(tmp_path)
    return {"ip": ip, "categoria": categoria, "fabricante": fabricante, "hostname": hostname, "vulnerable": vulnerable}

def main():
    console.clear()
    console.print(Panel.fit("[bold white on blue] NET-AUDIT PRO (PC VERSION) [/bold white on blue]", box=box.SQUARE))

    if not TELEGRAM_TOKEN:
        console.print("[yellow]⚠ No se detectó configuración de Telegram (config.py). Se omitirá el envío.[/yellow]")

    mi_ip, red_detectada = obtener_red_automatica()
    if not red_detectada: return console.print("[red]❌ No se detectó red.[/red]")

    console.print(f"[blue]📡 Red:[/blue] {red_detectada} | [blue]💻 IP:[/blue] {mi_ip}\n")
    nombre = console.input("[bold yellow]Nombre de la auditoría: [/bold yellow]").strip() or "Auditoria_Local"
    
    # Ruta dinámica compatible con cualquier usuario
    ruta_auditoria = os.path.join(os.path.expanduser("~"), "auditorias", nombre)
    os.makedirs(ruta_auditoria, exist_ok=True)

    with console.status("[green]Escaneando red...[/green]"):
        res = subprocess.check_output(["nmap", "-sn", "-PR", red_detectada]).decode()
        hosts = sorted(list(set([ip for ip in re.findall(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", res) if ip != mi_ip])))

    if not hosts: return console.print("[red]❌ No se encontraron hosts.[/red]")

    resultados = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console) as progress:
        task = progress.add_task("[cyan]Auditando...", total=len(hosts))
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futuros = {executor.submit(scan_host, ip, ruta_auditoria): ip for ip in hosts}
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
                progress.update(task, advance=1)

    tabla = Table(title=f"Reporte: {nombre}", box=box.ROUNDED)
    tabla.add_column("IP"); tabla.add_column("Cat"); tabla.add_column("Vuln")
    vulns = 0
    for r in sorted(resultados, key=lambda x: x['categoria']):
        if r['vulnerable']: vulns += 1
        tabla.add_row(r['ip'], r['categoria'], "[red]SI[/red]" if r['vulnerable'] else "No")
    console.print(tabla)

    with open(os.path.join(ruta_auditoria, "reporte.json"), "w") as f: json.dump(resultados, f, indent=4)
    console.save_html(os.path.join(ruta_auditoria, "reporte.html"))

    msg = f"🚀 *Auditoría PC Finalizada: {nombre}*\n📍 Red: `{red_detectada}`\n⚠️ Vulnerables: {vulns}"
    enviar_telegram(msg)
    enviar_archivo_telegram(os.path.join(ruta_auditoria, "reporte.html"), "📄 Reporte Completo")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: console.print("\n[red]Detenido por usuario.[/red]")
