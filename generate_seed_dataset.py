
import random
import uuid
from datetime import datetime, timedelta

# --------------------------------------------------
# Configuration
# --------------------------------------------------
OUTPUT_FILE = "seed_service.log"
TOTAL_LOGS = 5000
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

START_TIME = datetime(2026, 10, 27, 0, 0, 0)

SERVICES = [
    "api-gateway",
    "auth-service",
    "order-service",
    "payment-service",
    "inventory-service",
    "shipping-service",
    "notification-service",
    "user-service",
    "product-service",
    "database-service",
    "cache-service",
    "message-broker",
]

LEVELS = ["INFO", "WARN", "ERROR", "DEBUG"]

DB_HOSTS = [
    "db-orders-01",
    "db-payments-01",
    "db-users-01",
    "db-inventory-01",
]

HTTP_PATHS = [
    "/api/orders",
    "/api/orders/{id}",
    "/api/payments",
    "/api/products",
    "/api/products/search",
    "/api/users/profile",
    "/api/auth/login",
    "/api/inventory/check",
    "/api/shipping/track",
]

PAYMENT_ERRORS = [
    "connection_timeout",
    "db_pool_exhausted",
    "deadlock_detected",
    "gateway_unavailable",
    "payment_declined",
    "invalid_payment_method",
    "duplicate_transaction",
]

INCIDENTS = [
    "payment_db_pool_exhaustion",
    "database_connection_timeout",
    "inventory_service_degradation",
    "message_broker_lag",
    "cache_cluster_failure",
    "authentication_rate_limit",
    "shipping_provider_outage",
    "high_api_latency",
]

# --------------------------------------------------
# Utilities
# --------------------------------------------------
def request_context():
    return (
        f"requestId=req-{uuid.uuid4().hex[:12]} "
        f"traceId={uuid.uuid4().hex[:16]}"
    )


def log_line(timestamp, level, service, message):
    return (
        f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
        f"{level} [{service}] {message}"
    )


def random_timestamp():
    return START_TIME + timedelta(
        seconds=random.randint(0, 86399)
    )


# --------------------------------------------------
# Normal application traffic
# --------------------------------------------------
def normal_event(ts):
    service = random.choice(SERVICES)
    ctx = request_context()

    if service == "api-gateway":
        path = random.choice(HTTP_PATHS)
        method = random.choices(
            ["GET", "POST", "PUT", "DELETE"],
            weights=[55, 25, 15, 5],
        )[0]
        status = random.choices(
            [200, 201, 204, 400, 401, 404, 429, 500],
            weights=[65, 12, 5, 5, 4, 3, 3, 3],
        )[0]
        duration = random.randint(8, 2500)

        if duration > 1200 and status < 500:
            level = "WARN"
        elif status >= 500:
            level = "ERROR"
        elif status in (400, 401, 404, 429):
            level = "WARN"
        else:
            level = "INFO"

        message = (
            f"Request completed path={path} method={method} "
            f"status={status} duration_ms={duration} {ctx}"
        )

    elif service == "order-service":
        order_id = random.randint(1000, 9999)
        user_id = random.randint(500, 2500)
        amount = round(random.uniform(5, 1500), 2)
        action = random.choice([
            "Processing order",
            "Order confirmed",
            "Order validation completed",
            "Order cancelled",
            "Order update received",
        ])

        level = "INFO"
        message = (
            f"{action} orderId={order_id} userId={user_id} "
            f"amount={amount:.2f} currency=USD {ctx}"
        )

    elif service == "payment-service":
        payment_id = random.randint(2000, 99999)
        order_id = random.randint(1000, 9999)
        amount = round(random.uniform(5, 1500), 2)
        outcome = random.choices(
            ["success", "failed", "pending"],
            weights=[88, 7, 5],
        )[0]

        if outcome == "failed":
            level = "ERROR"
            reason = random.choice(PAYMENT_ERRORS)
            message = (
                f"Payment failed paymentId={payment_id} "
                f"orderId={order_id} reason={reason} "
                f"db_host={random.choice(DB_HOSTS)} {ctx}"
            )
        else:
            level = "INFO" if outcome == "success" else "WARN"
            message = (
                f"Payment {outcome} paymentId={payment_id} "
                f"orderId={order_id} amount={amount:.2f} "
                f"provider={random.choice(['stripe', 'adyen', 'internal'])} "
                f"{ctx}"
            )

    elif service == "auth-service":
        outcome = random.choice([
            "login_success",
            "token_validated",
            "token_expired",
            "invalid_credentials",
            "rate_limit_exceeded",
        ])
        level = (
            "ERROR" if outcome == "rate_limit_exceeded"
            else "WARN" if outcome in (
                "token_expired", "invalid_credentials"
            )
            else "INFO"
        )
        message = (
            f"Authentication event={outcome} "
            f"userId={random.randint(500, 2500)} "
            f"source=web-client {ctx}"
        )

    elif service == "inventory-service":
        level = random.choices(
            ["INFO", "WARN"], weights=[92, 8]
        )[0]
        message = (
            f"Inventory reservation sku=SKU-{random.randint(100,999)} "
            f"quantity={random.randint(1,8)} "
            f"available={random.randint(0,250)} "
            f"warehouse={random.choice(['WH-EAST', 'WH-WEST', 'WH-CENTRAL'])} "
            f"{ctx}"
        )

    elif service == "shipping-service":
        level = "INFO"
        message = (
            f"Shipment update shipmentId=SH-{random.randint(10000,99999)} "
            f"status={random.choice(['created', 'packed', 'shipped', 'delivered'])} "
            f"carrier={random.choice(['DHL', 'FedEx', 'UPS', 'LocalCarrier'])} "
            f"{ctx}"
        )

    elif service == "notification-service":
        outcome = random.choice(["sent", "queued", "retrying", "failed"])
        level = (
            "ERROR" if outcome == "failed"
            else "WARN" if outcome == "retrying"
            else "INFO"
        )
        message = (
            f"Notification {outcome} channel="
            f"{random.choice(['email', 'sms', 'push'])} "
            f"messageId=MSG-{random.randint(10000,99999)} "
            f"attempt={random.randint(1,3)} {ctx}"
        )

    elif service == "user-service":
        level = "INFO"
        message = (
            f"User profile accessed userId={random.randint(500,2500)} "
            f"operation={random.choice(['read', 'update', 'preferences'])} "
            f"{ctx}"
        )

    elif service == "product-service":
        level = "INFO"
        message = (
            f"Product query completed category="
            f"{random.choice(['electronics', 'home', 'clothing', 'books'])} "
            f"result_count={random.randint(0,100)} "
            f"duration_ms={random.randint(5,800)} {ctx}"
        )

    elif service == "database-service":
        duration = random.randint(2, 1800)
        level = "WARN" if duration > 700 else "INFO"
        message = (
            f"Query completed db_host={random.choice(DB_HOSTS)} "
            f"duration_ms={duration} rows={random.randint(0,5000)} "
            f"connections_active={random.randint(5,45)} {ctx}"
        )

    elif service == "cache-service":
        outcome = random.choices(
            ["hit", "miss", "eviction"], weights=[75, 22, 3]
        )[0]
        level = "WARN" if outcome == "eviction" else "DEBUG"
        message = (
            f"Cache {outcome} key=cache:{random.randint(1000,9999)} "
            f"latency_ms={random.randint(1,120)} "
            f"cluster=redis-primary {ctx}"
        )

    else:
        level = "INFO"
        message = (
            f"Message processed topic="
            f"{random.choice(['orders', 'payments', 'notifications'])} "
            f"partition={random.randint(0,7)} "
            f"consumer_lag={random.randint(0,150)} "
            f"messageId=MSG-{random.randint(10000,99999)} {ctx}"
        )

    return log_line(ts, level, service, message)


# --------------------------------------------------
# Correlated incident events
# --------------------------------------------------
def incident_events(ts):
    incident = random.choice(INCIDENTS)
    events = []
    ctx = request_context()

    if incident == "payment_db_pool_exhaustion":
        host = "db-payments-01"
        for i in range(random.randint(3, 8)):
            t = ts + timedelta(seconds=i * random.randint(1, 4))
            events.append(log_line(
                t, "ERROR", "payment-service",
                f"Payment failed paymentId={random.randint(20000,99999)} "
                f"reason=db_pool_exhausted db_host={host} "
                f"db_pool_active=50 db_pool_max=50 {ctx}"
            ))

        events.append(log_line(
            ts + timedelta(seconds=12),
            "ERROR", "api-gateway",
            f"Upstream timeout service=payment-service "
            f"status=504 duration_ms=30000 {ctx}"
        ))
        events.append(log_line(
            ts + timedelta(seconds=15),
            "WARN", "order-service",
            f"Order pending orderId={random.randint(1000,9999)} "
            f"reason=payment_timeout {ctx}"
        ))
        events.append(log_line(
            ts + timedelta(seconds=30),
            "INFO", "payment-service",
            f"Connection pool recovered db_host={host} "
            f"db_pool_active={random.randint(10,30)} "
            f"db_pool_max=50 {ctx}"
        ))

    elif incident == "database_connection_timeout":
        host = random.choice(DB_HOSTS)
        for i in range(4):
            events.append(log_line(
                ts + timedelta(seconds=i * 3),
                "ERROR", "database-service",
                f"Database connection timeout db_host={host} "
                f"connect_timeout_ms=5000 retry={i + 1} {ctx}"
            ))
        events.append(log_line(
            ts + timedelta(seconds=15),
            "WARN", "database-service",
            f"Database connection restored db_host={host} {ctx}"
        ))

    elif incident == "inventory_service_degradation":
        for i in range(4):
            events.append(log_line(
                ts + timedelta(seconds=i * 4),
                "WARN", "inventory-service",
                f"Slow inventory query duration_ms="
                f"{random.randint(2500,8000)} "
                f"sku=SKU-{random.randint(100,999)} {ctx}"
            ))
        events.append(log_line(
            ts + timedelta(seconds=20),
            "ERROR", "api-gateway",
            f"Upstream timeout service=inventory-service "
            f"status=504 duration_ms=5000 {ctx}"
        ))

    elif incident == "message_broker_lag":
        for i in range(4):
            events.append(log_line(
                ts + timedelta(seconds=i * 5),
                "WARN", "message-broker",
                f"Consumer lag increased topic=orders "
                f"partition={i} consumer_lag="
                f"{random.randint(5000,30000)} {ctx}"
            ))
        events.append(log_line(
            ts + timedelta(seconds=25),
            "INFO", "message-broker",
            f"Consumer lag recovered topic=orders consumer_lag=12 {ctx}"
        ))

    elif incident == "cache_cluster_failure":
        for i in range(3):
            events.append(log_line(
                ts + timedelta(seconds=i * 4),
                "ERROR", "cache-service",
                f"Cache connection failed cluster=redis-primary "
                f"reason=connection_refused retry={i + 1} {ctx}"
            ))
        events.append(log_line(
            ts + timedelta(seconds=15),
            "WARN", "product-service",
            f"Fallback to database reason=cache_unavailable "
            f"duration_ms=1800 {ctx}"
        ))

    elif incident == "authentication_rate_limit":
        for i in range(5):
            events.append(log_line(
                ts + timedelta(seconds=i * 2),
                "WARN", "auth-service",
                f"Rate limit triggered clientId=client-{random.randint(1,20)} "
                f"status=429 window_seconds=60 {ctx}"
            ))

    elif incident == "shipping_provider_outage":
        for i in range(3):
            events.append(log_line(
                ts + timedelta(seconds=i * 5),
                "ERROR", "shipping-service",
                f"Carrier API unavailable carrier="
                f"{random.choice(['DHL', 'FedEx', 'UPS'])} "
                f"status=503 retry={i + 1} {ctx}"
            ))

    elif incident == "high_api_latency":
        for i in range(5):
            events.append(log_line(
                ts + timedelta(seconds=i * 2),
                "WARN", "api-gateway",
                f"Slow request path={random.choice(HTTP_PATHS)} "
                f"status=200 duration_ms={random.randint(3000,12000)} "
                f"{ctx}"
            ))

    return events


# --------------------------------------------------
# Generate, sort, and save the complete dataset
# --------------------------------------------------
def main():
    records = []

    # Roughly 80% routine traffic and 20% incident-related events.
    incident_count = int(TOTAL_LOGS * 0.20)
    normal_count = TOTAL_LOGS - incident_count

    for _ in range(normal_count):
        records.append(normal_event(random_timestamp()))

    for _ in range(incident_count // 5):
        records.extend(incident_events(random_timestamp()))

    # Keep the requested dataset size exact.
    if len(records) > TOTAL_LOGS:
        records = random.sample(records, TOTAL_LOGS)
    while len(records) < TOTAL_LOGS:
        records.append(normal_event(random_timestamp()))

    records.sort(key=lambda line: datetime.strptime(
        line[:19], "%Y-%m-%d %H:%M:%S"
    ))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(records) + "\n")

    print(f"Dataset saved to {OUTPUT_FILE}")
    print(f"Total log entries: {len(records)}")
    print(f"Services: {len(SERVICES)}")
    print(f"Date range: {START_TIME.date()} (24-hour window)")


if __name__ == "__main__":
    main()
