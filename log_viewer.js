const LOG_FILE = 'ArkMailer.log';
let allLogLines = []; 
let refreshIntervalId = null; // Zorg dat deze initieel null is
const REFRESH_TIME = 5000; // Herlaad om de 5 seconden (pas aan indien nodig)

// --- CORE FUNCTIES ---

// Functie om de datumkiezer in te stellen op de datum van vandaag (YYYY-MM-DD)
function initDateInput() {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); 
    const dd = String(today.getDate()).padStart(2, '0');
    
    const formattedDate = `${yyyy}-${mm}-${dd}`;
    
    // Alleen instellen als er geen waarde is, om filteren niet te verstoren
    if (!document.getElementById('filterDate').value) {
        document.getElementById('filterDate').value = formattedDate;
    }
}

// Logs laden met een cache-buster (Harde Refresh)
function loadLogs() {
    initDateInput();
    
    const container = document.getElementById('logContainer');
    
    // 🚀 CACHE-BUSTER: Voegt een unieke tijdstempel toe om de browser te forceren
    const cacheBuster = `?v=${new Date().getTime()}`; 

    fetch(LOG_FILE + cacheBuster) 
        .then(response => {
            if (!response.ok) throw new Error(`Status: ${response.status}`);
            return response.text();
        })
        .then(text => {
            allLogLines = text.trim().split('\n').filter(line => line.trim() !== ''); 
            
            // 🔄 DRAAI DE ARRAY OM: Nieuwste logs bovenaan
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
    // Alleen filteren als er logs zijn geladen
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

// Start de automatische herlading van de logs
function startAutoRefresh() {
    if (refreshIntervalId) return; // Voorkom dubbele intervallen
    
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
    
    updateTimer(); // Eerste update direct
    refreshIntervalId = setInterval(updateTimer, 1000); 
}

// Stop de automatische herlading
function stopAutoRefresh() {
    if (refreshIntervalId) {
        clearInterval(refreshIntervalId);
        refreshIntervalId = null;
        document.getElementById('refreshStatus').style.display = 'none';
        // Knop wordt geactiveerd door checkSyncStatus()
        console.log("Automatische herlading gestopt.");
    }
}

// Functie om de status van het vlagbestand te controleren
function checkSyncStatus() {
    const runButton = document.getElementById('runButton');
    
    // Gebruik een cache-buster om ervoor te zorgen dat we de meest recente status krijgen
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
                runButton.style.backgroundColor = '#ffc107'; // Oranje
                runButton.style.color = '#333';
                
                if (!refreshIntervalId) { 
                    startAutoRefresh(); 
                }
            } else {
                // HET SCRIPT IS GESTOPT
                runButton.disabled = false;
                runButton.textContent = '▶️ Start Sync';
                runButton.style.backgroundColor = '#28a745'; // Groen
                runButton.style.color = 'white';
                
                if (refreshIntervalId) { 
                    // Stopt de refresh EN maakt de knop weer vrij
                    stopAutoRefresh(); 
                }
            }
        })
        .catch(error => {
            console.error("Fout bij controleren sync status:", error);
            // Optioneel: toon een fout op de pagina als de statuscheck faalt
        });
}

// --- PAGINA INITIALISATIE ---

// 1. Laad de logs bij de start
loadLogs();

// 2. Start de statuscheck interval (om de 2 seconden)
checkSyncStatus();
setInterval(checkSyncStatus, 2000); 

// 3. Controleer de URL parameters voor de initiële status (na knopklik)
const urlParams = new URLSearchParams(window.location.search);
const status = urlParams.get('status');

// Toon een melding na de klik
if (status === 'started') {
    history.replaceState(null, '', window.location.pathname);
    alert('✅ Synchronisatie is succesvol opgestart. Volg de voortgang hier.');
} else if (status === 'running') {
    history.replaceState(null, '', window.location.pathname);
    alert('⚠️ Let op: De synchronisatie loopt al. De knop is uitgeschakeld totdat het proces is voltooid.');
}