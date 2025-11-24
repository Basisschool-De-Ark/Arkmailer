from dotenv import load_dotenv
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient import errors
from googleapiclient.errors import HttpError # Specifiekere import
import json
import os
import requests
from datetime import date, timedelta, datetime
from typing import Dict, Set, List
import logging
import base64
from email.mime.text import MIMEText
import time
import sys # <-- Nieuwe import voor veilige exit

# --- LOGGING & INIT ---
# Gebruik van een roterende logfile is aan te raden voor productie.
logging.basicConfig(filename="ArkMailer.log", level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                     encoding='utf-8') # <-- Toegevoegde encoding fix
load_dotenv()

# --- VEILIGE JSON LADER FUNCTIE ---
def safe_json_load(env_var_name: str, default_value):
    """Laadt JSON uit .env variabele met foutafhandeling en controle op leegte."""
    json_string = os.getenv(env_var_name)
    if not json_string:
        # Geen fout als de variabele leeg is, retourneer de standaardwaarde
        return default_value
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        # Kritieke fout bij ongeldige JSON-syntax
        logging.error(f"FATALE FOUT: Fout bij het laden van JSON uit .env voor '{env_var_name}': {e}. Controleer de quotes.")
        sys.exit(1) # Stop het script bij een fatale JSON-fout

# --- GLOBALE VARIABELEN UIT .ENV (NU ROBUUSTER) ---
try:
    # Directory Service (Vereist)
    CREDENTIALS = safe_json_load("CREDENTIALS", {})
    SCOPES = safe_json_load("SCOPES", [])

    # Gmail Service (Optioneel/Rapportage)
    SCOPES_MAIL = safe_json_load("SCOPES_MAIL", [])
    CREDENTIALS_MAIL = safe_json_load("CREDENTIALS_MAIL", {})
    
    # Overige variabelen
    INSTELLINGSNUMBERS = os.getenv("INSTELLINGSNUMMERS")
    WISA_URL = os.getenv("WISA_URL")
    USERNAME_ENV = os.getenv("USERNAME_ENV")
    PASSWORD_ENV = os.getenv("PASSWORD_ENV")
    DOMAIN_NAME = os.getenv("DOMAIN")
    SENDER_EMAIL = os.getenv('SENDER_EMAIL_LOGIN')
    RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL')
    
except Exception as e:
    # Vangt fouten op zoals FileNotFoundError als safe_json_load dit zou aanroepen, of andere globale fouten
    logging.critical(f"FATALE OPSTARTFOUT tijdens initialisatie: {e}")
    sys.exit(1)

# --- TEST INSTELLING ---
# ... (rest van de variabelen)

# ... (rest van de functies: get_wisa_reference_date, load_json_data, generate_google_group_address, group_mailaddresses_by_json)
# ... (rest van de functies: get_google_groups, get_group_members, normalize_gmail_address, add_member_to_group)
# ... (rest van de functies: remove_member_from_group, ensure_group_exists, compare_and_sync_maps)


# --- AUTHENTICATIE FUNCTIES ---
def authenticate(token_file: str, scopes: List[str], client_config: Dict) -> (Credentials | None):
    """Algemene functie voor het authenticeren van Google API's."""
    # Controleer of de benodigde configuratie is geleverd
    if not client_config:
        logging.warning(f"Authenticatie afgebroken: Geen client_config geleverd voor {token_file}.")
        return None
        
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        
    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            creds = flow.run_local_server(port=0)
            
        with open(token_file, "w") as token:
            token.write(creds.to_json())
            
    return creds

def create_directory_service():
    """Creëert de Google Directory service."""
    # We laten het script crashen als de DIRECTORY credentials missen, want dit is essentieel.
    if not CREDENTIALS or not SCOPES:
        raise Exception("DIRECTORY CREDENTIALS en/of SCOPES ontbreken. Kan niet synchroniseren.")
        
    creds = authenticate("tokendir.json", SCOPES, CREDENTIALS)
    if creds is None:
         raise Exception("Authenticatie voor Directory Service mislukt.")
         
    return build('admin', 'directory_v1', credentials=creds)

def create_gmail_service():
    """Creëert de Google Gmail service."""
    # Geen crash, maar een return van None als de mail credentials missen.
    if not CREDENTIALS_MAIL or not SCOPES_MAIL:
        return None
        
    creds = authenticate("tokenmail.json", SCOPES_MAIL, CREDENTIALS_MAIL)
    if creds is None:
        return None # Als authenticatie faalt, retourneer None
        
    return build('gmail', 'v1', credentials=creds)


# --- E-MAIL RAPPORTAGE FUNCTIE ---
def send_email_report(added_addresses: Dict, deleted_addresses: Dict, wrong_addresses: Dict):
    """Verstuurt een samenvattend e-mailrapport via de Gmail API."""
    service = create_gmail_service()
    
    # Als de service niet gecreëerd kon worden (credentials missen/fout), log een waarschuwing en stop.
    if service is None:
        logging.warning("E-mailrapport niet verstuurd: Gmail Service kon niet worden gecreëerd (Credentials/Scopes missen of ongeldig).")
        print(" E-mailrapport niet verstuurd (credentials ontbreken).")
        return # Stop de functie als de service ontbreekt

    # ... (rest van de e-mail opbouw logica)

    # Vanaf hier is de e-mail opbouw logica ongewijzigd

    full_message_body = "\n".join(message_parts)
    
    # Stel het e-mailbericht in
    msg = MIMEText(full_message_body)
    current_date = datetime.now().strftime("%d/%m/%Y")
    msg['Subject'] = f'Arkmailer Sync Report - {current_date}'
    
    # Controleer de essentiële e-mailadressen
    if not SENDER_EMAIL or not RECEIVER_EMAIL:
         logging.warning("E-mailrapport niet verstuurd: SENDER_EMAIL of RECEIVER_EMAIL ontbreken in .env.")
         print(" E-mailrapport niet verstuurd (sender/receiver ontbreken).")
         return

    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    # Encodeer en verstuur het bericht
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

    try:
        sent_message = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        logging.info(f"E-mailrapport succesvol verstuurd. Message Id: {sent_message.get('id')}")
        print(f"\n E-mailrapport verstuurd.")
    except Exception as error:
        logging.error(f"Fout bij het versturen van het e-mailrapport: {error}")
        print(f"\n Fout bij het versturen van het e-mailrapport: {error}")
        
    logging.info(full_message_body)


# --- MAIN SCRIPT EXECUTION ---
def main():
    start_time = time.time()
    current_time_start = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    logging.info(f"Script started on: {current_time_start}")
    
    foute_mailadressen = {}
    added_addresses = {}
    deleted_addresses = {}
    
    try:
        logging.info("Start synchronisatie proces...")
        
        # Dit zal nu de "Client secrets" fout opvangen als CREDENTIALS ongeldig is en het script stoppen
        service = create_directory_service() 
        data = load_json_data()
        
        if data:
            directory_map = group_mailaddresses_by_json(data)
            google_group_map = get_google_groups(service)
            
            foute_mailadressen, added_addresses, deleted_addresses = compare_and_sync_maps(
                directory_map, google_group_map, service, 
                foute_mailadressen, added_addresses, deleted_addresses
            )
            
            # 🚨 Mail wordt NU verzonden (of de functie wordt overgeslagen als credentials missen)
            send_email_report(added_addresses, deleted_addresses, foute_mailadressen)
            logging.info("Synchronisatie voltooid.") # Let op: de status is nu VOLTOOID, niet 'succesvol' door de for-loop errors
        else:
             logging.error("Synchronisatie afgebroken: Kon geen WISA data laden.")

    except Exception as e:
        # Dit vangt nu alleen nog fatale errors op van create_directory_service() of de sync-logica
        logging.critical(f"Onverwachte fout in main(): {e}")
        print(f" Onverwachte fout: {e}")
        logging.error(f"Fout tijdens synchronisatie: {e}")
    finally:
        end_time = time.time()
        elapsed_time = end_time - start_time
        delta_time = timedelta(seconds=elapsed_time)
    
        hours, remainder = divmod(delta_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        logging.info(f"Script execution time: {hours} hours, {minutes} minutes, {seconds} seconds")
        current_time_end = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        logging.info(f"Script ended on: {current_time_end}")   

if __name__ == "__main__":
    main()