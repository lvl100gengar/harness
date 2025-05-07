// DOM Elements
const refreshRateSelect = document.getElementById('refresh-rate');
const displayCountSelect = document.getElementById('display-count');
const pauseButton = document.getElementById('pause-button');
const inTransitBody = document.getElementById('in-transit-body');
const completedBody = document.getElementById('completed-body');
const ingressStatus = document.getElementById('ingress-status');
const egressStatus = document.getElementById('egress-status');

// State
let isPaused = false;
let updateInterval;

// Utility Functions
function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString();
}

function formatDuration(seconds) {
    if (!seconds) return '0.00s';
    if (seconds < 60) {
        return seconds.toFixed(2) + 's';
    } else if (seconds < 3600) {
        return (seconds / 60).toFixed(2) + 'm';
    } else {
        return (seconds / 3600).toFixed(2) + 'h';
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0.00 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
}

function getStatusClass(status) {
    switch (status) {
        case 'SUCCESS':
            return 'status-success';
        case 'FAILED':
            return 'status-failed';
        case 'TIMEOUT':
            return 'status-timeout';
        case 'IN_TRANSIT':
            return 'status-in-transit';
        default:
            return '';
    }
}

function updateDatabaseStatus(statusElement, status) {
    if (!statusElement) return;
    
    const indicator = statusElement.querySelector('.status-indicator');
    const label = statusElement.querySelector('.status-label');
    if (!indicator || !label) return;
    
    // Update indicator class with enhanced styling
    indicator.className = 'status-indicator w-2 h-2 rounded-full mr-1.5 ' + 
        (status.connected ? 'bg-green-500 shadow-sm shadow-green-200' : 'bg-red-500 shadow-sm shadow-red-200');
    
    // Update host display
    label.textContent = status.host || 'Unknown Host';
}

// Add this utility function for copying text
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Show a temporary success message
        const toast = document.createElement('div');
        toast.className = 'fixed bottom-4 right-4 bg-green-500 text-white px-4 py-2 rounded shadow-lg transition-opacity duration-500';
        toast.textContent = 'UUID copied to clipboard';
        document.body.appendChild(toast);
        
        // Remove the toast after 2 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy text: ', err);
    });
}

function createInTransitRow(transaction) {
    const row = document.createElement('tr');
    row.className = 'transaction-row hover:bg-gray-50 transition-colors duration-150';
    
    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm font-medium text-gray-900">${transaction.username}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-900 truncate-text max-w-xs">${transaction.filename}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatBytes(transaction.file_size)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatDateTime(transaction.start_time)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatDuration(transaction.duration_so_far)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800 animate-pulse">
                IN TRANSIT
            </span>
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
            <button onclick="copyToClipboard('${transaction.uuid}')" 
                    class="text-indigo-600 hover:text-indigo-900 inline-flex items-center gap-1 focus:outline-none">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                          d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/>
                </svg>
                <span>Copy UUID</span>
            </button>
        </td>
    `;

    return row;
}

function createCompletedRow(transaction) {
    const row = document.createElement('tr');
    row.className = 'transaction-row hover:bg-gray-50 transition-colors duration-150';
    
    const statusClasses = {
        'SUCCESS': 'bg-green-100 text-green-800',
        'FAILED': 'bg-red-100 text-red-800',
        'TIMEOUT': 'bg-yellow-100 text-yellow-800'
    };
    
    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm font-medium text-gray-900">${transaction.username}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-900 truncate-text max-w-xs">${transaction.filename}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatBytes(transaction.file_size)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatDateTime(transaction.start_time)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <div class="text-sm text-gray-500">${formatDuration(transaction.duration)}</div>
        </td>
        <td class="px-6 py-4 whitespace-nowrap">
            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${statusClasses[transaction.status] || 'bg-gray-100 text-gray-800'}">
                ${transaction.status}
            </span>
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
            <button onclick="copyToClipboard('${transaction.uuid}')" 
                    class="text-indigo-600 hover:text-indigo-900 inline-flex items-center gap-1 focus:outline-none">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                          d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/>
                </svg>
                <span>Copy UUID</span>
            </button>
        </td>
    `;

    return row;
}

// Metrics calculation
function calculateMetrics(transactions) {
    const now = new Date();
    const fiveMinutesAgo = new Date(now - 5 * 60 * 1000);
    
    // Split transactions
    const completed = transactions.completed || [];
    const inTransit = transactions.in_transit || [];
    
    // Calculate in-transit metrics
    const filesInTransit = inTransit.length;
    const bytesInTransit = inTransit.reduce((sum, t) => sum + (parseInt(t.file_size) || 0), 0);
    
    // Calculate completed metrics within 5-minute window
    const recentCompleted = completed.filter(t => {
        const endTime = new Date(t.end_time);
        return endTime >= fiveMinutesAgo;
    });
    
    // Calculate rates
    let filesPerMinute = 0;
    let bytesPerSecond = 0;
    let avgProcessingTime = 0;
    
    if (recentCompleted.length > 0) {
        // Find oldest completion time using timestamps
        const oldestTimestamp = Math.min(...recentCompleted.map(t => new Date(t.end_time).getTime()));
        const timeSpanMinutes = Math.max((now.getTime() - oldestTimestamp) / (1000 * 60), 0.1);
        
        filesPerMinute = recentCompleted.length / timeSpanMinutes;
        
        const totalBytes = recentCompleted.reduce((sum, t) => sum + (parseInt(t.file_size) || 0), 0);
        bytesPerSecond = totalBytes / (timeSpanMinutes * 60);
        
        const processingTimes = recentCompleted
            .map(t => {
                const endTime = new Date(t.end_time).getTime();
                const startTime = new Date(t.start_time).getTime();
                return (endTime - startTime) / 1000;
            })
            .filter(t => t > 0);
        
        if (processingTimes.length > 0) {
            avgProcessingTime = processingTimes.reduce((a, b) => a + b, 0) / processingTimes.length;
        }
    }
    
    // Calculate totals
    const totalFiles = completed.length;
    const totalBytes = completed.reduce((sum, t) => sum + (parseInt(t.file_size) || 0), 0);
    
    return {
        files_in_transit: filesInTransit,
        bytes_in_transit: bytesInTransit,
        files_per_minute: filesPerMinute,
        bytes_per_second: bytesPerSecond,
        avg_processing_time: avgProcessingTime,
        total_files_processed: totalFiles,
        total_bytes_processed: totalBytes
    };
}

function formatRate(value) {
    return value.toFixed(2);
}

function updateMetricsDisplay(metrics) {
    function updateValue(elementId, newValue, formatter = (x) => x.toFixed(0)) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const formattedNewValue = formatter(newValue);
        const currentValue = element.textContent;
        
        if (currentValue !== formattedNewValue) {
            // Create a wrapper for the transition if it doesn't exist
            let wrapper = element.querySelector('.value-wrapper');
            if (!wrapper) {
                element.innerHTML = '<span class="value-wrapper">' + currentValue + '</span>';
                wrapper = element.querySelector('.value-wrapper');
                wrapper.style.transition = 'opacity 0.15s ease-out';
            }
            
            // Quick fade out
            wrapper.style.opacity = '0.7';
            
            // Update value and fade in
            setTimeout(() => {
                wrapper.textContent = formattedNewValue;
                wrapper.style.opacity = '1';
            }, 150);
        }
    }
    
    // Update each metric with appropriate formatting
    updateValue('files-in-transit', metrics.files_in_transit);
    updateValue('bytes-in-transit', metrics.bytes_in_transit, formatBytes);
    updateValue('files-per-minute', metrics.files_per_minute, formatRate);
    updateValue('bytes-per-second', metrics.bytes_per_second, (x) => formatBytes(x) + '/s');
    updateValue('avg-processing-time', metrics.avg_processing_time, formatDuration);
    updateValue('total-files', metrics.total_files_processed);
    updateValue('total-bytes', metrics.total_bytes_processed, formatBytes);
    
    // Update last update time with subtle fade
    const lastUpdate = document.getElementById('metrics-last-update');
    if (lastUpdate) {
        lastUpdate.style.opacity = '0.7';
        setTimeout(() => {
            lastUpdate.textContent = new Date().toLocaleTimeString();
            lastUpdate.style.opacity = '1';
        }, 150);
    }
}

// API Functions
async function fetchDatabaseStatus() {
    try {
        const response = await fetch('/api/status');
        const [ingressStatusData, egressStatusData] = await response.json();
        
        updateDatabaseStatus(ingressStatus, ingressStatusData);
        updateDatabaseStatus(egressStatus, egressStatusData);
    } catch (error) {
        console.error('Failed to fetch database status:', error);
    }
}

async function fetchTransactions() {
    if (isPaused) return;

    const limit = displayCountSelect.value;
    inTransitBody.classList.add('loading');
    completedBody.classList.add('loading');

    try {
        const response = await fetch(`/api/transactions?limit=${limit}`);
        const data = await response.json();

        // Update in-transit transactions
        inTransitBody.innerHTML = '';
        data.in_transit.forEach(transaction => {
            inTransitBody.appendChild(createInTransitRow(transaction));
        });

        // Update completed transactions
        completedBody.innerHTML = '';
        data.completed.forEach(transaction => {
            completedBody.appendChild(createCompletedRow(transaction));
        });

        // Calculate and update metrics
        const metrics = calculateMetrics(data);
        updateMetricsDisplay(metrics);
    } catch (error) {
        console.error('Failed to fetch transactions:', error);
    } finally {
        inTransitBody.classList.remove('loading');
        completedBody.classList.remove('loading');
    }
}

// Event Handlers
function updateRefreshInterval() {
    if (updateInterval) {
        clearInterval(updateInterval);
    }

    const refreshRate = parseInt(refreshRateSelect.value) * 1000;
    updateInterval = setInterval(() => {
        fetchTransactions();
        fetchDatabaseStatus();
    }, refreshRate);
}

refreshRateSelect.addEventListener('change', updateRefreshInterval);

displayCountSelect.addEventListener('change', () => {
    fetchTransactions();
});

pauseButton.addEventListener('click', () => {
    isPaused = !isPaused;
    pauseButton.textContent = isPaused ? 'Resume' : 'Pause';
    pauseButton.classList.toggle('bg-indigo-600');
    pauseButton.classList.toggle('bg-gray-600');
    
    if (!isPaused) {
        fetchTransactions();
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchTransactions();
    fetchDatabaseStatus();
    updateRefreshInterval();
}); 