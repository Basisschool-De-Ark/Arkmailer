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

# --- LOGGING & INIT ---
# Gebruik van een roterende logfile is aan te raden voor productie.
logging.basicConfig(filename="ArkMailer.log", level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

# --- GLOBALE VARIABELEN UIT .ENV ---
try:
    CREDENTIALS = json.loads(os.getenv("CREDENTIALS", "{}"))
    SCOPES = json.loads(os.getenv("SCOPES", "[]"))
    INSTELLINGSNUMMERS = os.getenv("INSTELLINGSNUMMERS")
    WISA_URL = os.getenv("WISA_URL")
    USERNAME_ENV = os.getenv("USERNAME_ENV")
    PASSWORD_ENV = os.getenv("PASSWORD_ENV")
    DOMAIN_NAME = os.getenv("DOMAIN")
    
    # Mail instellingen
    SCOPES_MAIL = json.loads(os.getenv('SCOPES_MAIL', '[]'))
    CREDENTIALS_MAIL = json.loads(os.getenv('CREDENTIALS_MAIL', '{}'))
    SENDER_EMAIL = os.getenv('SENDER_EMAIL_LOGIN')
    RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL')
    
except json.JSONDecodeError as e:
    logging.error(f"Fout bij het laden van JSON variabelen uit .env: {e}")
    exit(1)
except Exception as e:
    logging.error(f"Algemene fout bij het laden van .env variabelen: {e}")
    exit(1)

# --- TEST INSTELLING ---
# OPTIONEEL: Vul hier de exacte KLASCODE in die je wilt testen.
# Bijvoorbeeld: TEST_KLASCODE = "ArkLS-1 blauw"
# Laat leeg (TEST_KLASCODE = "") om alle klassen te syncen.
TEST_KLASCODE = "" # <--- PAS DEZE AAN OM 1 KLAS TE TESTEN

# --- DATUM LOGICA ---
def get_wisa_reference_date() -> str:
    """Berekent de referentiedatum voor de WISA-query."""
    today = date.today()
    
    if today.month == 7:
        # Als het juli is, gebruik 28 juni (laatste schooldag)
        ref_date = today.replace(day=28, month=6)
    elif today.month == 8:
        # Als het augustus is, gebruik 2 september (begin nieuw schooljaar)
        ref_date = today.replace(day=2, month=9)
    else:
        # Trek 14 dagen af in alle andere maanden.
        ref_date = today - timedelta(days=14)
        
    return ref_date.strftime("%d/%m/%Y")

FORMATTED_DATE = get_wisa_reference_date()
BASE_WISA_URL = f"{WISA_URL}/QUERY/OUDERMLR_N?werkdatum={FORMATTED_DATE}&instellingsnummer={INSTELLINGSNUMMERS}"


# --- AUTHENTICATIE FUNCTIES ---
def authenticate(token_file: str, scopes: List[str], client_config: Dict) -> Credentials:
    """Algemene functie voor het authenticeren van Google API's."""
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
    creds = authenticate("tokendir.json", SCOPES, CREDENTIALS)
    return build('admin', 'directory_v1', credentials=creds)

def create_gmail_service():
    """Creëert de Google Gmail service."""
    creds = authenticate("tokenmail.json", SCOPES_MAIL, CREDENTIALS_MAIL)
    return build('gmail', 'v1', credentials=creds)


# --- DATA LADEN FUNCTIES ---
def load_json_data() -> (Dict | None):
    """Haalt data op van de WISA-API."""
    url = f"{BASE_WISA_URL}&_username_={USERNAME_ENV}&_password_={PASSWORD_ENV}&format=json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status() # Vang HTTP-fouten (4xx of 5xx)
        json_data = response.json()

        # Schrijf JSON naar bestand (optioneel, maar behouden om logica niet te breken)
        os.makedirs("output", exist_ok=True)
        with open("output/data.json", "w") as data_file:
            json.dump(json_data, data_file, indent=2)

        logging.info("WISA data succesvol geladen.")
        return json_data
        
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP Fout bij WISA data: {e}. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Netwerkfout bij WISA data: {e}")
    except json.JSONDecodeError:
        logging.error("Fout: Kon de WISA response niet parsen als JSON.")
        
    return None

def generate_google_group_address(class_code: str) -> str:
    """Genereert het Google Groepsadres o.b.v. de klascode."""
    cleaned_prefix = class_code.strip().lower()

    # Verwijder bekende prefixes
    prefixes_to_remove = ["arkls-", "arkks-"]
    for prefix in prefixes_to_remove:
        if cleaned_prefix.startswith(prefix):
            cleaned_prefix = cleaned_prefix[len(prefix):]
            break

    # Verwijder spaties die na de prefixverwijdering nog kunnen bestaan
    cleaned_prefix = cleaned_prefix.replace(" ", "")
    
    return f"{cleaned_prefix}.ouders@{DOMAIN_NAME}"


def group_mailaddresses_by_json(data: List[Dict]) -> Dict[str, Set[str]]:
    """Mapt unieke e-mailadressen uit de WISA-data naar hun respectievelijke groepsadressen."""
    directory_group_mail_mapping = {}
    
    for student in data:
        if student.get("TYPE", "").strip().lower() == "lln": # Gebruik .strip() om extra spaties te verwijderen
            class_code = student.get("KLASCODE", "")
            # -----------------------------------------------------------------
            # !!! NIEUWE TEST FILTER LOGICA !!!
            # -----------------------------------------------------------------
            if TEST_KLASCODE and class_code.strip() != TEST_KLASCODE.strip():
                continue # Sla alle andere klassen over
            # -----------------------------------------------------------------
            email_addresses_raw = student.get("MAILADRESSEN", "")
            
            if not class_code or not email_addresses_raw:
                continue

            groepsadres = generate_google_group_address(class_code)
            
            # Verwerk e-mailadressen
            email_addresses = [email.strip().lower() for email in email_addresses_raw.split(',') if email.strip()]
            
            # Voeg de unieke, opgeschoonde adressen toe aan de map
            if groepsadres not in directory_group_mail_mapping:
                directory_group_mail_mapping[groepsadres] = set()
            directory_group_mail_mapping[groepsadres].update(email_addresses)
            
    return directory_group_mail_mapping


def get_google_groups(service) -> Dict[str, Set[str]]:
    """Haalt alle relevante groepen en hun leden op uit het domein."""
    group_mapping = {}
    page_token = None

    try:
        while True:
            logging.info("Groepen ophalen...")
            response = service.groups().list(customer='my_customer', pageToken=page_token).execute()
            groups = response.get('groups', [])

            for group in groups:
                group_email = group.get('email', '').lower()
                
                # Filter op de vereiste naamgevingsconventie
                if group_email.endswith(f".ouders@{DOMAIN_NAME.lower()}"): 
                    # Haal leden op voor deze groep
                    members = get_group_members(service, group_email)
                    group_mapping[group_email] = set(members)

            page_token = response.get('nextPageToken')
            if not page_token:
                break
        
        logging.info(f"Totaal {len(group_mapping)} relevante groepen opgehaald.")
        return group_mapping

    except HttpError as e:
        logging.error(f"Fout bij het ophalen van Google Groepen (HTTP-fout): {e}")
        return {}
    except Exception as e:
        logging.error(f"Algemene fout bij het ophalen van groepen: {e}")
        return {}


def get_group_members(service, group_email: str) -> List[str]:
    """Haalt alle leden van een specifieke groep op."""
    members_list = []
    page_token = None
    try:
        while True:
            response = service.members().list(groupKey=group_email, pageToken=page_token).execute()
            members = response.get('members', [])
            members_list.extend([member['email'].lower() for member in members if 'email' in member])
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return members_list
    except HttpError as e:
        # 404 betekent dat de groep niet bestaat, maar dit zou al in de hoofdlogica moeten zijn opgevangen
        logging.warning(f"Fout bij het ophalen van leden van {group_email}: {e}")
        return []
    except Exception as e:
        logging.error(f"Algemene fout bij het ophalen van leden van {group_email}: {e}")
        return []

# --- GMAIL VARIATIE FUNCTIE (Vereenvoudigd en correct) ---
def normalize_gmail_address(email: str) -> str:
    """Normaliseert een Gmail/Googlemail adres (verwijdert dots en alles na +)."""
    email = email.lower()
    if email.endswith("@gmail.com") or email.endswith("@googlemail.com"):
        local_part, domain = email.split('@')
        
        # 1. Verwijder alles na het '+' teken
        local_part = local_part.split('+')[0]
        
        # 2. Verwijder alle dots (punten)
        local_part = local_part.replace('.', '')
        
        # 3. Normaliseer @googlemail.com naar @gmail.com (Google's voorkeursvorm)
        normalized_domain = "gmail.com"
        
        return f"{local_part}@{normalized_domain}"
    return email # Retourneer ongewijzigd als het geen Gmail/Googlemail is

# --- SYNCHRONISATIE ACTIES ---

def add_member_to_group(service, group_email: str, member_email: str, wrong_mails: Dict, added_addresses: Dict):
    """Voegt een lid toe en handelt fouten af."""
    try:
        service.members().insert(groupKey=group_email, body={"email": member_email, "role": "MEMBER"}).execute()
        logging.info(f"E-mailadres {member_email} toegevoegd aan groep: {group_email}")
        print(f"✅ E-mailadres {member_email} toegevoegd aan groep: {group_email}")
        
        if group_email not in added_addresses:
            added_addresses[group_email] = set()
        added_addresses[group_email].add(member_email)
        
    except HttpError as e:
        status_code = e.resp.status
        
        if status_code == 409: # Conflict: Lid bestaat al
            logging.info(f"Lid {member_email} is reeds lid van {group_email} (409 Conflict).")
            print(f"➡️ Lid {member_email} is reeds lid van {group_email}.")
        elif status_code == 404: # Not Found: Geen geldig Google-account
            if group_email not in wrong_mails:
                wrong_mails[group_email] = set()
            wrong_mails[group_email].add(member_email)
            logging.warning(f"Ongeldig account: {member_email} in {group_email} (404 Not Found).")
            print(f"⚠️ Ongeldig account: {member_email} in {group_email}.")
        else:
            logging.error(f"Fout bij het toevoegen van {member_email} aan {group_email} ({status_code}): {e}")
            print(f"❌ Fout bij toevoegen {member_email} aan {group_email} ({status_code}): {e}")
    except Exception as e:
        logging.critical(f"Kritieke fout bij toevoegen lid {member_email}: {e}")
        print(f"❌ Kritieke fout bij toevoegen lid {member_email}: {e}")


def remove_member_from_group(service, group_email: str, member_email: str, deleted_addresses: Dict):
    """Verwijdert een lid uit een groep."""
    try:
        service.members().delete(groupKey=group_email, memberKey=member_email).execute()
        logging.info(f"E-mailadres {member_email} verwijderd uit groep: {group_email}")
        print(f"🗑️ E-mailadres {member_email} verwijderd uit groep: {group_email}")

        if group_email not in deleted_addresses:
            deleted_addresses[group_email] = set()
        deleted_addresses[group_email].add(member_email)
        
    except HttpError as e:
        if e.resp.status == 404:
            logging.info(f"Lid {member_email} was al verwijderd of niet gevonden in {group_email} (404 Not Found).")
        else:
            logging.error(f"Fout bij het verwijderen van {member_email} uit {group_email}: {e}")
            print(f"❌ Fout bij verwijderen {member_email} uit {group_email}: {e}")
    except Exception as e:
        logging.critical(f"Kritieke fout bij verwijderen lid {member_email}: {e}")
        print(f"❌ Kritieke fout bij verwijderen lid {member_email}: {e}")


def ensure_group_exists(service, email: str, name: str, description: str):
    """Controleert of de Google Groep bestaat. Zo niet, dan wordt deze aangemaakt."""
    try:
        service.groups().get(groupKey=email).execute()
        logging.info(f"Groep '{email}' bestaat al.")
        return True
    
    except HttpError as e:
        if e.resp.status == 404:
            logging.info(f"Groep '{email}' niet gevonden. Wordt aangemaakt...")
            group_body = {
                'email': email,
                'name': name,
                'description': description
            }
            try:
                service.groups().insert(body=group_body).execute()
                logging.info(f"Groep '{email}' succesvol aangemaakt.")
                return True
            except HttpError as creation_error:
                logging.error(f"FATALE FOUT bij het aanmaken van de groep: {creation_error}")
                print(f"❌ FATALE FOUT bij het aanmaken van de groep: {creation_error}")
                return False
        
        logging.error(f"FATALE FOUT bij controleren/aanmaken van groep: {e}")
        print(f"❌ FATALE FOUT bij controleren/aanmaken van groep: {e}")
        return False


def compare_and_sync_maps(directory_map: Dict[str, Set[str]], google_group_map: Dict[str, Set[str]], service, 
                          wrong_mails: Dict, added_addresses: Dict, deleted_addresses: Dict):
    """Vergelijkt de WISA-map met de Google-map en voert synchronisatieacties uit."""
    
    # Maak een genormaliseerde map van Google-adressen voor snelle lookups (alleen voor Gmail-adressen)
    google_normalized_map: Dict[str, Set[str]] = {}
    for group, members in google_group_map.items():
        if group not in google_normalized_map:
            google_normalized_map[group] = set()
        for member in members:
            google_normalized_map[group].add(normalize_gmail_address(member))

    for groepsadres, directory_mailadressen in directory_map.items():
        logging.info(f"Start synchronisatie voor groep: {groepsadres}")
        print(f"\nStart synchronisatie voor groep: {groepsadres}")
        
        # --- 1. Zorg dat de groep bestaat ---
        group_name = groepsadres.split('@')[0].split('.')[0].capitalize()
        group_description = f"Automatische synchronisatie groep voor {groepsadres}"
        if not ensure_group_exists(service, groepsadres, group_name, group_description):
            continue # Sla deze groep over als aanmaken/bestaan faalt
            
        # Haal de huidige leden op (nu is de groep zeker aanwezig)
        google_addresses = google_group_map.get(groepsadres, set())
        
        # --- 2. Bepaal adressen om te verwijderen ---
        addresses_to_remove = set()
        for member_to_check in google_addresses:
            normalized_member = normalize_gmail_address(member_to_check)
            
            # Controleer of het lid nog in de WISA-data zit (normaal of genormaliseerd)
            if normalized_member in directory_mailadressen or member_to_check in directory_mailadressen:
                continue # Lid zit in de Directory map (of is een geldige variatie van een lid)
            
            # Als het lid niet in de WISA-data zit, moet het verwijderd worden.
            addresses_to_remove.add(member_to_check)
            
        # Voer de verwijderingen uit
        for mailadres_to_remove in addresses_to_remove:
            remove_member_from_group(service, groepsadres, mailadres_to_remove, deleted_addresses)

        # --- 3. Bepaal adressen om toe te voegen ---
        addresses_to_add = set()
        for member_to_check in directory_mailadressen:
            # Normaliseer het adres uit de Directory map
            normalized_member = normalize_gmail_address(member_to_check)
            
            # Controleer of het lid al in de Google map zit (normaal of genormaliseerd)
            if member_to_check in google_addresses:
                continue # Zit er al in
            if normalized_member in google_normalized_map.get(groepsadres, set()):
                continue # Zit er al in onder een genormaliseerde vorm (bijv. zonder punt)

            # Als het lid nog niet in de Google map zit, moet het toegevoegd worden.
            addresses_to_add.add(member_to_check)
            
        # Voer de toevoegingen uit
        for mailadres_to_add in addresses_to_add:
            add_member_to_group(service, groepsadres, mailadres_to_add, wrong_mails, added_addresses)
            
        logging.info(f"Synchronisatie voltooid voor groep: {groepsadres}")

    return wrong_mails, added_addresses, deleted_addresses


# --- E-MAIL RAPPORTAGE FUNCTIE ---
def send_email_report(added_addresses: Dict, deleted_addresses: Dict, wrong_addresses: Dict):
    """Verstuurt een samenvattend e-mailrapport via de Gmail API."""
    creds = create_gmail_service()
    service = build('gmail', 'v1', credentials=creds)
    
    # Opbouw van het rapportbericht
    message_parts = []
    
    if added_addresses:
        message_parts.append("\n--- Adressen Toegevoegd ---")
        for group_email, members in added_addresses.items():
            message_parts.append(f"\nToegevoegd aan groep {group_email}:")
            for member in members:
                message_parts.append(f"- {member}")
    else:
        message_parts.append("\n--- Geen Adressen Toegevoegd ---")

    if deleted_addresses:
        message_parts.append("\n--- Adressen Verwijderd ---")
        for group_email, members in deleted_addresses.items():
            message_parts.append(f"\nVerwijderd uit groep {group_email}:")
            for member in members:
                message_parts.append(f"- {member}")
    else:
        message_parts.append("\n--- Geen Adressen Verwijderd ---")

    if wrong_addresses:
        message_parts.append("\n--- FOUTIEVE/NIET-Bestaande Adressen ---")
        for group_email, members in wrong_addresses.items():
            message_parts.append(f"\nFout opgetreden in groep {group_email}:")
            for member in members:
                message_parts.append(f"- {member} (Niet toegevoegd/Bestaat niet)")
    else:
        message_parts.append("\n--- Geen Foutieve Adressen Gevonden ---")

    full_message_body = "\n".join(message_parts)
    
    # Stel het e-mailbericht in
    msg = MIMEText(full_message_body)
    current_date = datetime.now().strftime("%d/%m/%Y")
    msg['Subject'] = f'Arkmailer Sync Report - {current_date}'
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    # Encodeer en verstuur het bericht
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

    try:
        sent_message = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        logging.info(f"E-mailrapport succesvol verstuurd. Message Id: {sent_message.get('id')}")
        print(f"\n✅ E-mailrapport verstuurd.")
    except Exception as error:
        logging.error(f"Fout bij het versturen van het e-mailrapport: {error}")
        print(f"\n❌ Fout bij het versturen van het e-mailrapport: {error}")
        
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
        service = create_directory_service()
        data = load_json_data()
        
        if data:
            directory_map = group_mailaddresses_by_json(data)
            # Haal groepen op NA het creëren van de directory service
            google_group_map = get_google_groups(service)
            
            foute_mailadressen, added_addresses, deleted_addresses = compare_and_sync_maps(
                directory_map, google_group_map, service, 
                foute_mailadressen, added_addresses, deleted_addresses
            )
            
        send_email_report(added_addresses, deleted_addresses, foute_mailadressen)
        logging.info("Synchronisatie succesvol voltooid.")

    except Exception as e:
        logging.critical(f"Onverwachte fout in main(): {e}")
        print(f"❌ Onverwachte fout: {e}")
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