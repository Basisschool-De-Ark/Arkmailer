<?php
// check_sync_status.php - Geeft de status van het slotbestand terug

$flag_file = 'sync_is_running.flag';
$status = [
    'isRunning' => file_exists($flag_file)
];

header('Content-Type: application/json');
echo json_encode($status);
?>