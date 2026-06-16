import time
import random
import logging
import json
from datetime import datetime
from flask import Flask, jsonify, request, Response
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)

# ── Logging setup ──────────────────────────────────────────────────────────
# We output logs as JSON so ELK Stack can parse them easily later
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "level":     record.levelname,
            "message":   record.getMessage(),
            "service":   "flask-app",
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.handlers = [handler]

# ── Prometheus metrics ─────────────────────────────────────────────────────
# These are the numbers Prometheus will collect from our app

# Counter = only goes up (like an odometer)
# tracks every HTTP request, labelled by method, endpoint, and status code
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

# Histogram = tracks distribution of values (like response times)
# this tells us P50, P95, P99 latency
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Gauge = goes up and down (like a fuel gauge)
# tracks how many requests are being handled RIGHT NOW
ACTIVE_REQUESTS = Gauge(
    'http_active_requests',
    'Number of active HTTP requests'
)

# Counter for application-level errors
ERROR_COUNT = Counter(
    'app_errors_total',
    'Total application errors',
    ['error_type']
)

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)

# Runs BEFORE every request — start the timer, increment active requests
@app.before_request
def before_request():
    request.start_time = time.time()
    ACTIVE_REQUESTS.inc()

# Runs AFTER every request — record how long it took, decrement active
@app.after_request
def after_request(response):
    latency = time.time() - request.start_time
    ACTIVE_REQUESTS.dec()
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.path,
        status_code=response.status_code
    ).inc()
    REQUEST_LATENCY.labels(endpoint=request.path).observe(latency)
    logger.info(
        f"{request.method} {request.path} "
        f"status={response.status_code} duration={latency:.3f}s"
    )
    return response

# ── API endpoints ──────────────────────────────────────────────────────────

@app.route('/health')
def health():
    # Kubernetes uses this to check if the app is alive
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

@app.route('/api/products')
def products():
    # Simulate occasional slowness (10% of requests take 0.5-2 seconds)
    # This will show up as latency spikes in Grafana
    if random.random() < 0.1:
        time.sleep(random.uniform(0.5, 2.0))
    items = [
        {"id": i, "name": f"Product {i}", "price": round(random.uniform(10, 500), 2)}
        for i in range(1, 11)
    ]
    return jsonify({"products": items, "count": len(items)})

@app.route('/api/orders', methods=['POST'])
def create_order():
    # Simulate occasional failures (5% of orders fail)
    # This will trigger our HighErrorRate alert in Prometheus
    if random.random() < 0.05:
        ERROR_COUNT.labels(error_type="payment_timeout").inc()
        logger.error("Order failed — payment gateway timeout")
        return jsonify({"error": "Payment gateway timeout"}), 500
    order_id = random.randint(1000, 9999)
    logger.info(f"Order {order_id} created successfully")
    return jsonify({"order_id": order_id, "status": "created"}), 201

@app.route('/api/users/<int:user_id>')
def get_user(user_id):
    # Users above ID 1000 don't exist — returns 404
    # This generates warning logs we can search in Kibana
    if user_id > 1000:
        ERROR_COUNT.labels(error_type="user_not_found").inc()
        logger.warning(f"User {user_id} not found")
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com"
    })

@app.route('/metrics')
def metrics():
    # This is what Prometheus scrapes every 15 seconds
    # It returns all the counters, histograms, and gauges above
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)