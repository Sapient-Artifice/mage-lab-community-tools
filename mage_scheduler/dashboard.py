from flask import Flask, render_template, send_file
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import os

app = Flask(__name__)
csv_path = os.path.join(os.path.dirname(__file__), 'tasks', 'gpu_monitor_log.csv')

@app.route('/')
def index():
    # Render the main dashboard page
    return render_template('dashboard.html')

@app.route('/plot.png')
def plot_png():
    df = pd.read_csv(csv_path, parse_dates=['timestamp'])

    plt.figure(figsize=(14,7))

    # Plot GPU Utilization Percent
    plt.subplot(2,1,1)
    plt.plot(df['timestamp'], df['gpu_0_utilization_percent'], marker='o', linestyle='-', color='b')
    plt.title('GPU Utilization Percent Over Time')
    plt.ylabel('GPU Utilization (%)')
    plt.grid(True)

    # Plot GPU Memory Used and Free
    plt.subplot(2,1,2)
    plt.plot(df['timestamp'], df['gpu_0_memory_used_mb'], marker='x', linestyle='-', color='r', label='Memory Used (MB)')
    plt.plot(df['timestamp'], df['gpu_0_memory_free_mb'], marker='x', linestyle='-', color='g', label='Memory Free (MB)')
    plt.title('GPU Memory Used and Free Over Time')
    plt.ylabel('Memory (MB)')
    plt.xlabel('Time')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()

    # Save plot to BytesIO object and return as response
    img = BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return send_file(img, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
