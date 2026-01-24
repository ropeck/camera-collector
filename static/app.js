/**
 * Beach Sunrise/Sunset Gallery Application
 *
 * Single-page app for browsing and playing monthly video compilations.
 */

// DOM Elements
const loadingEl = document.getElementById('loading');
const monthsGridEl = document.getElementById('months-grid');
const videoPlayerEl = document.getElementById('video-player');
const playerTitleEl = document.getElementById('player-title');
const closePlayerBtn = document.getElementById('close-player');
const videoEl = document.getElementById('video');
const videoSourceEl = document.getElementById('video-source');
const playerLoadingEl = document.getElementById('player-loading');
const playerLoadingTextEl = document.getElementById('player-loading-text');
const playerMetaEl = document.getElementById('player-meta');
const yearFilterEl = document.getElementById('year-filter');
const timeFilterEl = document.getElementById('time-filter');

// State
let monthsData = [];
let currentFilter = {
    year: '',
    time: ''
};

// Month names for display
const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

/**
 * Format duration in seconds to MM:SS
 */
function formatDuration(seconds) {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format file size to human readable
 */
function formatSize(bytes) {
    if (!bytes) return '--';
    const mb = bytes / (1024 * 1024);
    if (mb < 1000) {
        return `${mb.toFixed(1)} MB`;
    }
    return `${(mb / 1024).toFixed(2)} GB`;
}

/**
 * Get collage thumbnail URL for a month
 */
function getCollageUrl(year, month, timeFilter) {
    const filter = timeFilter ? `-${timeFilter}` : '';
    return `https://storage.googleapis.com/fogcat-webcam/${year}/${month.toString().padStart(2, '0')}/collages/collage-${year}-${month.toString().padStart(2, '0')}${filter}-5x6.jpg`;
}

/**
 * Fetch available months from API
 */
async function fetchMonths() {
    try {
        const response = await fetch('/api/months');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.months || [];
    } catch (error) {
        console.error('Error fetching months:', error);
        throw error;
    }
}

/**
 * Generate or retrieve a compilation
 */
async function generateCompilation(year, month, timeFilter) {
    const params = new URLSearchParams({
        year: year.toString(),
        month: month.toString()
    });
    if (timeFilter) {
        params.append('time_filter', timeFilter);
    }

    const response = await fetch(`/api/compilation/generate?${params}`, {
        method: 'POST'
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate compilation');
    }

    return response.json();
}

/**
 * Create a month card element
 */
function createMonthCard(monthData) {
    const card = document.createElement('div');
    card.className = 'month-card';
    card.dataset.year = monthData.year;
    card.dataset.month = monthData.month;

    const monthName = monthNames[monthData.month - 1];
    const collageUrl = getCollageUrl(monthData.year, monthData.month, currentFilter.time || null);

    card.innerHTML = `
        <div class="thumbnail">
            <img src="${collageUrl}" alt="${monthName} ${monthData.year}"
                 onerror="this.parentElement.innerHTML='<div class=\\'placeholder\\'>&#127749;</div>'">
        </div>
        <div class="info">
            <div class="month-title">${monthName} ${monthData.year}</div>
            <div class="counts">
                <div class="count-item sunrise" title="Sunrise videos">
                    &#127749; ${monthData.sunrise_count}
                </div>
                <div class="count-item sunset" title="Sunset videos">
                    &#127751; ${monthData.sunset_count}
                </div>
            </div>
            <div class="compilation-status">
                ${monthData.has_sunrise_compilation ? '<span class="badge cached">Sunrise ready</span>' : ''}
                ${monthData.has_sunset_compilation ? '<span class="badge cached">Sunset ready</span>' : ''}
                ${monthData.has_all_compilation ? '<span class="badge cached">All ready</span>' : ''}
                ${!monthData.has_sunrise_compilation && !monthData.has_sunset_compilation && !monthData.has_all_compilation ? '<span class="badge not-cached">Not compiled</span>' : ''}
            </div>
            <div class="actions">
                <button class="action-btn sunrise" data-filter="sunrise" title="Play sunrise compilation">
                    &#127749; Sunrise
                </button>
                <button class="action-btn sunset" data-filter="sunset" title="Play sunset compilation">
                    &#127751; Sunset
                </button>
                <button class="action-btn all" data-filter="" title="Play all videos">
                    All
                </button>
            </div>
        </div>
    `;

    // Add click handlers for action buttons
    card.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const filter = btn.dataset.filter || null;
            playCompilation(monthData.year, monthData.month, filter);
        });
    });

    return card;
}

/**
 * Render the months grid
 */
function renderMonths() {
    monthsGridEl.innerHTML = '';

    // Filter months based on current filters
    let filtered = monthsData;

    if (currentFilter.year) {
        filtered = filtered.filter(m => m.year.toString() === currentFilter.year);
    }

    if (currentFilter.time === 'sunrise') {
        filtered = filtered.filter(m => m.sunrise_count > 0);
    } else if (currentFilter.time === 'sunset') {
        filtered = filtered.filter(m => m.sunset_count > 0);
    }

    if (filtered.length === 0) {
        monthsGridEl.innerHTML = `
            <div class="empty-state">
                <h3>No videos found</h3>
                <p>Try adjusting your filters</p>
            </div>
        `;
        return;
    }

    filtered.forEach(monthData => {
        monthsGridEl.appendChild(createMonthCard(monthData));
    });
}

/**
 * Populate year filter dropdown
 */
function populateYearFilter() {
    const years = [...new Set(monthsData.map(m => m.year))].sort((a, b) => b - a);

    yearFilterEl.innerHTML = '<option value="">All Years</option>';
    years.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearFilterEl.appendChild(option);
    });
}

/**
 * Play a compilation video
 */
async function playCompilation(year, month, timeFilter) {
    const monthName = monthNames[month - 1];
    const filterName = timeFilter === 'sunrise' ? 'Sunrises' :
                       timeFilter === 'sunset' ? 'Sunsets' : 'All Videos';

    playerTitleEl.textContent = `${monthName} ${year} - ${filterName}`;
    videoPlayerEl.classList.remove('hidden');
    playerLoadingEl.classList.remove('hidden');
    playerLoadingTextEl.textContent = 'Loading compilation...';
    videoEl.style.display = 'none';
    playerMetaEl.innerHTML = '';

    // Scroll to player
    videoPlayerEl.scrollIntoView({ behavior: 'smooth' });

    try {
        const result = await generateCompilation(year, month, timeFilter);

        // Update meta info
        playerMetaEl.innerHTML = `
            <div class="meta-item">
                <span class="meta-label">Videos:</span> ${result.video_count || '--'}
            </div>
            <div class="meta-item">
                <span class="meta-label">Duration:</span> ${formatDuration(result.duration_seconds)}
            </div>
            <div class="meta-item">
                <span class="meta-label">Size:</span> ${formatSize(result.size_bytes)}
            </div>
            <div class="meta-item">
                <span class="meta-label">Status:</span> ${result.cached ? 'Cached' : 'Generated'}
            </div>
        `;

        // Load video
        videoSourceEl.src = result.url;
        videoEl.load();
        videoEl.style.display = 'block';
        playerLoadingEl.classList.add('hidden');

        // Auto-play
        videoEl.play().catch(err => {
            console.log('Auto-play prevented:', err);
        });

    } catch (error) {
        console.error('Error loading compilation:', error);
        playerLoadingTextEl.textContent = `Error: ${error.message}`;
    }
}

/**
 * Close the video player
 */
function closePlayer() {
    videoEl.pause();
    videoPlayerEl.classList.add('hidden');
}

/**
 * Initialize the application
 */
async function init() {
    // Set up event listeners
    closePlayerBtn.addEventListener('click', closePlayer);

    yearFilterEl.addEventListener('change', (e) => {
        currentFilter.year = e.target.value;
        renderMonths();
    });

    timeFilterEl.addEventListener('change', (e) => {
        currentFilter.time = e.target.value;
        renderMonths();
    });

    // Allow closing player with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !videoPlayerEl.classList.contains('hidden')) {
            closePlayer();
        }
    });

    // Fetch and display months
    try {
        monthsData = await fetchMonths();
        populateYearFilter();
        loadingEl.style.display = 'none';
        renderMonths();
    } catch (error) {
        loadingEl.innerHTML = `
            <div class="error-state">
                <h3>Failed to load gallery</h3>
                <p>${error.message}</p>
                <button onclick="location.reload()">Retry</button>
            </div>
        `;
    }
}

// Start the app when DOM is ready
document.addEventListener('DOMContentLoaded', init);
