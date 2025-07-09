// Update System Status
function updateSystemStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            document.getElementById('telegram-status-text').textContent = 
                data.telegram_connected ? 'Connected' : 'Disconnected';
            document.getElementById('mt5-status-text').textContent = 
                data.mt5_connected ? 'Connected' : 'Disconnected';
            document.getElementById('signal-status-text').textContent = 
                data.signal_parser_active ? 'Active' : 'Inactive';
        });
}

// Load Initial Trades
function loadInitialTrades() {
    fetch('/api/trades')
        .then(response => response.json())
        .then(trades => {
            const tbody = document.getElementById('trades-table-body');
            tbody.innerHTML = '';
            
            trades.forEach(trade => {
                addTradeToTable(trade);
            });
            updateMetrics();
        });
}

// Add Single Trade to Table
function addTradeToTable(trade) {
    const row = document.createElement('tr');
    row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
            ${new Date(trade.timestamp).toLocaleTimeString()}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
            ${trade.symbol}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm ${trade.action === 'BUY' ? 'text-green-600' : 'text-red-600'}">
            ${trade.action}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
            ${trade.entry_price}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
            ${trade.stop_loss}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
            ${trade.take_profit_1}
        </td>
        <td class="px-6 py-4 whitespace-nowrap text-sm">
            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                ${trade.status === 'SUCCESS' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                ${trade.status}
            </span>
        </td>
    `;
    document.getElementById('trades-table-body').prepend(row);
}

// Update Performance Metrics
function updateMetrics() {
    fetch('/api/trades')
        .then(response => response.json())
        .then(trades => {
            const total = trades.length;
            const success = trades.filter(t => t.status === 'SUCCESS').length;
            const winRate = total > 0 ? Math.round((success / total) * 100) : 0;
            
            document.getElementById('total-trades').textContent = total;
            document.getElementById('success-trades').textContent = success;
            document.getElementById('failed-trades').textContent = total - success;
            document.getElementById('win-rate').textContent = `${winRate}%`;
        });
}

// Initialize everything
document.addEventListener('DOMContentLoaded', () => {
    updateSystemStatus();
    loadInitialTrades();
    
    // Refresh status every 10 seconds
    setInterval(updateSystemStatus, 10000);
    
    // Set up EventSource for real-time updates
    const eventSource = new EventSource('/stream');
    eventSource.onmessage = (e) => {
        const trade = JSON.parse(e.data);
        addTradeToTable(trade);
        updateMetrics();
    };
});