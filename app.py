from flask import Flask, render_template, jsonify
import sqlite3
from datetime import datetime
import json
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect('trades.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trades')
def get_trades():
    conn = get_db_connection()
    trades = conn.execute('SELECT * FROM trades ORDER BY timestamp DESC LIMIT 50').fetchall()
    conn.close()
    
    # Convert to list of dictionaries
    trades_list = [dict(trade) for trade in trades]
    
    # Convert timestamp to string for JSON serialization
    for trade in trades_list:
        if 'timestamp' in trade:
            trade['timestamp'] = datetime.strptime(trade['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify(trades_list)

@app.route('/api/status')
def get_status():
    try:
        with open('system_status.json') as f:
            status = json.load(f)
        return jsonify(status)
    except FileNotFoundError:
        return jsonify({"error": "Status file not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)