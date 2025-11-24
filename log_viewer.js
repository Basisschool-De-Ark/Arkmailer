const LOG_FILE = 'ArkMailer.log';
let allLogLines = []; 
let refreshIntervalId = null; 
const REFRESH_TIME = 5000; // Herlaad om de 5 seconden
const STATUS_CHECK_TIME = 5000; // Statuscheck om de 5 seconden (verhoogd voor stabiliteit)

// --- CORE FUNCTIES ---

// Functie om de datumkiezer in te stellen op de datum van vandaag (YYYY-MM-DD)
function initDateInput() {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); 
    const dd = String(today.getDate()).padStart(2, '0');
    
    const formattedDate = `${yyyy}-${mm}-${dd}`;
    
    if (!document.getElementById('filterDate').value) {
        document.getElementById('filterDate').value = formattedDate;
    }
}

// Logs laden met een cache-buster (Harde Refresh)
function loadLogs() {
    initDateInput();
    
    const container = document.getElementById('logContainer');
    const cacheBuster = `?v=${new Date().getTime()}`; 

    fetch(LOG_FILE + cacheBuster) 
        .then(response => {
            if (!response.ok) throw new Error(`Status: ${response.status}`);
            return response.text();
        })
        .then(text => {
            allLogLines = text.trim().split('\n').filter(line => line.trim() !== ''); 
            
            // DRAAI DE ARRAY OM: Nieuwste logs bovenaan
            allLogLines.reverse();
            
            document.getElementById('lineCount').textContent = `Totaal regels: ${allLogLines.length}`;
            
            filterLogs(); 
        })
        .catch(error => {
            container.innerHTML = `<p style="color: red;">❌ FOUT: Kan '${LOG_FILE}' niet laden via de webserver.</p><p style="color: #555;">Details: ${error.message}</p>`;
        });
}

// Logs weergeven op de pagina
function displayLogs(lines) {
    const container = document.getElementById('logContainer');
    container.innerHTML = ''; 

    if (lines.length === 0) {
        container.innerHTML = '<p>Geen loglijnen gevonden voor deze selectie.</p>';
        return;
    }

    lines.forEach(line => {
        const logElement = document.createElement('div');
        logElement.className = 'log-line';
        logElement.textContent = line;
        
        const levelMatch = line.match(/\s-\s(INFO|WARNING|ERROR|CRITICAL|DEBUG)\s-/i);
        if (levelMatch && levelMatch[1]) {
            logElement.classList.add(levelMatch[1].toUpperCase());
        }

        container.appendChild(logElement);
    });
}

// Filter logs op niveau, zoekterm én DATUM
function filterLogs() {
    if (allLogLines.length === 0) return;
    
    const dateFilter = document.getElementById('filterDate').value; 
    const levelFilter = document.getElementById('filterLevel').value.toUpperCase();
    const searchTerm = document.getElementById('search').value.toLowerCase();
    
    const filteredLines = allLogLines.filter(line => {
        const logDateMatch = line.match(/^(\d{4}-\d{2}-\d{2})/);
        const logDate = logDateMatch ? logDateMatch[1] : null;

        const datePass = !dateFilter || (logDate && logDate === dateFilter);

        const levelMatch = line.match(/\s-\s(INFO|WARNING|ERROR|CRITICAL|DEBUG)\s-/i);
        const lineLevel = levelMatch && levelMatch[1] ? levelMatch[1].toUpperCase() : 'UNKNOWN';
        const levelPass = !levelFilter || levelFilter === lineLevel;
        
        const searchPass = !searchTerm || line.toLowerCase().includes(searchTerm);
        
        return datePass && levelPass && searchPass;
    });
    
    displayLogs(filteredLines);
    document.getElementById('lineCount').textContent = `Totaal regels: ${filteredLines.length} (gefilterd)`;
}

// --- AUTOREFRESH & STATUS LOGICA ---

// NIEUWE FUNCTIE: Start de synchronisatie via fetch om browser redirects te voorkomen
function startSynchronization() {
    const runButton = document.getElementById('runButton');

    // Voorkom dubbelklikken onmiddellijk en toon 'opstarten'
    runButton.disabled = true;
    runButton.textContent = '🔄 Bezig met opstarten...'; 
    runButton.style.backgroundColor = '#ffc107'; 
    runButton.style.color = '#333';
    
    // Roep run_script.php aan zonder de pagina te verlaten
    fetch('run_script.php')
        .then(response => {
            if (!response.ok) {
                // Als de PHP server een foutcode teruggeeft (bv. 500)
                throw new Error(`Serverfout bij opstarten: ${response.status}`);
            }
            // De PHP-opstart was succesvol (HTTP 200), nu status checken
            checkSyncStatus(); 
            //alert('✅ Synchronisatie is succesvol opgestart. Volg de voortgang hier.');
        })
        .catch(error => {
            alert('❌ Fout bij het starten van de synchronisatie: ' + error.message);
            // Herstel de knopstatus in geval van fout
            checkSyncStatus(); 
        });
}


// Start de automatische herlading van de logs
function startAutoRefresh() {
    if (refreshIntervalId) return; 
    
    document.getElementById('refreshStatus').style.display = 'inline-block';
    document.getElementById('runButton').disabled = true; 
    
    let timer = REFRESH_TIME / 1000;
    
    const updateTimer = () => {
        document.getElementById('refreshTimer').textContent = `Herlaadt over ${timer}s...`;
        timer--;
        if (timer < 0) {
            timer = REFRESH_TIME / 1000;
            loadLogs(); // Herlaad de logs
        }
    };
    
    updateTimer(); 
    refreshIntervalId = setInterval(updateTimer, 1000); 
}

// Stop de automatische herlading
function stopAutoRefresh() {
    if (refreshIntervalId) {
        clearInterval(refreshIntervalId);
        refreshIntervalId = null;
        document.getElementById('refreshStatus').style.display = 'none';
        console.log("Automatische herlading gestopt.");
    }
}

// Functie om de status van het vlagbestand te controleren (voor de knop)
function checkSyncStatus() {
    const runButton = document.getElementById('runButton');
    
    // Gebruik een cache-buster en de verhoogde status check tijd
    const cacheBuster = `?v=${new Date().getTime()}`; 

    fetch('check_sync_status.php' + cacheBuster)
        .then(response => {
             if (!response.ok) throw new Error('Status PHP error');
             return response.json();
        })
        .then(data => {
            if (data.isRunning) {
                // HET SCRIPT IS BEZIG
                runButton.disabled = true;
                runButton.textContent = '🔄 Sync Loopt...';
                runButton.style.backgroundColor = '#ffc107'; 
                runButton.style.color = '#333';
                
                if (!refreshIntervalId) { 
                    startAutoRefresh(); 
                }
            } else {
                // HET SCRIPT IS GESTOPT
                runButton.disabled = false;
                runButton.textContent = '▶️ Start Sync';
                runButton.style.backgroundColor = '#28a745'; 
                runButton.style.color = 'white';
                
                if (refreshIntervalId) { 
                    // Stopt de refresh EN maakt de knop weer vrij
                    stopAutoRefresh(); 
                }
            }
        })
        .catch(error => {
            console.error("Fout bij controleren sync status:", error);
            // Zorg ervoor dat de knop in ieder geval aanklikbaar blijft als de check faalt
            runButton.disabled = false;
        });
}

// --- PAGINA INITIALISATIE ---

// 1. Laad de logs bij de start
loadLogs();

// 2. Start de statuscheck interval
checkSyncStatus();
setInterval(checkSyncStatus, STATUS_CHECK_TIME); 

// 3. Controleer de URL parameters voor de initiële status (oude redirects, nu vervangen door alerts)
const urlParams = new URLSearchParams(window.location.search);
const status = urlParams.get('status');

// Verwijder de oude status parameters uit de URL (omdat we nu alerts gebruiken)
if (status === 'started' || status === 'running') {
    history.replaceState(null, '', window.location.pathname);
}

// --- Settings modaal venster ---
var modal = document.getElementById("configModal");

    // Functie om de modal te openen
    function openModal() {
        modal.style.display = "block";
    }

    // Functie om de modal te sluiten
    function closeModal() {
        modal.style.display = "none";
    }

    // Sluit de modal als de gebruiker buiten het venster klikt
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    }