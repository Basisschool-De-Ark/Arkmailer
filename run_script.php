<?php
// run_script.php

// run_script.php

// 1. Definitie van de paden (GEBRUIK BACKSLASHES!)
$python_exe = 'C:\Users\De Ark\AppData\Local\Python\pythoncore-3.14-64\python.exe'; 
$python_script = 'C:\Users\De Ark\Documents\Arkmailer\arkmailer-main\ArkMailer.py';


// 2. Het uitvoercommando: Gebruik DUBBELE QUOTES en het start commando.
// We gebruiken shell_exec omdat dit soms betere resultaten geeft dan exec voor het 'start'-commando.
$command = "start /min cmd.exe /c \"\"{$python_exe}\" \"{$python_script}\"\"";


// 3. Voer het commando uit.
shell_exec($command);

// Stuur de gebruiker terug naar de log viewer
header('Location: log_viewer.html?status=started');
exit;
?>