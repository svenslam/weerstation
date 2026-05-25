import time
import os
import json
import subprocess
import uuid
from datetime import datetime

# ==============================================================================
# CONFIGURATIE VOOR JOUW WEERSTATION
# ==============================================================================
# Het bestand waarin de meetgegevens worden opgeslagen in je GitHub repository.
# De React app op GitHub Pages leest automatisch dit bestand uit om de grafieken te tonen!
JSON_REL_PATH = "public/data.json"
MAX_HISTORY_ITEMS = 200      # Maximaal aantal metingen om het bestand klein en snel te houden
MEASUREMENT_INTERVAL = 600   # Aantal seconden tussen metingen (600 = elke 10 minuten)

# Probeer de benodigde Adafruit sensor libraries te laden
try:
    import board
    import busio
    import adafruit_ahtx0
    print("✓ Hardware libraries succesvol geladen.")
except ImportError:
    print("⚠️  Hardware libraries niet gevonden. Gaat over in SIMULATIEMODUS (voor droogtesten op PC of Mac).")
    board = None

def get_sensor_reading():
    """
    Leest de temperatuur en luchtvochtigheid uit van de DHT20 sensor.
    Mocht de sensor niet aangesloten zijn of draait het script op een testomgeving,
    dan worden er realistische testgegevens gegenereerd.
    """
    if board is None:
        # Simulatie voor PC/Mac of als hardware ontbreekt
        import random
        temp = 18.0 + random.uniform(-1.5, 3.5)
        hum = 50.0 + random.uniform(-5.0, 10.0)
        return round(temp, 1), round(hum, 1), "virtual"
    
    try:
        # Initialiseer I2C bus en DHT20/AHT20 Sensor
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_ahtx0.AHTx0(i2c)
        temp = sensor.temperature
        hum = sensor.relative_humidity
        return round(temp, 1), round(hum, 1), "physical"
    except Exception as e:
        print(f"❌ Fout bij uitlezen sensor: {e}")
        print("We vallen tijdelijk terug op simulatie-meting.")
        import random
        temp = 19.0 + random.uniform(-1.0, 2.0)
        hum = 52.0 + random.uniform(-3.0, 3.0)
        return round(temp, 1), round(hum, 1), "virtual"

def update_json_file(temp, hum, source):
    """
    Laadt de bestaande data.json file, voegt de nieuwe meting toe en slaat het weer op.
    Borgt dat het bestand niet onbeperkt groeit via MAX_HISTORY_ITEMS.
    Slaat de data op in zowel public/data.json als docs/data.json zodat het live werkt.
    """
    # Probeer te laden van docs/data.json (meest recent) of public/data.json of data.json
    paths_to_check = ["docs/data.json", "public/data.json", "data.json"]
    data = {"history": []}
    
    for path in paths_to_check:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        parsed = json.loads(content)
                        if "history" in parsed and isinstance(parsed["history"], list):
                            data = parsed
                            print(f"📖 Succesvol bestaande geschiedenis geladen van {path}")
                            break
            except Exception as e:
                print(f"⚠️ Kon {path} niet lezen: {e}")

    # Bereid nieuwe meting voor
    new_entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), # ISO-8601 UTC formaat
        "temperature": temp,
        "humidity": hum,
        "source": source
    }

    # Voeg toe aan geschiedenis
    data["history"].append(new_entry)

    # Beperk grootte van de lijst
    if len(data["history"]) > MAX_HISTORY_ITEMS:
        data["history"] = data["history"][-MAX_HISTORY_ITEMS:]

    # Sla op in beide mappen om lokale builds en GitHub Pages direct synchroon te houden
    saved_paths = []
    for path in ["public/data.json", "docs/data.json"]:
        try:
            dir_name = os.path.dirname(path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"💾 JSON bijgewerkt ({path}): {temp}°C | {hum}%")
            saved_paths.append(path)
        except Exception as e:
            print(f"❌ Fout bij opslaan van JSON naar {path}: {e}")
            
    return saved_paths

def push_to_github(file_paths):
    """
    Voert Git commando's uit om de data bestanden te committen en pushen naar GitHub.
    Dit zorgt ervoor dat GitHub Pages direct wordt bijgewerkt!
    """
    if not file_paths:
        return
    try:
        # Voeg alle bijgewerkte bestanden toe aan Git staging
        for path in file_paths:
            subprocess.run(["git", "add", path], check=True, stdout=subprocess.DEVNULL)
        
        # Bepaal commitbericht met data
        commit_msg = f"Weer update: Temp {datetime.now().strftime('%H:%M:%S')} is {get_current_temp_string(file_paths[0])}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, stdout=subprocess.DEVNULL)
        
        # Push naar GitHub
        print("🚀 Updaten op GitHub (git push)...")
        result = subprocess.run(["git", "push"], capture_output=True, text=True, check=True)
        print("✓ Succesvol gepusht naar GitHub!")
    except subprocess.CalledProcessError as e:
        stdout_str = e.stdout if isinstance(getattr(e, "stdout", None), str) else ""
        stderr_str = e.stderr if isinstance(getattr(e, "stderr", None), str) else ""
        # Als er geen wijzigingen waren om te committen (bijvoorbeeld identieke waarden, hoewel onwaarschijnlijk met timestamps)
        if "nothing to commit" in stdout_str or "nothing to commit" in stderr_str:
            print("ℹ️ Geen nieuwe wijzigingen om te committen.")
        else:
            print(f"❌ Git actie mislukt: {e}")
            # Toon foutdetails van Git indien beschikbaar
            git_err = stderr_str or stdout_str
            if git_err:
                print(f"Foutmelding van Git:\n{git_err}")
            print("\n💡 TIP: Zorg ervoor dat Git is geconfigureerd op de Pi en dat je een SSH-key of Personal Access Token (PAT) hebt ingesteld.")

def get_current_temp_string(file_path):
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            if data["history"]:
                latest = data["history"][-1]
                return f"{latest['temperature']}°C, {latest['humidity']}%"
    except:
        pass
    return "meting"

# ==============================================================================
# MAIN ENGINE
# ==============================================================================
if __name__ == "__main__":
    print("======================================================================")
    print("  🌦️  SENSORLINK - GITHUB PAGES AUTO-LOGGER (DHT20 & PI3B) 🌦️")
    print("======================================================================")
    print(f"Elke {MEASUREMENT_INTERVAL} seconden wordt een meting opgeslagen in public/data.json & docs/data.json")
    print("en direct doorgezet naar GitHub.")
    print("Druk op Ctrl+C om te stoppen.\n")

    # Controleer of we in een Git repo zitten
    if not os.path.exists(".git"):
         print("⚠️  Let op: Geen .git folder gedetecteerd. Zorg ervoor dat dit script ")
         print("draait vanuit de hoofdmap van jouw gekloonde GitHub repository!")
         print("----------------------------------------------------------------------")

    try:
        while True:
            # 1. Haal meting op
            temp, hum, source = get_sensor_reading()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sensor uitgelezen.")
            
            # 2. Werk bestand bij
            file_paths = update_json_file(temp, hum, source)
            
            # 3. Push naar GitHub
            if file_paths:
                push_to_github(file_paths)
            
            # 4. Slaap tot de volgende meting
            print(f"Slaapstand actief voor {MEASUREMENT_INTERVAL} seconden...\n")
            time.sleep(MEASUREMENT_INTERVAL)
            
    except KeyboardInterrupt:
        print("\nProgramma handmatig gestopt. Tot ziens!")
