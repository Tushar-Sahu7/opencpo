// ── Session Resumption ──────────────────────────────────────────
(function () {
  var sid = localStorage.getItem('active_session_id');
  if (!sid) return;
  fetch('/api/sessions/' + sid + '/poll')
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (s && (s.mollie_status === 'paid' || s.mollie_status === 'authorized') && !s.stopped_at) {
        window.location.href = '/session/' + sid;
      } else {
        localStorage.removeItem('active_session_id');
      }
    })
    .catch(function () { localStorage.removeItem('active_session_id'); });
})();

// ── Hash-based tab switching (scan tab via /#scan) ───────────────────────
var scannerActive = false;

function checkHashTab() {
  var hash = location.hash;
  var mapTab = document.getElementById('tab-map');
  var scanTab = document.getElementById('tab-scan');
  if (!mapTab || !scanTab) return;

  if (hash === '#scan') {
    mapTab.classList.add('hidden');
    scanTab.classList.remove('hidden');
    startScanner();
  } else {
    scanTab.classList.add('hidden');
    mapTab.classList.remove('hidden');
    stopScanner();
    if (map) setTimeout(function () { map.invalidateSize(); }, 100);
  }
}

window.addEventListener('hashchange', checkHashTab);

// ── Pin SVG ─────────────────────────────────────────────────────
function pinSVG(color) {
  return '<svg width="32" height="40" viewBox="0 0 32 40" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M16 0C7.163 0 0 7.163 0 16c0 10.667 16 24 16 24S32 26.667 32 16C32 7.163 24.837 0 16 0z" fill="' + color + '" fill-opacity="0.92"/>' +
    '<circle cx="16" cy="16" r="9" fill="rgba(255,255,255,0.15)"/>' +
    '<circle cx="16" cy="16" r="6" fill="white" fill-opacity="0.9"/>' +
    '<circle cx="16" cy="16" r="3.5" fill="' + color + '"/>' +
    '</svg>';
}

function statusColor(status) {
  if (!status) return '#64748b';
  var s = (status + '').toLowerCase();
  if (s === 'available') return '#22c55e';
  if (s === 'charging' || s === 'occupied') return '#00B0E4';
  if (s === 'faulted') return '#ef4444';
  return '#64748b';
}

// ── Map ─────────────────────────────────────────────────────────
var map, userMarker, chargerLayer, tileLayer;
var chargerCache = { data: null, ts: 0 };
var CACHE_TTL = 30000;
var fetchDebounce = null;
var isDark = true;

var TILE_DARK  = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
var TILE_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
var TILE_ATTR  = '&copy; <a href="https://stadiamaps.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OSM</a>';

function initMap() {
  map = L.map('charger-map', {
    center: [52.3942, 4.8666],
    zoom: 14,
    zoomControl: false,
    attributionControl: true,
  });

  tileLayer = L.tileLayer(TILE_DARK, { attribution: TILE_ATTR, maxZoom: 19 });
  tileLayer.addTo(map);
  chargerLayer = L.layerGroup().addTo(map);

  map.on('moveend', scheduleFetch);
  map.on('zoomend', scheduleFetch);
  map.on('click', closeSheet);

  document.getElementById('zoom-in').addEventListener('click', function () { map.zoomIn(); });
  document.getElementById('zoom-out').addEventListener('click', function () { map.zoomOut(); });
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('geo-btn').addEventListener('click', locateUser);
  document.getElementById('locate-banner-btn').addEventListener('click', locateUser);
  document.getElementById('sheet-handle').addEventListener('click', closeSheet);

  // Show locate banner, let user trigger location manually
  document.getElementById('locate-banner').classList.remove('hidden');
  fetchNearby();
}

function toggleTheme() {
  isDark = !isDark;
  tileLayer.setUrl(isDark ? TILE_DARK : TILE_LIGHT);
}

function scheduleFetch() {
  clearTimeout(fetchDebounce);
  fetchDebounce = setTimeout(fetchNearby, 500);
}

function fetchNearby() {
  if (!map) return;
  var center = map.getCenter();
  var bounds = map.getBounds();
  var ne = bounds.getNorthEast();
  var sw = bounds.getSouthWest();
  var latDiff = Math.abs(ne.lat - sw.lat) / 2;
  var lngDiff = Math.abs(ne.lng - sw.lng) / 2;
  var radiusKm = Math.sqrt(latDiff * latDiff + lngDiff * lngDiff) * 111;
  var radius = Math.min(Math.round(radiusKm * 1000), 5000);

  var now = Date.now();
  if (chargerCache.data && (now - chargerCache.ts) < CACHE_TTL) {
    renderChargers(chargerCache.data);
    return;
  }

  var loading = document.getElementById('map-loading');
  loading.style.display = 'flex';

  var url = '/api/chargers/nearby?lat=' + center.lat + '&lng=' + center.lng + '&radius=' + radius;
  fetch(url)
    .then(function (r) {
      if (!r.ok) throw new Error('API error ' + r.status);
      return r.json();
    })
    .then(function (data) {
      chargerCache = { data: data, ts: Date.now() };
      renderChargers(data);
    })
    .catch(function (e) {
      console.error('Charger fetch failed:', e);
    })
    .finally(function () {
      loading.style.display = 'none';
    });
}

function renderChargers(data) {
  chargerLayer.clearLayers();
  var chargers = Array.isArray(data) ? data : (data.chargers || data.results || []);

  chargers.forEach(function (cp) {
    var lat = cp.lat || cp.latitude;
    var lng = cp.lng || cp.longitude;
    if (lat == null || lng == null) return;

    var connectors = cp.connectors || [];
    var firstConn = connectors[0];
    var firstStatus = firstConn ? firstConn.status : cp.status;
    var color = statusColor(firstStatus || cp.status);

    var icon = L.divIcon({
      className: 'charger-marker-wrap',
      html: '<div class="pin-marker pin-pulse">' + pinSVG(color) + '</div>',
      iconSize: [32, 40],
      iconAnchor: [16, 40],
      popupAnchor: [0, -44],
    });

    var marker = L.marker([lat, lng], { icon: icon });
    marker.on('click', (function (charger) {
      return function (e) {
        L.DomEvent.stopPropagation(e);
        openSheet(charger);
      };
    })(cp));
    marker.addTo(chargerLayer);
  });

  var badge = document.getElementById('charger-badge');
  var I18N = window.I18N || {};
  badge.textContent = '⚡ ' + chargers.length + ' ' + (chargers.length === 1 ? (I18N.charger_singular || 'lader') : (I18N.chargers_badge || 'laders'));
  badge.style.opacity = '1';
  setTimeout(function () { badge.style.opacity = '0'; }, 5000);
}

function locateUser() {
  if (!navigator.geolocation) {
    document.getElementById('locate-banner').classList.remove('hidden');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      var lat = pos.coords.latitude;
      var lng = pos.coords.longitude;

      if (userMarker) userMarker.remove();
      var userIcon = L.divIcon({
        className: 'charger-marker-wrap',
        html: '<div class="user-dot-outer"><div class="user-dot-inner"></div></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });
      userMarker = L.marker([lat, lng], { icon: userIcon, zIndexOffset: 1000 }).addTo(map);

      map.setView([lat, lng], 15);
      document.getElementById('locate-banner').classList.add('hidden');
    },
    function () {
      document.getElementById('locate-banner').classList.remove('hidden');
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

// ── Distance helper ─────────────────────────────────────────────
function distTo(lat, lng) {
  if (!userMarker) return null;
  var u = userMarker.getLatLng();
  var R = 6371000;
  var dLat = (lat - u.lat) * Math.PI / 180;
  var dLng = (lng - u.lng) * Math.PI / 180;
  var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(u.lat * Math.PI / 180) * Math.cos(lat * Math.PI / 180) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2);
  var d = 2 * R * Math.asin(Math.sqrt(a));
  return d < 1000 ? Math.round(d) + ' m' : (d / 1000).toFixed(1) + ' km';
}

// ── Bottom Sheet ────────────────────────────────────────────────
function openSheet(cp) {
  var lat = cp.lat || cp.latitude;
  var lng = cp.lng || cp.longitude;
  var dist = distTo(lat, lng);
  var connectors = cp.connectors || [];
  var cpId = cp.cp_id || cp.id || '';

  var I18N = window.I18N || {};
  var connHTML = '';
  if (connectors.length > 0) {
    connectors.forEach(function (c) {
      var sc = statusColor(c.status);
      var label = c.status || (I18N.unknown_status || 'Onbekend');
      var cid = c.connector_id || c.id || 1;
      var type = c.type || c.connector_type || '';
      var startBtn = '';
      var canStart = c.status && ['available', 'preparing'].includes(c.status.toLowerCase());
      if (canStart && cpId) {
        var btnLabel = c.status.toLowerCase() === 'preparing' 
          ? (I18N.charge_ready || '✓ Ready →') 
          : (I18N.charge_action || 'Charge →');
        var btnBg = c.status.toLowerCase() === 'preparing' ? '#22c55e' : 'var(--accent)';
        startBtn = '<a href="/charge/' + encodeURIComponent(cpId) + '/' + encodeURIComponent(cid) + '" ' +
          'style="padding:4px 10px;background:' + btnBg + ';color:#0C2340;' +
          'border-radius:6px;font-size:12px;font-weight:700;text-decoration:none;margin-left:8px;">' +
          btnLabel + '</a>';
      }
      connHTML += '<div style="display:flex;align-items:center;justify-content:space-between;' +
        'padding:10px 0;border-bottom:1px solid var(--border);">' +
        '<div style="font-size:14px;font-weight:600;">' + (I18N.connector || 'Connector') + ' ' + cid + (type ? ' \u00b7 ' + type : '') + '</div>' +
        '<div style="display:flex;align-items:center;">' +
        '<div style="width:8px;height:8px;border-radius:50%;background:' + sc + ';margin-right:5px;"></div>' +
        '<span style="font-size:13px;color:' + sc + ';font-weight:600;">' + label + '</span>' +
        startBtn +
        '</div>' +
        '</div>';
    });
  } else {
    connHTML = '<div class="empty-state"><p class="empty-state-text">' +
      (I18N.no_connectors || 'Geen connectoren beschikbaar') + '</p></div>';
  }

  var name = cp.name || cp.site_name || cpId || (I18N.charger || 'Laadpunt');
  var addr = cp.address || cp.location || cp.site_name || '';
  if (addr === name) addr = '';

  var navBtn = (lat && lng)
    ? '<a href="https://www.google.com/maps/dir/?api=1&destination=' + lat + ',' + lng +
      '" target="_blank" rel="noopener" class="sheet-btn sheet-btn-nav">🧭 ' +
      (I18N.navigate || 'Navigeer') + '</a>'
    : '';

  document.getElementById('sheet-content').innerHTML =
    '<div class="sheet-charger-name">' + name + '</div>' +
    (addr ? '<div class="sheet-charger-addr">📍 ' + addr + '</div>' : '') +
    (dist ? '<div class="map-popup-dist">' + dist + ' ' + (I18N.distance_from_you || 'van jou') + '</div>' : '') +
    '<div class="sheet-connector-list">' + connHTML + '</div>' +
    (navBtn ? '<div class="sheet-actions">' + navBtn + '</div>' : '');

  document.getElementById('charger-sheet').classList.add('open');
}

function closeSheet() {
  document.getElementById('charger-sheet').classList.remove('open');
}

// ── QR Scanner ──────────────────────────────────────────────────
var videoStream = null;
var scanInterval = null;
var barcodeDetector = null;

function startScanner() {
  if (scannerActive) return;

  var video = document.getElementById('scan-video');
  var errDiv = document.getElementById('camera-error');
  var status = document.getElementById('scan-status');

  if ('BarcodeDetector' in window) {
    try { barcodeDetector = new BarcodeDetector({ formats: ['qr_code'] }); } catch (e) { barcodeDetector = null; }
  }

  navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }
  })
    .then(function (stream) {
      videoStream = stream;
      video.srcObject = stream;
      errDiv.classList.add('hidden');
      scannerActive = true;

      var I18N = window.I18N || {};
      if (barcodeDetector) {
        status.textContent = I18N.camera_active_qr || 'Camera actief — richt op QR-code';
        scanInterval = setInterval(detectQR, 300);
      } else {
        status.textContent = I18N.camera_active_manual || 'Camera actief — voer code handmatig in';
      }
    })
    .catch(function () {
      var I18N = window.I18N || {};
      errDiv.classList.remove('hidden');
      status.textContent = I18N.camera_no_access || 'Geen cameratoegang';
    });
}

function stopScanner() {
  scannerActive = false;
  clearInterval(scanInterval);
  scanInterval = null;
  if (videoStream) {
    videoStream.getTracks().forEach(function (t) { t.stop(); });
    videoStream = null;
  }
  var video = document.getElementById('scan-video');
  if (video) video.srcObject = null;
}

function detectQR() {
  if (!barcodeDetector || !scannerActive) return;
  var video = document.getElementById('scan-video');
  if (!video || video.readyState < 2) return;

  barcodeDetector.detect(video)
    .then(function (codes) {
      if (codes.length > 0) {
        clearInterval(scanInterval);
        scannerActive = false;
        navigateToCode(codes[0].rawValue);
      }
    })
    .catch(function () { /* silent */ });
}

function submitManualCode() {
  var input = document.getElementById('manual-code');
  var code = input.value.trim();
  if (code) navigateToCode(code);
}

function navigateToCode(code) {
  // If the code is a URL containing /c/, extract just the code part
  var urlMatch = code.match(/\/c\/([^/?#\s]+)/);
  var finalCode = urlMatch ? urlMatch[1] : code;
  window.location.href = '/c/' + encodeURIComponent(finalCode);
}

// ── Init ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  initMap();
  checkHashTab(); // Check if we should start on scan tab

  document.getElementById('manual-submit').addEventListener('click', submitManualCode);
  document.getElementById('manual-code').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') submitManualCode();
  });
});
