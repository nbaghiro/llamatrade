# Deployment & Operations Guide

This guide covers deploying LlamaTrade to staging and production environments on GCP.

---

## Infrastructure Overview

### GCP Services Used

| Service | Purpose |
|---------|---------|
| **GKE Autopilot** | Kubernetes cluster for all services |
| **Cloud SQL** | PostgreSQL 16 database |
| **Memorystore** | Redis 7 for cache/queues |
| **Cloud Storage** | Backtest results, static assets |
| **Cloud CDN** | Frontend asset delivery |
| **Cloud Load Balancer** | L7 load balancing, SSL termination |
| **Secret Manager** | Sensitive configuration |
| **Cloud Monitoring** | Metrics, logging, alerting |
| **Artifact Registry** | Docker image storage |

### Environment Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                         GCP PROJECT                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │      STAGING        │    │     PRODUCTION      │             │
│  │                     │    │                     │             │
│  │  GKE Namespace:     │    │  GKE Namespace:     │             │
│  │    staging          │    │    production       │             │
│  │                     │    │                     │             │
│  │  Cloud SQL:         │    │  Cloud SQL:         │             │
│  │    llamatrade-stg   │    │    llamatrade-prod  │             │
│  │                     │    │                     │             │
│  │  Redis:             │    │  Redis:             │             │
│  │    redis-staging    │    │    redis-prod       │             │
│  │                     │    │                     │             │
│  │  Domain:            │    │  Domain:            │             │
│  │    staging.llama... │    │    app.llamatrade.. │             │
│  └─────────────────────┘    └─────────────────────┘             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

All configuration is via environment variables. Never hardcode values.

**Required for all services:**

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_SECRET` | JWT signing key | (from Secret Manager) |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ENCRYPTION_KEY` | 32-byte key for Alpaca credentials | (from Secret Manager) |
| `ENVIRONMENT` | `development`, `staging`, `production` | `production` |
| `LOG_LEVEL` | Logging level | `INFO` |

**Service-specific:**

| Service | Variable | Description |
|---------|----------|-------------|
| Market Data | `ALPACA_API_KEY` | Alpaca API key |
| Market Data | `ALPACA_API_SECRET` | Alpaca API secret |
| Billing | `STRIPE_API_KEY` | Stripe secret key |
| Billing | `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| Notification | `SENDGRID_API_KEY` | SendGrid for email |
| Notification | `TWILIO_*` | Twilio for SMS |

### Secret Management

Secrets are stored in GCP Secret Manager and mounted as environment variables:

```yaml
# k8s deployment
env:
  - name: JWT_SECRET
    valueFrom:
      secretKeyRef:
        name: llamatrade-secrets
        key: jwt-secret
  - name: ENCRYPTION_KEY
    valueFrom:
      secretKeyRef:
        name: llamatrade-secrets
        key: encryption-key
```

**Creating secrets:**

```bash
# Create secret in Secret Manager
echo -n "your-secret-value" | gcloud secrets create jwt-secret --data-file=-

# Create Kubernetes secret from Secret Manager
kubectl create secret generic llamatrade-secrets \
  --from-literal=jwt-secret=$(gcloud secrets versions access latest --secret=jwt-secret)
```

---

## Deployment Process

### Continuous Deployment (Staging)

Merging to `main` automatically deploys to staging:

```
Push to main → GitHub Actions → Build images → Deploy to staging
```

Workflow (`.github/workflows/deploy-staging.yml`):

1. Run tests
2. Build Docker images
3. Push to Artifact Registry
4. Apply Kubernetes manifests
5. Wait for rollout
6. Run smoke tests

### Production Deployment

Production requires manual approval:

```bash
# Create release
git tag v1.2.3
git push origin v1.2.3

# GitHub Actions runs tests, builds images
# Then waits for approval

# After approval, deploy via:
make deploy-prod
```

Or manually:

```bash
# Set kubectl context
gcloud container clusters get-credentials llamatrade-prod --region us-central1

# Apply manifests
kubectl apply -k infrastructure/k8s/overlays/production

# Monitor rollout
kubectl rollout status deployment/auth -n production
kubectl rollout status deployment/strategy -n production
# ... for each service
```

---

## Database Migrations

### Running Migrations

Migrations run automatically during deployment, but can be run manually:

```bash
# Connect to Cloud SQL (via proxy)
cloud_sql_proxy -instances=project:region:instance=tcp:5432

# Run migrations
cd services/auth
DATABASE_URL="postgresql://..." alembic upgrade head
```

### Creating Migrations

```bash
cd services/auth
alembic revision --autogenerate -m "Add new column"

# Review generated migration
cat alembic/versions/xxx_add_new_column.py

# Test locally first
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

### Rollback

```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade abc123

# Check current version
alembic current
```

---

## Kubernetes Resources

### Deployments

Each service has a deployment in `infrastructure/k8s/base/<service>/`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth
  template:
    spec:
      containers:
        - name: auth
          image: gcr.io/project/auth:latest
          ports:
            - containerPort: 8810
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            grpc:
              port: 8810
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            grpc:
              port: 8810
            initialDelaySeconds: 5
            periodSeconds: 5
```

### Services

Internal gRPC services:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: auth
spec:
  selector:
    app: auth
  ports:
    - port: 8810
      targetPort: 8810
      protocol: TCP
```

### Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: auth
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: auth
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

## Monitoring

### Health Checks

Every service exposes `/health`:

```json
{
  "status": "healthy",
  "service": "auth",
  "version": "1.2.3",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Metrics

Services expose Prometheus metrics at `/metrics`:

- `http_requests_total` — Request count by method, path, status
- `http_request_duration_seconds` — Request latency histogram
- `grpc_server_handled_total` — gRPC calls by method, status
- `db_query_duration_seconds` — Database query latency
- `redis_operations_total` — Redis operation count

### Logging

Structured JSON logs to stdout:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "auth",
  "tenant_id": "uuid",
  "request_id": "uuid",
  "message": "User logged in",
  "user_id": "uuid"
}
```

Logs are collected by Cloud Logging and queryable:

```
resource.type="k8s_container"
resource.labels.namespace_name="production"
jsonPayload.level="ERROR"
```

### Alerting

Alerts configured in Cloud Monitoring:

| Alert | Condition | Severity |
|-------|-----------|----------|
| High error rate | > 5% 5xx responses | Critical |
| High latency | p99 > 5s | Warning |
| Pod crash loop | Restart > 3 in 10min | Critical |
| Database connections | > 80% pool | Warning |
| Memory pressure | > 90% usage | Warning |

---

## Troubleshooting

### Viewing Logs

```bash
# All logs for a service
kubectl logs -l app=auth -n production --tail=100

# Follow logs
kubectl logs -l app=auth -n production -f

# Specific pod
kubectl logs auth-abc123 -n production

# Previous container (after restart)
kubectl logs auth-abc123 -n production --previous
```

### Debugging Pods

```bash
# Get pod status
kubectl get pods -n production

# Describe pod (events, conditions)
kubectl describe pod auth-abc123 -n production

# Exec into pod
kubectl exec -it auth-abc123 -n production -- /bin/sh

# Port forward for local debugging
kubectl port-forward svc/auth 8810:8810 -n production
```

### Database Access

```bash
# Start Cloud SQL proxy
cloud_sql_proxy -instances=project:region:llamatrade-prod=tcp:5432

# Connect via psql
psql "postgresql://user:pass@localhost:5432/llamatrade"
```

### Common Issues

**Pod not starting:**

```bash
kubectl describe pod <pod-name> -n production
# Look at Events section for errors
```

**Database connection errors:**

```bash
# Check Cloud SQL proxy
kubectl logs cloud-sql-proxy-xxx -n production

# Check connection pool
kubectl exec -it auth-xxx -- /bin/sh -c "curl localhost:8810/health"
```

**High latency:**

```bash
# Check resource usage
kubectl top pods -n production

# Check HPA status
kubectl get hpa -n production

# Scale manually if needed
kubectl scale deployment/auth --replicas=5 -n production
```

---

## Rollback Procedures

### Kubernetes Rollback

```bash
# View rollout history
kubectl rollout history deployment/auth -n production

# Rollback to previous version
kubectl rollout undo deployment/auth -n production

# Rollback to specific revision
kubectl rollout undo deployment/auth --to-revision=3 -n production
```

### Database Rollback

```bash
# Rollback last migration
DATABASE_URL="..." alembic downgrade -1

# Verify
alembic current
```

### Full Environment Rollback

For major incidents:

1. Pause deployments
2. Rollback Kubernetes deployments
3. Rollback database if needed
4. Verify health checks pass
5. Resume normal operations

---

## Scaling

### Manual Scaling

```bash
# Scale specific service
kubectl scale deployment/backtest --replicas=10 -n production

# Scale all services
kubectl scale deployment --all --replicas=3 -n production
```

### Database Scaling

Cloud SQL can be scaled via console or Terraform:

```hcl
resource "google_sql_database_instance" "main" {
  settings {
    tier = "db-custom-4-16384"  # 4 vCPU, 16GB RAM
  }
}
```

### Redis Scaling

Memorystore scaling:

```hcl
resource "google_redis_instance" "main" {
  memory_size_gb = 8
}
```

---

## Disaster Recovery

### Backups

- **Database**: Automated daily backups, 7-day retention
- **Redis**: Persistence enabled, hourly snapshots
- **Object Storage**: Versioning enabled

### Recovery Procedures

**Database restore:**

```bash
gcloud sql backups restore <backup-id> \
  --restore-instance=llamatrade-prod \
  --backup-instance=llamatrade-prod
```

**Full environment rebuild:**

```bash
# Apply Terraform
cd infrastructure/terraform/production
terraform apply

# Deploy services
kubectl apply -k infrastructure/k8s/overlays/production

# Restore database from backup
gcloud sql backups restore ...

# Verify
./scripts/smoke-test.sh production
```
