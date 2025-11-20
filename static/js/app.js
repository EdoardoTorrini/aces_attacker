const rsuLat = 44.652986;
const rsuLon = 10.929981;
const zoom = 17;


const emergencyIcon = new L.Icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

const map = L.map('map').setView([rsuLat, rsuLon], zoom);
const vehicleLayerGroup = L.layerGroup().addTo(map);
const fixedRSUMarker = L.marker([rsuLat, rsuLon], { icon: emergencyIcon }).addTo(map).bindPopup("<b>Road Site Unit</b>")

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

// ----- Selettori Elementi DOM -----
const speedEl = document.getElementById('speed-data');
const latEl = document.getElementById('lat-data');
const lonEl = document.getElementById('lon-data');
const headingEl = document.getElementById('heading-data');

const redLight = document.getElementById('light-red');
const yellowLight = document.getElementById('light-yellow');
const greenLight = document.getElementById('light-green');

// Classi CSS per le luci (definite con Tailwind)
const lightBaseClass = "w-16 h-16 rounded-full border-2 border-gray-700 m-2 transition-all duration-300";
const lightOff = "bg-gray-700";
const redOn = "bg-red-500 shadow-lg shadow-red-500/50";
const yellowOn = "bg-yellow-500 shadow-lg shadow-yellow-500/50";
const greenOn = "bg-green-500 shadow-lg shadow-green-500/50";


function updateMap(data) {
    if (data == null || data.msg != "ok") {
    	return;
    }
    // Pulisce la mappa
    vehicleLayerGroup.clearLayers();

    // Controlla se i dati OBU sono validi
    if (!data || data.lat == null || data.lon == null || !data.vehicle_id) {
        console.warn("Dati telemetrici incompleti o non validi:", data);
        // Pulisce i campi di testo
        speedEl.innerText = 'N/A';
        latEl.innerText = 'N/A';
        lonEl.innerText = 'N/A';
	headingEl.innerText = 'N/A';
        return;
    }

    const icon = L.icon({
        iconUrl: '/static/img/car.png',
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, 16],
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        shadowSize: [41, 41]
    });
    
    const newMarker = L.marker([data.lat, data.lon], { icon: icon });
    
    vehicleLayerGroup.addLayer(newMarker);

    // Aggiorna i campi di testo OBU
    speedEl.innerText = data.speed + ' km/h';
    latEl.innerText = data.lat.toFixed(6);
    lonEl.innerText = data.lon.toFixed(6);
    headingEl.innerText = data.heading + '°';
}

function updateTrafficLight(data) {
    // NOTA: Uso 'sub_cause_code' come definito nel tuo main.py
    const code = data ? data.sub_cause_code : null;

    if ((code === -1) || (code === null)) {
    	return;
    }

    // Resetta tutte le luci allo stato "spento"
    redLight.className = `${lightBaseClass} ${lightOff}`;
    yellowLight.className = `${lightBaseClass} ${lightOff}`;
    greenLight.className = `${lightBaseClass} ${lightOff}`;

    // Accende la luce corretta
    if (code === 1) {
        greenLight.className = `${lightBaseClass} ${greenOn}`;
    } else if (code === 2) {
        yellowLight.className = `${lightBaseClass} ${yellowOn}`;
    } else if (code === 3) {
        redLight.className = `${lightBaseClass} ${redOn}`;
    }
    // Se il codice è null o non corrisponde, restano tutte spente
}


async function fetchTelemetryData() {
    try {
        const response = await fetch('/obu');
        if (!response.ok) {
            throw new Error(`Errore HTTP: ${response.status}`);
        }
        const data = await response.json();
        
        updateMap(data);
        
    } catch (error) {
        console.error("Impossibile recuperare i dati di telemetria (OBU):", error);
        updateMap(null); // Pulisce la mappa e i campi in caso di errore
    }
}

async function fetchRsuData() {
    try {
        const response = await fetch('/rsu');
        if (!response.ok) {
            // Se non ci sono dati (404), non è un errore, solo nessun aggiornamento
            if (response.status === 404) {
                console.log("Nessun nuovo dato RSU.");
                updateTrafficLight(null); // Spegne le luci se non ci sono dati
                return;
            }
            throw new Error(`Errore HTTP: ${response.status}`);
        }
        const data = await response.json();
        
        updateTrafficLight(data);
        
    } catch (error) {
        console.error("Impossibile recuperare i dati RSU (DENM):", error);
        updateTrafficLight(null); // Spegne le luci in caso di errore
    }
}

async function startAttack() {
    const attack_type = document.getElementById('attack_type');
    console.log(attack_type.options[attack_type.selectedIndex].value);
    var a_id = attack_type.options[attack_type.selectedIndex].value;
    const response = await fetch("/start_attack", {
	method: "POST",
	headers: {"Content-Type": "application/json"},
	body: JSON.stringify({attack_id: a_id})
    })
    attack_type.value = "";
}

// Polling OBU: ogni 2 secondi
setInterval(fetchTelemetryData, 500);

// Polling RSU: ogni 2 secondi
setInterval(fetchRsuData, 500);

// Chiamate iniziali per caricare i dati al caricamento della pagina
fetchTelemetryData();
fetchRsuData();
