import time
import json
import os
import requests
import logging
import base64
import sys
from datetime import date, timedelta, datetime
from typing import Dict, Set, List, Optional

# Externe bibliotheken
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- LOGGING & INIT ---
# Gebruik van UTF-8 codering voor de logfile om tekens en speciale symbolen correct te ondersteunen.
logging.basicConfig(
    filename="ArkMailer.log", 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8' # CRUCIALE FIX VOOR charmap/unicode fouten
)
load_dotenv()

# --- VEILIGE JSON LADER FUNCTIE ---
def safe_json_load(env_var_name: str, default_value):
    """Laadt JSON uit .env variabele met foutafhandeling en controle op leegte."""
    json_string = os.getenv(env_var_name)
    if not json_string:
        return default_value
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        # Kritieke fout bij ongeldige JSON-syntax, stopt het script
        logging.critical(f"FATALE FOUT: Fout bij het laden van JSON uit .env voor '{env_var_name}': {e}. Controleer of de JSON correct is ge-escaped.")
        print(f"\nFATALE FOUT: JSONDecodeError in .env voor {env_var_name}. Zie log.")
        sys.exit(1)

# --- GLOBALE VARIABELEN UIT .ENV (NU ROBUUSTER) ---
try:
    # Directory Service (Vereist)
    CREDENTIALS = safe_json_load("CREDENTIALS", {})
    SCOPES = safe_json_load("SCOPES", [])

    # Gmail Service (Optioneel/Rapportage)
    SCOPES_MAIL = safe_json_load("SCOPES_MAIL", [])
    CREDENTIALS_MAIL = safe_json_load("CREDENTIALS_MAIL", {})
    
    # Overige variabelen
    INSTELLINGSNUMMERS = os.getenv("INSTELLINGSNUMMERS")
    WISA_URL = os.getenv("WISA_URL")
    USERNAME_ENV = os.getenv("USERNAME_ENV")
    PASSWORD_ENV = os.getenv("PASSWORD_ENV")
    DOMAIN_NAME = os.getenv("DOMAIN")
    SENDER_EMAIL = os.getenv('SENDER_EMAIL_LOGIN')
    RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL')
    
except Exception as e:
    logging.critical(f"FATALE OPSTARTFOUT tijdens initialisatie: {e}")
    sys.exit(1)

# --- TEST INSTELLING ---
# Laat leeg (TEST_KLASCODE = "") om alle klassen te syncen.
TEST_KLASCODE = ""

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
        #ref_date = today - timedelta(days=14)
        ref_date = today.replace(day=30, month=1)
        
    return ref_date.strftime("%d/%m/%Y")

FORMATTED_DATE = get_wisa_reference_date()
BASE_WISA_URL = f"{WISA_URL}/QUERY/OUDERMLR_N?werkdatum={FORMATTED_DATE}&instellingsnummer={INSTELLINGSNUMMERS}"


# --- AUTHENTICATIE FUNCTIES ---
def authenticate(token_file: str, scopes: List[str], client_config: Dict) -> Optional[Credentials]:
    """Algemene functie voor het authenticeren van Google API's."""
    # Dit vangt de 'Client secrets must be for a web or installed app' fout af.
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
    if not CREDENTIALS or not SCOPES:
        raise Exception("DIRECTORY CREDENTIALS en/of SCOPES ontbreken. Kan niet synchroniseren.")
        
    creds = authenticate("tokendir.json", SCOPES, CREDENTIALS)
    if creds is None:
         raise Exception("Authenticatie voor Directory Service mislukt.")
         
    return build('admin', 'directory_v1', credentials=creds)

def create_gmail_service():
    """Creëert de Google Gmail service."""
    if not CREDENTIALS_MAIL or not SCOPES_MAIL:
        return None
        
    creds = authenticate("tokenmail.json", SCOPES_MAIL, CREDENTIALS_MAIL)
    if creds is None:
        return None
        
    return build('gmail', 'v1', credentials=creds)


# --- DATA LADEN FUNCTIES ---
def load_json_data() -> Optional[Dict]:
    """Haalt data op van de WISA-API."""
    url = f"{BASE_WISA_URL}&_username_={USERNAME_ENV}&_password_={PASSWORD_ENV}&format=json"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status() # Vang HTTP-fouten (4xx of 5xx)
        json_data = response.json()

        # Schrijf JSON naar bestand (optioneel)
        os.makedirs("output", exist_ok=True)
        with open("output/data.json", "w", encoding='utf-8') as data_file:
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
    SPECIFIEKE_KLAS = "ArkKS-K1 Kikker" # FIX voor de Kikkerklas
    
    all_class_codes = set() # Voor debugging
    
    for student in data:
        class_code = student.get("KLASCODE", "").strip()
        student_type = student.get("TYPE", "").strip().lower()
        
        if class_code:
            all_class_codes.add(class_code)
        
        # FIX: Accepteer de Kikkerklas ongeacht het TYPE veld, of als het een gewone leerling (lln) is.
        if student_type == "lln" or class_code == SPECIFIEKE_KLAS:
            
            # --- Test Filter Logica ---
            if TEST_KLASCODE and class_code != TEST_KLASCODE.strip():
                continue # Sla alle andere klassen over als TEST_KLASCODE is ingesteld
            # --------------------------
            
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
            
    logging.info(f"Alle KLASCODE's gevonden in de ruwe WISA data: {sorted(list(all_class_codes))}")
    return directory_group_mail_mapping


def get_google_groups(service) -> Dict[str, Set[str]]:
    """Haalt alle relevante groepen en hun leden op uit het domein."""
    # ... (code is ongewijzigd) ...
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
    # ... (code is ongewijzigd) ...
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
        
        # 3. Normaliseer @googlemail.com naar @gmail.com
        normalized_domain = "gmail.com"
        
        return f"{local_part}@{normalized_domain}"
    return email # Retourneer ongewijzigd als het geen Gmail/Googlemail is

# --- SYNCHRONISATIE ACTIES ---

def add_member_to_group(service, group_email: str, member_email: str, wrong_mails: Dict, added_addresses: Dict):
    """Voegt een lid toe en handelt fouten af."""
    try:
        service.members().insert(groupKey=group_email, body={"email": member_email, "role": "MEMBER"}).execute()
        logging.info(f"E-mailadres {member_email} toegevoegd aan groep: {group_email}")
        print(f" E-mailadres {member_email} toegevoegd aan groep: {group_email}") # Geen emoji

        if group_email not in added_addresses:
            added_addresses[group_email] = set()
        added_addresses[group_email].add(member_email)
        
    except HttpError as e:
        status_code = e.resp.status
        
        if status_code == 409: # Conflict: Lid bestaat al
            logging.info(f"Lid {member_email} is reeds lid van {group_email} (409 Conflict).")
            print(f" Lid {member_email} is reeds lid van {group_email}.")
        elif status_code == 404: # Not Found: Geen geldig Google-account
            if group_email not in wrong_mails:
                wrong_mails[group_email] = set()
            wrong_mails[group_email].add(member_email)
            logging.warning(f"Ongeldig account: {member_email} in {group_email} (404 Not Found).")
            print(f" Ongeldig account: {member_email} in {group_email}.")
        else:
            logging.error(f"Fout bij het toevoegen van {member_email} aan {group_email} ({status_code}): {e}")
            print(f" Fout bij toevoegen {member_email} aan {group_email} ({status_code}): {e}")
    except Exception as e:
        logging.critical(f"Kritieke fout bij toevoegen lid {member_email}: {e}")
        print(f" Kritieke fout bij toevoegen lid {member_email}: {e}")


def remove_member_from_group(service, group_email: str, member_email: str, deleted_addresses: Dict):
    """Verwijdert een lid uit een groep."""
    try:
        service.members().delete(groupKey=group_email, memberKey=member_email).execute()
        logging.info(f"E-mailadres {member_email} verwijderd uit groep: {group_email}")
        print(f" E-mailadres {member_email} verwijderd uit groep: {group_email}") # Geen emoji

        if group_email not in deleted_addresses:
            deleted_addresses[group_email] = set()
        deleted_addresses[group_email].add(member_email)
        
    except HttpError as e:
        if e.resp.status == 404:
            logging.info(f"Lid {member_email} was al verwijderd of niet gevonden in {group_email} (404 Not Found).")
        else:
            logging.error(f"Fout bij het verwijderen van {member_email} uit {group_email}: {e}")
            print(f" Fout bij verwijderen {member_email} uit {group_email}: {e}")
    except Exception as e:
        logging.critical(f"Kritieke fout bij verwijderen lid {member_email}: {e}")
        print(f" Kritieke fout bij verwijderen lid {member_email}: {e}")


def ensure_group_exists(service, email: str, name: str, description: str):
    """Controleert of de Google Groep bestaat. Zo niet, dan wordt deze aangemaakt."""
    # ... (code is ongewijzigd) ...
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
                print(f" FATALE FOUT bij het aanmaken van de groep: {creation_error}")
                return False
        
        logging.error(f"FATALE FOUT bij controleren/aanmaken van groep: {e}")
        print(f" FATALE FOUT bij controleren/aanmaken van groep: {e}")
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
            continue
            
        # Haal de huidige leden op 
        google_addresses = google_group_map.get(groepsadres, set())
        
        # --- 2. Bepaal adressen om te verwijderen ---
        addresses_to_remove = set()
        for member_to_check in google_addresses:
            normalized_member = normalize_gmail_address(member_to_check)
            
            if normalized_member in directory_mailadressen or member_to_check in directory_mailadressen:
                continue
            
            addresses_to_remove.add(member_to_check)
            
        # Voer de verwijderingen uit
        for mailadres_to_remove in addresses_to_remove:
            remove_member_from_group(service, groepsadres, mailadres_to_remove, deleted_addresses)

        # --- 3. Bepaal adressen om toe te voegen ---
        addresses_to_add = set()
        for member_to_check in directory_mailadressen:
            normalized_member = normalize_gmail_address(member_to_check)
            
            if member_to_check in google_addresses:
                continue
            if normalized_member in google_normalized_map.get(groepsadres, set()):
                continue

            addresses_to_add.add(member_to_check)
            
        # Voer de toevoegingen uit
        for mailadres_to_add in addresses_to_add:
            add_member_to_group(service, groepsadres, mailadres_to_add, wrong_mails, added_addresses)
            
        logging.info(f"Synchronisatie voltooid voor groep: {groepsadres}")
        
        # CRUCIALE FIX: Vertraging toevoegen om Rate Limiting (HTTP 429) te voorkomen
        time.sleep(1) 
        
    return wrong_mails, added_addresses, deleted_addresses


# --- E-MAIL RAPPORTAGE FUNCTIE (HTML HERWERKT) ---
def send_email_report(added_addresses: Dict, deleted_addresses: Dict, wrong_addresses: Dict):
    """Verstuurt een samenvattend HTML e-mailrapport via de Gmail API."""
    service = create_gmail_service()
    
    # Check op service
    if service is None:
        logging.warning("E-mailrapport niet verstuurd: Gmail Service kon niet worden gecreëerd.")
        print(" E-mailrapport niet verstuurd (credentials ontbreken).")
        return 

    # 1. Genereer de HTML body die overeenkomt met de afbeelding
    html_body = generate_report_html(added_addresses, deleted_addresses, wrong_addresses, SENDER_EMAIL)
    
    # 2. Stel het MIME-bericht in als MIMEMultipart
    msg = MIMEMultipart('alternative')
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    msg['Subject'] = f'Arkmailer - Rapport {current_date}'
    
    # 3. Voeg de HTML-versie toe aan het bericht
    html_part = MIMEText(html_body, 'html')
    msg.attach(html_part)

    # 4. Check op afzender/ontvanger
    if not SENDER_EMAIL or not RECEIVER_EMAIL:
        logging.warning("E-mailrapport niet verstuurd: SENDER_EMAIL of RECEIVER_EMAIL ontbreken in .env.")
        print(" E-mailrapport niet verstuurd (sender/receiver ontbreken).")
        return

    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    # 5. Encodeer en verstuur het bericht
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

    try:
        sent_message = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        logging.info(f"E-mailrapport succesvol verstuurd. Message Id: {sent_message.get('id')}")
        print(f"\n E-mailrapport verstuurd.")
    except Exception as error:
        logging.error(f"Fout bij het versturen van het e-mailrapport: {error}")
        print(f"\n Fout bij het versturen van het e-mailrapport: {error}")
        
    # Log de platte tekst versie van de inhoud voor debuggen
    logging.info("HTML Rapport Inhoud: \n" + html_body)


# --- NIEUWE FUNCTIE: HTML GENERATIE ---
def generate_report_html(added_addresses: Dict, deleted_addresses: Dict, wrong_addresses: Dict, contact_email: str) -> str:
    """Genereert de volledige HTML body voor het e-mailrapport."""
    
    # Functie om de inhoud van de blokken te genereren
    def generate_content_html(addresses: Dict):
        content_html = ""
        for group_email, members in addresses.items():
            content_html += f"<p style='margin: 0; padding-bottom: 5px; font-weight: bold;'>Toegevoegd aan groep {group_email}:</p>"
            content_html += "<ul style='list-style-type: none; padding: 0; margin-top: 0;'>"
            for member in members:
                content_html += f"<li>- <span style='color: white; text-decoration: none;'>{member}</span></li>"
            content_html += "</ul>"
        return content_html

    # Functie om de afzonderlijke gekleurde blokken te maken
    def create_report_block(title: str, addresses: Dict, is_added: bool = False, is_error: bool = False):
        if is_error:
            # Rood voor fouten/verwijderde/niet-gevonden
            bg_color = '#dc3545'
            content_text = 'Geen Foutieve Adressen Gevonden' if not addresses else ''
        elif is_added:
            # Groen voor toegevoegde
            bg_color = '#28a745'
            content_text = 'Geen Adressen Toegevoegd' if not addresses else ''
        else:
            # Rood voor verwijderde
            bg_color = '#dc3545'
            content_text = 'Geen Adressen Verwijderd' if not addresses else ''
            
        content_html = generate_content_html(addresses) if addresses else (
             f"<p style='margin: 0; text-align: center;'>{content_text}</p>"
        )

        # De rode en groene blokken met afgeronde hoeken
        block = f"""
        <div style="background-color: {bg_color}; color: white; border-radius: 10px; padding: 15px; margin-bottom: 20px;">
            <h3 style="text-align: center; margin-top: 0; margin-bottom: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.5); padding-bottom: 5px;">
                {title}
            </h3>
            <div style="font-size: 14px; line-height: 1.5;">
                {content_html}
            </div>
        </div>
        """
        return block

    # Bouw alle blokken op
    added_block = create_report_block("Adressen Toegevoegd", added_addresses, is_added=True)
    deleted_block = create_report_block("Adressen Verwijderd", deleted_addresses, is_added=False)

    # De 'Foutieve Adressen' block gebruikt een iets andere logica voor de titel
    wrong_block_content = {}
    if wrong_addresses:
        # Als er foutieve adressen zijn, gebruik dan de bestaande structuur voor de content
        wrong_block_content = wrong_addresses
        
    wrong_block = create_report_block("Foutieve Adressen", wrong_block_content, is_error=True)

    # De HTML-template
    current_date_str = datetime.now()
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1); }}
            .header {{ background-color: #000; color: white; padding: 15px 20px; border-radius: 8px 8px 0 0; display: flex; justify-content: space-between; align-items: center; }}
            .logo-text {{ font-size: 24px; font-weight: bold; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="logo-text" style="color: white; margin: 0;">Arkmailer - Rapport</h1>
                <span style="font-size: 14px; color: #ccc;">{current_date_str}</span>
            </div>

            <div style="padding: 20px 0;">
                {added_block}
                {deleted_block}
                {wrong_block}
            </div>

            <div style="font-size: 14px; margin-top: 25px; text-align: right; color: #555;">
                Contact: <a href="mailto:{contact_email}" style="color: #555; text-decoration: none;">{contact_email}</a>
            </div>
        </div>
    </body>
    </html>
    """
    return html

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
        
        # Dit roept create_directory_service op, wat crasht bij missende CREDENTIALS
        service = create_directory_service() 
        data = load_json_data()
        
        if data:
            directory_map = group_mailaddresses_by_json(data)
            google_group_map = get_google_groups(service)
            
            foute_mailadressen, added_addresses, deleted_addresses = compare_and_sync_maps(
                directory_map, google_group_map, service, 
                foute_mailadressen, added_addresses, deleted_addresses
            )
            
            # De e-mail wordt nu verstuurd (of overgeslagen als mail credentials missen)
            send_email_report(added_addresses, deleted_addresses, foute_mailadressen)
            logging.info("Synchronisatie voltooid.")
        else:
             logging.error("Synchronisatie afgebroken: Kon geen WISA data laden.")

    except Exception as e:
        # Dit vangt nu alleen nog fatale errors op
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