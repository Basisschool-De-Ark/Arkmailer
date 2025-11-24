<?php
// save_config.php - Script om formuliergegevens op te slaan in het .env bestand

// Zorg dat de .env bibliotheek geladen is
require 'vendor/autoload.php'; 
use Dotenv\Dotenv;

// 1. Definitie van het .env pad
$env_path = __DIR__;
$env_file_name = '.env';
$env_file_full_path = $env_path . DIRECTORY_SEPARATOR . $env_file_name;

// 2. Controleren en valideren van de invoer
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || empty($_POST)) {
    header('Location: log_viewer.html?status=error&msg=Geen geldige invoer');
    exit;
}

// 3. De .env file inlezen
if (!file_exists($env_file_full_path) || !is_writable($env_file_full_path)) {
    // Dit is een fatale fout: de webserver heeft geen schrijfrechten!
    header('Location: log_viewer.html?status=error&msg=FATALE FOUT: .env bestand bestaat niet of is niet beschrijfbaar (SCHRIJFRECHTEN!).');
    exit;
}

$env_content = file_get_contents($env_file_full_path);
$new_env_content = $env_content;

// 4. De nieuwe waarden toepassen
// Loop door alle ingediende velden en vervang de waarden in de .env content
foreach ($_POST as $key => $value) {
    // We negeren lege velden om geen bestaande instellingen te verwijderen
    if ($key === 'password' || empty($value)) {
        continue;
    }

    // 4a. Beveilig de waarde: zorg ervoor dat de waarde correct wordt opgeslagen in quotes
    // Voor JSON-strings of paden
    $escaped_value = addslashes($value);
    
    // 4b. De reguliere expressie om de variabele te vervangen:
    // Zoekt naar: VARIABLENAAM=...
    $pattern = '/^' . preg_quote($key) . '=(.*)$/m'; 

    if (preg_match($pattern, $env_content)) {
        // Variabele gevonden: Vervang de hele regel
        $new_env_content = preg_replace(
            $pattern,
            $key . '="' . $escaped_value . '"',
            $new_env_content,
            1 // Vervang slechts één keer
        );
    } else {
        // Variabele niet gevonden: Voeg deze toe aan het einde
        $new_env_content .= "\n" . $key . '="' . $escaped_value . '"';
    }
}

// 5. De nieuwe content wegschrijven
if (file_put_contents($env_file_full_path, $new_env_content) === false) {
    header('Location: log_viewer.html?status=error&msg=Fout bij wegschrijven naar .env.');
    exit;
}

// 6. Succesmelding
header('Location: log_viewer.html?status=success&msg=Instellingen succesvol bijgewerkt. Herstart de sync.');
exit;
?>