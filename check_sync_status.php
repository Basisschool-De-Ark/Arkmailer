<?php
// check_sync_status.php - Controleert de laatste wijzigingstijd van het logbestand

$log_file = 'ArkMailer.log'; // Zorg dat dit de correcte naam is!
$max_seconds_idle = 15;      // Maximale tijd (in seconden) dat het logbestand mag stilstaan (Pas aan als de sync langer duurt zonder te loggen)

$status = [
    'isRunning' => false
];

// Controleer of het logbestand bestaat
if (file_exists($log_file)) {
    // Haal de laatste wijzigingstijd op
    $last_modified = filemtime($log_file); 
    
    // Bereken het tijdsverschil
    $time_difference = time() - $last_modified;
    
    // Als het verschil kleiner is dan de maximale idle-tijd, is het script bezig
    if ($time_difference < $max_seconds_idle) {
        $status['isRunning'] = true;
    }
}

header('Content-Type: application/json');
echo json_encode($status);
?>