# ATITO QS — DFD & ORM Documentation

**Author:** Eng. STEPHEN ODHIAMBO

**Purpose:** Detailed Data Flow Diagram (DFD) and Object-Relational Mapping (ORM) documentation for the ATITO QS application. 
This document includes a levelled DFD (context + process-level), a data dictionary, and complete SQLAlchemy ORM model examples with indexing, constraints, and practical notes for production readiness.

---

## Table of contents

1. DFD — Overview
2. DFD Level 0 (Context) — Short description
3. DFD Level 1 — Diagram (PNG) + process descriptions
4. Data Dictionary (flows & payloads)
5. Data Stores (schema summary)
6. Security & Compliance notes
7. ORM Documentation — SQLAlchemy models (copy-pasteable)
8. Indexing, migrations, and performance guidance
9. Deployment & backup checklist
10. Next steps & deliverables

---

## 1. DFD — Overview

This system-level DFD describes how users, external services, and internal subsystems interact to ingest drawings, extract quantities, cost them using live rates, and produce reports. The DFD is split into a Context diagram (Level 0) and a Level 1 diagram that shows the main processes, data stores, and flows.

---

## 2. DFD Level 0 (Context)

**Primary external actors:**

* **User** (Quantity Surveyor, Contractor, Client)
* **M-Pesa Daraja** (payment provider)
* **Suppliers & Public Rate Sources** (IQSK, NCA, KIPPRA, Integrum)
* **Google Vision API** (primary OCR)

**Primary system (ATITO QS):**

* Accepts uploads and metadata; runs OCR + AI; produces BoQ/BBS and reports; stores results in PostgreSQL and object storage; exposes APIs and frontend.

**Primary data stores:** PostgreSQL (master data & JSONB fields) and Object Storage (files & photos).

---

## 3. DFD Level 1 — Diagram + process descriptions

**Diagram (PNG):** The diagram for Level 1 (process-level DFD) is attached below. It shows the main processes, stores, and flows.

![DFD Level 1 — ATITO QS](/sandbox/mnt/data/atito_dfd_level1.png)

> If the image does not render in your viewer, download it directly from: `sandbox:/mnt/data/atito_dfd_level1.png`.

### Process descriptions (numbered for reference)

1. **Auth & RBAC (JWT)**

   * Responsible for user authentication, role issuance, and token refresh. Emits audit events and enforces RBAC for all API endpoints.

2. **Upload & Parsing**

   * Accepts PDF/DWG/IFC/Images; stores raw file in object store; enqueues parsing jobs (vector extraction, rasterization) to the task queue (Redis).

3. **OCR & AI/CV Engine**

   * Background workers perform OCR using Google Vision (primary) or Tesseract (fallback), run object detection/segmentation models (e.g., `models/yolov8n.pt`) to identify walls, doors, windows, dims, and draw semantic layers for reasoning.

4. **Geometric Reasoning & Takeoff Engine**

   * Transforms parsed geometry + text into structural elements with precise dimensions (areas, lengths, counts). Applies QS rules to compute net quantities.

5. **BoQ & BBS Generator**

   * Uses material recipes, waste% rules, and rounding rules (e.g., steel to nearest 50kg) to break net quantities into material lines and produce BBS entries compliant with BS 8666.

6. **Costing Engine & Rate Updater**

   * Accepts periodic feeds from the Web Scraper; computes weighted averages, applies location factors, preliminary costs, provisional sums, labor overhead, contingency, and VAT.

7. **Reporting & Export**

   * Requests data from PostgreSQL and object store to generate PDF/XLSX/CSV/JSON outputs and streams them to the user for download.

8. **On-site Sync**

   * Handles offline-first site logs from IndexedDB; uploads photos to object store; writes site logs to PostgreSQL once online.

9. **Audit & Logging**

   * Central logging process capturing all significant actions, errors, confidence scores, and user interactions. Stored into `audit_log` in PostgreSQL.

10. **Web Scraper**

* Periodically scrapes supplier and public data sources for up-to-date materials pricing and feeds the Costing Engine.

---

## 4. Data Dictionary (flows & payloads)

Below are the most important data flows and a short description of their structure.

* **credentials (User → Auth)**

  * `{email, password}` or OAuth token. Encrypted in transit (TLS) and never logged in plain text.

* **project files / metadata (User → Upload)**

  * `{project_id, file_name, file_type, file_hash, uploader_id, metadata: {county, floors, project_type}}`

* **parsing job (Upload → Redis → OCR)**

  * `{job_id, s3_path, file_type, project_id, enqueue_ts}`

* **ocr result (GVI/Tesseract → OCR)**

  * `{text_blocks: [...], confidence_scores: [...], page_number}`

* **parsed elements (OCR → Geo)**

  * `[ {element_type: 'wall'|'column'|'door'|'window'|'slab', geometry: {type:'polyline'|'polygon'|'point', coordinates: [...]}, labels: {...}, dims: {...}, confidence: 0.0-1.0 } ]`

* **takeoff quantities (Geo → BOQ)**

  * `{element_id, element_type, net_qty, gross_qty, waste_pct, uom, material_recipe_id, confidence}`

* **boq_items JSONB (BOQ → PostgreSQL)**

  * `[{id, code, description, uom, net_qty, gross_qty, rate, total_cost, ai_remarks: {...}}, ...]`

* **rate feed (Scraper → Cost)**

  * `{material_code, source, unit_price, date_collected, raw_html_snippet}`

* **payment callback (MPESA → PG)**

  * `{transaction_id, amount, phone_number, status, timestamp}`

* **site log (Client device → Sync)**

  * `{project_id, user_id, notes, photo_s3_path, latitude, longitude, ts}`

---

## 5. Data Stores (schema summary)

**PostgreSQL** (primary relational store)

* `users` (id PK, email, password_hash, name, role, plan_type, last_login_at, created_at, updated_at)
* `projects` (id PK, owner_id FK users, name, county, floors, gfa, metadata JSONB, status, created_at)
* `materials` (id PK, code, name, unit, description, last_price, source)
* `supplier_rates` (id PK, supplier_id FK, material_id FK, price, currency, captured_at)
* `boq_items` (id PK, project_id FK, item_code, description, uom, net_qty, gross_qty, rate, total_cost, ai_notes JSONB)
* `bbs_items` (id PK, project_id FK, bar_shape, bar_size, length_m, quantity, weight_kg, ai_notes JSONB)
* `site_logs` (id PK, project_id FK, user_id FK, notes, photo_path, latitude, longitude, ts)
* `expenses` (id PK, project_id FK, date, description, category, amount, supplier_id)
* `comments` (id PK, parent_id FK nullable, project_id FK, user_id FK, target_type, target_id, body, created_at)
* `audit_log` (id PK, user_id FK, action_type, details JSONB, created_at)
* `transactions` (id PK, project_id FK, user_id FK, mpesa_txn_id, amount, status, created_at)

**Object Storage** (S3-compatible)

* `uploads/{project_id}/{file_hash}.{ext}` → drawings, PDFs
* `photos/{project_id}/{YYYYMMDD}/{uuid}.jpg` → site photos

**Redis (Task Queue)**

* Queued parsing, OCR, model inference, and long-running jobs. Use Redis + RQ or Celery with Redis broker.

---

## 6. Security & Compliance notes

* **Transport:** TLS 1.2+ for all endpoints; enforce HSTS.
* **Auth:** JWT with short lived access tokens (e.g. 15m) and refresh tokens. Role claim embedded: `role`.
* **Secrets:** Use environment variables with a secrets manager for production (AWS Secrets Manager / HashiCorp Vault). Do NOT commit `.env` to repo.
* **DB encryption:** Column-level encryption optional for extremely sensitive fields; at minimum enable full-disk encryption on DB server and S3 encryption (SSE).
* **Backups:** WAL archiving & daily base backups; test restores periodically.
* **Audit:** All critical actions (uploads, BoQ generation, payments) must be written to `audit_log` with actor, timestamp, and details.
* **Third-party calls:** Limit and validate responses from external sources (Google Vision, MPESA, scraping). Implement request timeouts and retry policies.

---

## 7. ORM Documentation — SQLAlchemy (declarative) examples

Below are copy-ready SQLAlchemy models (declarative with typing). These assume `sqlalchemy>=1.4` and use `sqlalchemy.orm` declarative base and modern typing styles.

> Paste these into your `models.py` (or split across files per domain). Use Alembic for migrations.

```python
# models.py (SQLAlchemy declarative)
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, Numeric, Boolean, Enum, JSON, Float, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base
import enum
import datetime

Base = declarative_base()

class UserRole(enum.Enum):
    admin = 'admin'
    qs = 'qs'
    client = 'client'
    contractor = 'contractor'

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.qs, nullable=False)
    plan_type = Column(String(32), default='free')
    last_login_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    projects = relationship('Project', back_populates='owner')

class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(512), nullable=False)
    county = Column(String(128), nullable=True)
    floors = Column(Integer, default=1)
    gfa = Column(Float, nullable=True)
    metadata = Column(JSONB, default=dict)
    status = Column(String(64), default='draft')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship('User', back_populates='projects')
    boq_items = relationship('BoQItem', back_populates='project')
    bbs_items = relationship('BBSItem', back_populates='project')

    __table_args__ = (
        Index('ix_projects_owner_name', 'owner_id', 'name'),
    )

class Material(Base):
    __tablename__ = 'materials'
    id = Column(Integer, primary_key=True)
    code = Column(String(128), unique=True, nullable=False)
    name = Column(String(512), nullable=False)
    unit = Column(String(64), nullable=False)
    description = Column(Text)
    last_price = Column(Numeric(12,2))
    source = Column(String(128))

class Supplier(Base):
    __tablename__ = 'suppliers'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    contact = Column(String(255))
    location = Column(String(255))

class SupplierRate(Base):
    __tablename__ = 'supplier_rates'
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id', ondelete='CASCADE'))
    material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'))
    price = Column(Numeric(12,2), nullable=False)
    currency = Column(String(8), default='KES')
    captured_at = Column(DateTime, default=datetime.datetime.utcnow)

    supplier = relationship('Supplier')
    material = relationship('Material')

class BoQItem(Base):
    __tablename__ = 'boq_items'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    item_code = Column(String(128), nullable=True)
    description = Column(Text, nullable=False)
    uom = Column(String(32), nullable=False)
    net_qty = Column(Float, nullable=False)
    gross_qty = Column(Float, nullable=False)
    rate = Column(Numeric(12,2), nullable=True)
    total_cost = Column(Numeric(14,2), nullable=True)
    ai_notes = Column(JSONB, default=dict)

    project = relationship('Project', back_populates='boq_items')

class BBSItem(Base):
    __tablename__ = 'bbs_items'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    bar_shape = Column(String(32))
    bar_size = Column(String(16))
    length_m = Column(Float)
    quantity = Column(Integer)
    weight_kg = Column(Float)
    ai_notes = Column(JSONB, default=dict)

    project = relationship('Project', back_populates='bbs_items')

class SiteLog(Base):
    __tablename__ = 'site_logs'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    notes = Column(Text)
    photo_path = Column(String(1024))
    latitude = Column(Float)
    longitude = Column(Float)
    ts = Column(DateTime, default=datetime.datetime.utcnow)

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(Text)
    category = Column(String(128))
    amount = Column(Numeric(12,2))
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('comments.id'), nullable=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    target_type = Column(String(64))  # e.g., 'boq_item' or 'bbs_item'
    target_id = Column(Integer)
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    action_type = Column(String(128), nullable=False)
    details = Column(JSONB)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    mpesa_txn_id = Column(String(128), unique=True)
    amount = Column(Numeric(12,2))
    status = Column(String(64))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Useful indexes / GIN on JSONB columns to support queries
Index('ix_boq_items_project_ai', BoQItem.project_id, postgresql_using='btree')
Index('ix_bbs_items_project', BBSItem.project_id)

# GIN index for JSONB if needed (create via alembic / raw SQL)
# CREATE INDEX ix_boq_ai_notes_gin ON boq_items USING GIN (ai_notes);
```

---

## 8. Indexing, migrations, and performance guidance

* **JSONB & GIN:** Add GIN indexes on `ai_notes` and `metadata` JSONB columns if you need to query them frequently. Example: `CREATE INDEX CONCURRENTLY ix_boq_ai_notes_gin ON boq_items USING GIN (ai_notes);`
* **Partial Indexes:** Use partial indexes for active projects: `CREATE INDEX ix_projects_active ON projects (owner_id) WHERE status='active';`
* **Connection Pooling:** Use `pgbouncer` in transaction pooling mode for web workers.
* **Background workers:** Offload heavy AI tasks to worker pods (K8s) and use Redis/Celery or RQ for job orchestration.
* **Migrations:** Use Alembic. Write migrations for JSONB and GIN index creation with `op.execute()` for raw statements when necessary.

---

## 9. Deployment & backup checklist

* Use containerized deployment (Docker) and orchestration (Kubernetes) for production.
* Secrets: HashiCorp Vault or cloud secrets manager.
* Backups: Daily base backups + WAL retention (7–30 days depending on RTO/RPO).
* Monitoring: Prometheus + Grafana for metrics; ELK / Loki for logs.
* DR testing: Periodic restore tests.

---

## 10. Next steps & deliverables

* Generate ER diagram (PNG or SVG) from the SQLAlchemy models (I can produce this next).
* Produce Alembic migration scripts for the initial schema.
* Generate example API CRUD endpoints (FastAPI) for `projects/boq/transactions`.
* Optionally: produce a sequence diagram for BoQ generation.

---
