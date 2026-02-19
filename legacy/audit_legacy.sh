#!/bin/bash

# ==============================================================================
#  NET-AUDIT LEGACY (BASH v1.6)
#  Descripción: Versión ligera. Auto-detecta la red y arregla los colores.
# ==============================================================================

# --- COLORES (ARREGLADOS) ---
# Usamos \033 en lugar de \133 para evitar el fallo visual
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- VARIABLES GLOBALES ---
BASE_DIR="$HOME/auditorias"

# --- TRAP CTRL+C (SALIDA LIMPIA) ---
function ctrl_c(){
    echo -e "\n${RED}[!] Interrupción detectada. Saliendo...${NC}"
    tput cnorm
    exit 1
}
trap ctrl_c INT

# --- BARRA DE PROGRESO ---
function progress_bar(){
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    tput civis # Ocultar cursor
    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf " [%c] " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
    tput cnorm # Mostrar cursor
}

# --- BANNER ---
function banner(){
    clear
    echo -e "${BLUE}==============================================${NC}"
    echo -e "      ${YELLOW}NET-AUDIT LEGACY (BASH v1.6)${NC}"
    echo -e "${BLUE}==============================================${NC}"
}

# --- AUTO-DESCUBRIMIENTO DE RED ---
function get_network_info(){
    echo -e "\n${CYAN}[?] Detectando configuración de red...${NC}"
    
    # Truco para obtener la IP que tiene salida a internet (la principal)
    # Esto funciona en casi cualquier Linux moderno
    MY_IP=$(ip route get 8.8.8.8 | sed -n 's/.*src \([^\ ]*\).*/\1/p')
    INTERFACE=$(ip route get 8.8.8.8 | sed -n 's/.*dev \([^\ ]*\).*/\1/p')
    
    if [ -z "$MY_IP" ]; then
        echo -e "${RED}[!] Error: No tienes conexión a la red.${NC}"
        exit 1
    fi

    # Calculamos el rango /24 (Asumimos máscara estándar 255.255.255.0)
    # Ejemplo: Si IP es 192.168.1.33 -> Rango es 192.168.1.0/24
    SUBNET=$(echo "$MY_IP" | cut -d "." -f 1,2,3).0/24

    echo -e "${GREEN}✔ Interfaz Detectada:${NC} ${YELLOW}$INTERFACE${NC}"
    echo -e "${GREEN}✔ Tu IP Local:${NC}        ${YELLOW}$MY_IP${NC}"
    echo -e "${GREEN}✔ Rango Objetivo:${NC}     ${YELLOW}$SUBNET${NC}"
}

# --- ESCANEO DE HOSTS ---
function discover_hosts(){
    echo -ne "\n${YELLOW}[?]${NC} Buscando dispositivos en $SUBNET..."
    
    # Escaneo Ping Sweep silencioso
    nmap -sn "$SUBNET" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | grep -v "$MY_IP" > hosts.txt
    
    TOTAL_HOSTS=$(wc -l < hosts.txt)
    
    if [ "$TOTAL_HOSTS" -eq 0 ]; then
        echo -e " ${RED}FAIL${NC}"
        echo -e "${RED}[!] No se encontraron otros dispositivos en la red.${NC}"
        rm hosts.txt
        exit 0
    else
        echo -e " ${GREEN}OK${NC} ($TOTAL_HOSTS encontrados)"
    fi
}

# --- ESCANEO DETALLADO ---
function full_scan(){
    echo -e "\n${BLUE}[+]${NC} Iniciando auditoría profunda...\n"

    while read -r ip; do
        echo -ne "  ${CYAN}➜${NC} Auditando ${YELLOW}$ip${NC}..."
        
        # Crear carpeta
        mkdir -p "$WORKDIR/$ip"
        
        # Escaneo optimizado (Similar al modo Agresivo de Python)
        # -sV: Versiones
        # -O: Sistema Operativo
        # --min-rate 1000: Rápido
        nmap -sS -sV -O --version-light --min-rate 1000 -p- --open -n -Pn "$ip" -oN "$WORKDIR/$ip/scan.txt" > /dev/null 2>&1 &
        
        PID=$!
        progress_bar $PID
        
        if [ $? -eq 0 ]; then
            echo -e " ${GREEN}✔ Hecho${NC}"
        else
            echo -e " ${RED}✘ Error${NC}"
        fi
        
    done < hosts.txt
    
    rm hosts.txt
}

# --- BLOQUE PRINCIPAL (MAIN) ---
banner

# Verificar Dependencias
if ! command -v nmap &> /dev/null; then
    echo -e "${RED}[!] Error: Nmap no está instalado.${NC}"
    exit 1
fi

# 1. Obtener datos automáticamente
get_network_info

# 2. Pedir nombre
echo -e ""
echo -ne "${YELLOW}Nombre de la auditoría: ${NC}"
read AUDIT_NAME

# Si el usuario no escribe nada, ponemos un nombre por defecto
if [ -z "$AUDIT_NAME" ]; then
    AUDIT_NAME="Auditoria_Auto"
fi

# Limpiar nombre (espacios -> guiones)
AUDIT_NAME=${AUDIT_NAME// /_}
WORKDIR="$BASE_DIR/$AUDIT_NAME"

mkdir -p "$WORKDIR"
cd "$WORKDIR" || exit

# 3. Ejecutar
discover_hosts
full_scan

# 4. Finalizar
echo -e "\n${BLUE}==============================================${NC}"
echo -e "${GREEN}✔ Auditoría finalizada.${NC}"
echo -e "📂 Reportes guardados en: ${CYAN}$WORKDIR${NC}"
echo -e "${BLUE}==============================================${NC}\n"
