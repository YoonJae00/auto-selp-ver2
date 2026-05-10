# Design Specification: Auto-Selp E-commerce Automation Platform

## 1. Overview
Auto-Selp is a comprehensive SaaS-based e-commerce automation hub designed for sellers to optimize product data, track sales performance, and eventually manage the entire product lifecycle (registration, sales, CS). The system is built on a Microservices Architecture (MSA) to ensure scalability and ease of future feature additions.

## 2. Architecture: Microservices (MSA)
The system is composed of independent services orchestrated via Docker Compose.

### 2.1 Services
- **API Gateway (Nginx)**: The entry point for all client requests. Handles routing, SSL termination, and basic security.
- **Auth Service (FastAPI)**: 
    - Manages user registration, login (JWT), and role-based access control (Admin/Consumer).
    - Stores and encrypts platform API keys (Naver, Coupang) using AES-256.
- **Dashboard Service (FastAPI)**:
    - Provides real-time and historical analytics (Daily sales, weekly trends, revenue charts).
    - Optimized for read-heavy operations to ensure a fast main page experience.
- **Product Processor (FastAPI)**:
    - Core logic for product name refinement, keyword curation, and category mapping.
    - Offloads heavy tasks to Background Workers.
- **Worker (Celery)**:
    - Executes long-running tasks: Excel parsing, LLM calls (Gemini), and platform API requests.
- **Database (PostgreSQL)**: Shared database instance with schema-level separation for services.
- **Message Broker (Redis)**: Handles task queuing for Celery and serves as a cache for the Dashboard.

## 3. Core Functional Logic (Product Processor)

### 3.1 Pipeline Steps
1. **Refinement**: LLM-based cleaning of product names (removing brand, special chars, duplicates).
2. **Keyword Curation**: 
    - Phase 1: Seed collection from Naver Search Ad API & Coupang Web Adapter.
    - Phase 2: Filtering by competition, length, and stop-words.
    - Phase 3: Trademark verification via local blacklist and LLM context check.
3. **Category Mapping**: 
    - Naver: Search API path matching -> Local mapping file lookup.
    - Coupang: Direct call to Category Prediction API.

## 4. Data Strategy
- **Security**: User API keys are encrypted at rest. JWT is used for service-to-service and client-to-service authentication.
- **Concurrency**: Celery workers handle parallel processing of Excel rows to prevent system bottlenecks.
- **Scalability**: Each service is containerized, allowing horizontal scaling of the Processor or Dashboard services independently.

## 5. UI/UX Roadmap (SaaS)
- **Main Dashboard**: Visual charts for sales data.
- **Processing Page**: Excel upload drag-and-drop, real-time status tracking of async tasks.
- **Settings**: Management of user profiles and platform API credentials.

## 6. Tech Stack
- **Backend**: Python 3.12+, FastAPI, Celery, SQLAlchemy (Async).
- **Frontend**: React/Next.js (TypeScript).
- **Database**: PostgreSQL 16.
- **Infrastructure**: Docker, Docker Compose, Redis.
- **AI**: Gemini 2.0 Flash API.
