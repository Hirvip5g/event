import base64
import json
import requests

# Endpoints oficiales extraídos de la aplicación
EVENTOS_JSON_URL = "https://shplus.240025.xyz/application-webview/eventos.json"
TOKEN_ENDPOINT = "https://shplus.240025.xyz/application-webview/vixplus/json/api/token.php"
LURA_PLAY_URL = "https://nxs.mp.lura.live/v1/play/{}"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"

def build_info_base64_url(video_id: str) -> str:
    """Genera los macros y la codificación Base64 URL-Safe requerida por Lura (igual que en la app)."""
    macros = {
        "dfp_server_url": "https://pubads.g.doubleclick.net/gampad/ads?",
        "dfp_env": "vp",
        "dfp_impl": "s",
        "dfp_tfcd": "0",
        "dfp_npa": "0",
        "dfp_gdfp_req": "1",
        "dfp_unviewed_position_start": "1",
        "dfp_vad_type": "linear",
        "dfp_vpa": "1",
        "dfp_vconp": "1",
        "dfp_ss_req": "1",
        "dfp_vpi": "1",
        "dfp_scor": "4241",
        "dfp_sid": "337e0553-2a5f-4e09-a7c6-3a96abfaff9a",
        "dfp_ppid": "fcdb7020-a980-364a-4265-95b522646dab",
        "dfp_ad_rule": "1",
        "dfp_vpmute": "0",
        "dfp_vpos": "midroll",
        "dfp_video_language": "es",
        "dfp_vid": video_id,
        "LURA_PAL_NONCE": "",
        "LURA_CORRELATOR": "170731108"
    }

    config_json = {
        "ads": {"macros": macros, "serverSide": {"mode": "serverside", "provider": "lura"}},
        "cast": {"airplay": {"enabled": False}, "chromecast": {"enabled": False}},
        "controls": {"enabled": True, "theme": "Default", "autoplay": True, "muted": False, "loop": False, "volume": 1, "platform": "tv", "layout": "default"},
        "content": {"additionalInformation": {"shouldDisplayUpgradeButton": False}},
        "plugins": {
            "pal": {"enabled": True, "descriptionUrl": "https://www.vix.com/"},
            "conviva": {
                "enabled": True,
                "viewerId": "337e0553-2a5f-4e09-a7c6-3a96abfaff9a",
                "customerKey": "a7f3b924880f9fdb4be55df333ff9cb5d8408d44",
                "version": "4",
                "logLevel": 0,
                "contentInfo": {
                    "c3.cm.genre": "NA", "c3.cm.genreList": "NA", "c3.cm.showTitle": "NA",
                    "c3.cm.seriesName": "NA", "c3.cm.seasonNumber": "NA", "c3.cm.episodeNumber": "NA",
                    "content_group": "promo", "sender_device_app_version": "tvapp/v1.53.0-rc.4",
                    "series_id": "NA", "sports_event_id": "NA", "streamUrl": "https://web-tv.stg.vix.tv/canales",
                    "user_type": "viewer", "vod_type": "NA"
                }
            }
        }
    }

    raw_bytes = json.dumps(config_json, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b'=').decode('utf-8')

def extraer_transmision(video_id: str, session: requests.Session, global_auth: str):
    """Extrae el enlace MPD y la licencia de un videoId específico."""
    try:
        # 1. Obtener token de video para el ID
        video_token_url = f"https://web.per.vix.tv/api/video/token?videoId={video_id}"
        headers = {
            "authorization": f"Bearer {global_auth}",
            "accept": "*/*",
            "origin": "https://web.per.vix.tv",
            "referer": "https://web.per.vix.tv/es-es/canales",
            "x-player-version": "AnvatoPlayer",
            "x-video-pod-serve": "ULTRON",
            "x-video-type": "Livestream",
            "user-agent": DEFAULT_USER_AGENT
        }
        
        v_resp = session.get(video_token_url, headers=headers, timeout=10)
        v_data = v_resp.json()
        video_token = v_data.get("token")
        
        if not video_token:
            return None, None
            
        # 2. Combinar token con la info de macros
        combined_token = f"{video_token}.{build_info_base64_url(video_id)}"
        
        # 3. Consultar Lura para el manifiesto de video
        lura_url = LURA_PLAY_URL.format(video_id)
        lura_headers = {
            "accept": "*/*",
            "origin": "https://web-tv.stg.vix.tv",
            "referer": "https://web-tv.stg.vix.tv/",
            "user-agent": DEFAULT_USER_AGENT
        }
        lura_resp = session.post(lura_url, data={"token": combined_token}, headers=lura_headers, timeout=10)
        lura_data = lura_resp.json()
        
        # 4. Encontrar el .mpd y licenseUrl
        for item in lura_data.get("content", {}).get("media", []):
            url = item.get("url", "")
            lic = item.get("licenseUrl", "")
            if ".mpd" in url:
                return url, lic
                
    except Exception as e:
        pass
    return None, None

def main():
    session = requests.Session()
    # Usar un User-Agent global para prevenir bloqueos por parte del servidor web
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    
    print("[*] Descargando cartelera de eventos...")
    try:
        resp = session.get(EVENTOS_JSON_URL, timeout=10)
        print(f"[*] Código HTTP de respuesta: {resp.status_code}")
        eventos = resp.json()
    except requests.exceptions.JSONDecodeError:
        print("[-] El servidor respondió, pero el contenido NO es un JSON válido.")
        print("[-] Contenido recibido:")
        print(resp.text[:500])
        return
    except Exception as e:
        print(f"[-] Error al descargar el JSON de eventos: {e}")
        return

    print(f"[*] Se encontraron {len(eventos)} eventos en la cartelera.")
    
    print("[*] Obteniendo credenciales globales de acceso (Token)...")
    try:
        token_resp = session.get(TOKEN_ENDPOINT, timeout=10)
        global_auth = token_resp.json().get("authorization")
        if not global_auth:
            print("[-] No se pudo obtener el parámetro 'authorization'.")
            return
    except Exception as e:
        print(f"[-] Error obteniendo el token principal: {e}")
        return

    # Procesar cada evento de la lista
    for evento in eventos:
        titulo = evento.get("title")
        desc = evento.get("desc")
        url_evento = evento.get("url", "")
        
        # Extraer el 'id' desde la URL del evento usando un pequeño truco de parsing
        video_id = None
        if "id=" in url_evento:
            video_id = url_evento.split("id=")[1].split("&")[0]
        elif "NoKey" in evento:
            video_id = evento["NoKey"]
            
        print(f"\n--------------------------------------------------")
        print(f"Evento: {titulo} ({desc})")
        print(f"Video ID: {video_id or 'No disponible'}")
        
        if video_id:
            mpd, license_url = extraer_transmision(video_id, session, global_auth)
            if mpd:
                print(f" > [✔] MPD: {mpd}")
                print(f" > [✔] Licencia: {license_url}")
            else:
                print(" > [✘] No se pudo extraer la transmisión (puede que el evento haya finalizado o requiera otro flujo).")
        else:
            print(" > [✘] No se encontró un ID válido para procesar.")

if __name__ == "__main__":
    main()