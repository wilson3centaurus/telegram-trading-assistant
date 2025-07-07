document.addEventListener('DOMContentLoaded', function() {
    // Initialize the dashboard
    initDashboard();
    
    // Set up periodic updates
    setInterval(updateDashboard, 5000);
});

function initDashboard() {
    updateSystemStatus();
    updateRecentActivity();
    updateTradesTable();
    updatePerformanceMetrics();
}

function updateDashboard() {
    updateSystemStatus();
    updateRecentActivity();
    updateTradesTable();
    updatePerformanceMetrics();
}

function updateSystemStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            updateStatusIndicator('telegram', data.telegram_connected);
            updateStatusIndicator('mt5', data.mt5_connected);
            updateStatusIndicator('signal', data.signal_parser_active);
            
            document.getElementById('telegram-status-text').textContent = 
                data.telegram_connected ? 'Connected' : 'Disconnected';
            document.getElementById('mt5-status-text').textContent = 
                data.mt5_connected ? 'Connected' : 'Disconnected';
            document.getElementById('signal-status-text').textContent = 
                data.signal_parser_active ? 'Active' : 'Inactive';
        })
        .catch(error => {
            console.error('Error fetching system status:', error);
        });
}

function updateStatusIndicator(element, isActive) {
    const indicator = document.getElementById(`${element}-status`);
    if (isActive) {
        indicator.classList.remove('bg-gray-300', 'bg-red-500');
        indicator.classList.add('bg-green-500');
    } else {
        indicator.classList.remove('bg-gray-300', 'bg-green-500');
        indicator.classList.add('bg-red-500');
    }
}

function updateRecentActivity() {
    fetch('/api/trades?limit=3')
        .then(response => response.json())
        .then(trades => {
            const activityContainer = document.getElementById('recent-activity');
            activityContainer.innerHTML = '';
            
            if (trades.length === 0) {
                activityContainer.innerHTML = `
                    <div class="text-center py-4">
                        <p class="text-gray-500">No recent activity</p>
                    </div>
                `;
                return;
            }
            
            trades.forEach(trade => {
                const activityItem = document.createElement('div');
                activityItem.className = 'flex items-start py-2 border-b border-gray-100 last:border-0';
                
                const icon = document.createElement('div');
                icon.className = `flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center mr-3 ${
                    trade.status === 'SUCCESS' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'
                }`;
                icon.innerHTML = `<i class="fas fa-${
                    trade.action === 'BUY' ? 'arrow-up' : 'arrow-down'
                }"></i>`;
                
                const content = document.createElement('div');
                content.className = 'flex-1';
                
                const title = document.createElement('p');
                title.className = 'text-sm font-medium';
                title.textContent = `${trade.action} ${trade.symbol}`;
                
                const details = document.createElement('p');
                details.className = 'text-xs text-gray-500';
                details.textContent = `Entry: ${trade.entry_price} | SL: ${trade.stop_loss} | TP1: ${trade.take_profit_1}`;
                
                const time = document.createElement('p');
                time.className = 'text-xs text-gray-400 mt-1';
                time.textContent = new Date(trade.timestamp).toLocaleString();
                
                content.appendChild(title);
                content.appendChild(details);
                content.appendChild(time);
                
                activityItem.appendChild(icon);
                activityItem.appendChild(content);
                
                activityContainer.appendChild(activityItem);
            });
        })
        .catch(error => {
            console.error('Error fetching recent activity:', error);
        });
}

function updateTradesTable() {
    fetch('/api/trades')
        .then(response => response.json())
        .then(trades => {
            const tableBody = document.getElementById('trades-table-body');
            tableBody.innerHTML = '';
            
            if (trades.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" class="px-6 py-4 text-center text-gray-500">
                            No trades found
                        </td>
                    </tr>
                `;
                return;
            }
            
            trades.forEach(trade => {
                const row = document.createElement('tr');
                
                const timeCell = document.createElement('td');
                timeCell.className = 'px-6 py-4 whitespace-nowrap text-sm text-gray-500';
                timeCell.textContent = new Date(trade.timestamp).toLocaleTimeString();
                
                const symbolCell = document.createElement('td');
                symbolCell.className = 'px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900';
                symbolCell.textContent = trade.symbol;
                
                const actionCell = document.createElement('td');
                actionCell.className = `px-6 py-4 whitespace-nowrap text-sm ${
                    trade.action === 'BUY' ? 'text-green-600' : 'text-red-600'
                }`;
                actionCell.textContent = trade.action;
                
                const entryCell = document.createElement('td');
                entryCell.className = 'px-6 py-4 whitespace-nowrap text-sm text-gray-500';
                entryCell.textContent = trade.entry_price;
                
                const slCell = document.createElement('td');
                slCell.className = 'px-6 py-4 whitespace-nowrap text-sm text-gray-500';
                slCell.textContent = trade.stop_loss;
                
                const tpCell = document.createElement('td');
                tpCell.className = 'px-6 py-4 whitespace-nowrap text-sm text-gray-500';
                tpCell.textContent = trade.take_profit_1;
                
                const statusCell = document.createElement('td');
                statusCell.className = 'px-6 py-4 whitespace-nowrap text-sm';
                
                const statusBadge = document.createElement('span');
                statusBadge.className = `px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                    trade.status === 'SUCCESS' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`;
                statusBadge.textContent = trade.status;
                
                statusCell.appendChild(statusBadge);
                
                row.appendChild(timeCell);
                row.appendChild(symbolCell);
                row.appendChild(actionCell);
                row.appendChild(entryCell);
                row.appendChild(slCell);
                row.appendChild(tpCell);
                row.appendChild(statusCell);
                
                tableBody.appendChild(row);
            });
        })
        .catch(error => {
            console.error('Error fetching trades:', error);
        });
}

function updatePerformanceMetrics() {
    fetch('/api/trades')
        .then(response => response.json())
        .then(trades => {
            const totalTrades = trades.length;
            const successTrades = trades.filter(t => t.status === 'SUCCESS').length;
            const failedTrades = totalTrades - successTrades;
            const winRate = totalTrades > 0 ? Math.round((successTrades / totalTrades) * 100) : 0;
            
            document.getElementById('total-trades').textContent = totalTrades;
            document.getElementById('success-trades').textContent = successTrades;
            document.getElementById('failed-trades').textContent = failedTrades;
            document.getElementById('win-rate').textContent = `${winRate}%`;
        })
        .catch(error => {
            console.error('Error fetching performance metrics:', error);
        });
}