<?php
// run_script.php - Voorkomt dubbele uitvoeringen en logt de uitvoeringsfout

// 1. DEFINITIE VAN HET VLAGBESTAND EN PADEN
$flag_file = 'sync_is_running.flag';
$debug_log_file = 'sync_execution_debug.log'; // Nieuw bestand voor foutmeldingen
$python_exe = 'C:\Users\De Ark\AppData\Local\Python\pythoncore-3.14-64\python.exe'; 
$python_script = 'C:\Users\De Ark\Documents\Arkmailer\arkmailer-main\ArkMailer.py';
$log_viewer_url = 'log_viewer.html'; // Zorg dat dit de correcte HTML bestandsnaam is

// 2. CHECK: VOORKOM DUBBELE RUNS
if (file_exists($flag_file)) {
    header("Location: {$log_viewer_url}?status=running");
    exit;
}

// 3. VLAG ZETTEN EN COMMANDO UITVOEREN
// Maak het vlagbestand aan (slotmechanisme)
file_put_contents($flag_file, date('Y-m-d H:i:s'));

// 4. BOUW EN LOG HET COMMANDO

// Maak een robuust commando dat de uitvoer naar een debug log stuurt.
// '> sync_execution_debug.log 2>&1' stuurt STDOUT en STDERR naar het logbestand.
// '&' voert asynchroon uit op de achtergrond.
$command_to_run = escapeshellarg($python_exe) . " " . escapeshellarg($python_script) . " > " . escapeshellarg($debug_log_file) . " 2>&1 &";

// Log het commando dat we proberen uit te voeren (voor extra debuggen)
file_put_contents($debug_log_file, 
    "--- START EXECUTION AT " . date('Y-m-d H:i:s') . " ---\n", 
    FILE_APPEND
);

// Voer het commando op de achtergrond uit
exec($command_to_run); 

// Stuur de gebruiker terug
header("Location: {$log_viewer_url}?status=started");
exit;
?>