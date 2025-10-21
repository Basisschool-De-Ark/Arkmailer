// log_viewer_drag_drop.js

let allLogLines = []; 
const dropZone = document.getElementById('dropZone');
const logContainer = document.getElementById('logContainer');
const logArea = document.getElementById('logArea'); // De scrollcontainer
const fileInput = document.getElementById('fileInput');

// --- DRAG & DROP EVENT HANDLERS ---

// Zorg ervoor dat de browser het bestand niet opent
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => e.preventDefault());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        readFile(files[0]);
    }
});

// Klik op de zone opent de file selector
dropZone.addEventListener('click', () => {
    fileInput.click();
});

// Lees bestand na handmatige selectie
fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        readFile(files[0]);
    }
});

// --- CORE FUNCTIES ---

// 1. Logbestand inlezen vanuit de browser
function readFile(file) {
    const reader = new FileReader();
    
    reader.onload = (e) => {
        const text = e.target.result;
        
        // Verwerk het ingelezen bestand
        allLogLines = text.trim().split('\n').filter(line => line.trim() !== '');
        allLogLines.reverse(); // Nieuwste bovenaan
        
        document.getElementById('lineCount').textContent = `Totaal regels: ${allLogLines.length}`;
        
        // Verberg de dropzone en toon de container
        dropZone.classList.add('hidden');
        logContainer.style.display = 'block'; 
        
        // Initialiseer datum en toon logs
        initDateInput();
        filterLogs();
    };
    
    reader.onerror = () => {
        logContainer.innerHTML = '<p style="color: red;">❌ FOUT: Kan het bestand niet lezen.</p>';
    };
    
    reader.readAsText(file);
}


// Functie om de datumkiezer in te stellen op de datum van vandaag (YYYY-MM-DD)
function initDateInput() {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); 
    const dd = String(today.getDate()).padStart(2, '0');
    
    const formattedDate = `${yyyy}-${mm}-${dd}`;
    document.getElementById('filterDate').value = formattedDate;
}

// Logs weergeven op de pagina
function displayLogs(lines) {
    logContainer.innerHTML = ''; 

    if (lines.length === 0) {
        logContainer.innerHTML = '<p>Geen loglijnen gevonden voor deze selectie.</p>';
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

        logContainer.appendChild(logElement);
    });
}

// Filter logs op niveau, zoekterm én DATUM
function filterLogs() {
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

// Initialisatie van de datum bij het laden van de pagina
initDateInput();