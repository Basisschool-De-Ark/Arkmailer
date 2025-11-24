<?php
// run_script.php - Voorkomt dubbele uitvoeringen en logt de uitvoeringsfout

// --- 1. LADEN VAN .ENV VARIABELEN ---
require 'C:\\Users\\De Ark\\Documents\\Arkmailer\\arkmailer-main\\vendor\\autoload.php';

// GEEN 'use Dotenv\Dotenv;' nodig als we de volledige naam gebruiken
try {
    // Gebruik de volledige klassenaam: \Dotenv\Dotenv
    $dotenv = \Dotenv\Dotenv::createImmutable(__DIR__);
    
    $dotenv->load();

} catch (\Exception $e) {
    // ... (rest van de foutafhandeling)
    http_response_code(500);
    echo json_encode(['status' => 'error', 'message' => 'Kan .env bestand niet laden. Fout: ' . $e->getMessage()]);
    exit;
}

// --- 2. VARIABELEN OPHALEN UIT DE OMGEVING ---
// Haal de paden op uit de geladen omgevingsvariabelen
$python_exe = getenv('PYTHON_EXECUTABLE');
$python_script = getenv('PYTHON_SCRIPT_PATH');
$debug_log_file = getenv('DEBUG_LOG_FILE');
$log_viewer_url = getenv('LOG_VIEWER_URL');


// Sanity Check: Controleer of de paden zijn gevonden
if (!$python_exe || !$python_script) {
    http_response_code(500);
    echo json_encode(['status' => 'error', 'message' => 'Configuratiefout: PYTHON_EXECUTABLE of PYTHON_SCRIPT_PATH ontbreekt in .env.']);
    exit;
}

// --- 3. COMMANDO VORMEN EN UITVOEREN ---
// We gebruiken de variabelen uit .env om het commando te vormen.
// De functie escapeshellarg is essentieel voor Windows paden met spaties
$command_to_run = escapeshellarg($python_exe) . " " . escapeshellarg($python_script) . " > " . escapeshellarg($debug_log_file) . " 2>&1 &";

// Log het commando
file_put_contents($debug_log_file, 
    "--- START EXECUTION VIA WEB AT " . date('Y-m-d H:i:s') . " ---\nCommand: " . $command_to_run . "\n", 
    FILE_APPEND
);

// Voer het commando op de achtergrond uit
exec($command_to_run); 

// Stuur een bevestiging terug
http_response_code(200);
echo json_encode(['status' => 'started', 'message' => 'Script successvol opgestart. Zie ' . $debug_log_file . ' voor de status.']);
exit;
?>