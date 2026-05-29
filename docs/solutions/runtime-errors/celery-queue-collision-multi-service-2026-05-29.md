---
title: Celery Queue Collision in Multi-Service Architecture Causes Unregistered Task Failures
date: 2026-05-29
category: docs/solutions/runtime-errors
module: celery-integration
problem_type: runtime_error
component: tooling
symptoms:
  - "Pressing the process button instantly marks database products as failed in the UI"
  - "The processor worker container logs show no task pickup activity"
  - "The marketplace worker container logs show ERROR: Received unregistered task of type tasks.process_db_products_task and KeyError"
root_cause: config_error
resolution_type: code_fix
severity: high
tags: [celery, redis, queues, docker-compose, multi-service, microservices]
---

# Celery Queue Collision in Multi-Service Architecture Causes Unregistered Task Failures

## Problem
In a multi-service Docker Compose architecture where multiple services utilize the same Redis broker (e.g., `redis://redis:6379/0`), Celery tasks are discarded and fail instantly with unregistered task errors when workers from different services compete for the default `celery` queue.

## Symptoms
- Pressing the "가공" (Process) button instantly marks database products as `"failed"` in the UI Command Center without performing any operations.
- The `processor` worker service (`worker-1`) shows no logging activity regarding task receipt or processing.
- The `marketplace` worker service (`marketplace-worker-1`) shows a loud error log in the console:
  ```
  Received unregistered task of type 'tasks.process_db_products_task'.
  The message has been ignored and discarded.
  KeyError: 'tasks.process_db_products_task'
  ```

## What Didn't Work
- Attempting to rebuild the `processor` and `worker` containers alone did not solve the issue, as the `marketplace-worker` continued to win the race to fetch tasks from the shared default queue.

## Solution
Isolate the Celery queues for each microservice by defining distinct default queue names on the Celery application configurations and updating the worker run commands in `docker-compose.yml` to specify explicit queue targets.

### 1. Set Default Queues in Celery App Configs
In `services/processor/celery_app.py`:
```python
celery_app.conf.update(
    # ...
    task_default_queue="processor",
)
```
In `services/marketplace/celery_app.py`:
```python
celery_app.conf.update(
    # ...
    task_default_queue="marketplace",
)
```

### 2. Configure Workers to Listen to Explicit Queues
In `docker-compose.yml`, update the `command` keys with `-Q` flags to subscribe to their respective queues:
```yaml
  worker:
    build: ./services/processor
    command: celery -A tasks.celery_app worker --loglevel=info -Q processor

  marketplace-worker:
    build: ./services/marketplace
    command: celery -A tasks.celery_app worker --loglevel=info -Q marketplace
```

## Why This Works
By default, if `task_default_queue` is not specified, all Celery instances subscribe to the shared queue name `celery`. In a multi-service setup sharing a single Redis instance, this causes workers to pull task messages they do not have registered in their local codebases. Assigning distinct queues ensures that `tasks.process_db_products_task` is routed only to the `processor` queue, which is subscribed to exclusively by the processor `worker` service.

## Prevention
- **Queue Segregation**: Always enforce separate queue namespaces (e.g., `-Q <service_name>`) for different microservices or applications sharing the same Redis/RabbitMQ broker.
- **Queue Auditing**: Periodically run `celery -A celery_app inspect active_queues` to ensure no overlapping queue subscriptions exist between services.
