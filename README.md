# 🎓 Automated Student OD & Leave Approval with Attendance Integration

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen.svg)]()
[![Stack](https://img.shields.io/badge/Stack-Node.js%20%7C%20Express%20%7C%20React%20%7C%20MongoDB-blue.svg)]()

> **A centralized web platform built with Express, Node.js, React, and MongoDB that digitizes student On-Duty (OD) and leave applications, automates multi-role faculty approvals, and synchronizes approved records directly with student attendance.**

---

## 📌 Table of Contents
- [Problem Statement](#-problem-statement)
- [Proposed Solution](#-proposed-solution)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Workflow & Process Flow](#-workflow--process-flow)
- [Tech Stack](#-tech-stack)
- [Quick Start & Setup](#-quick-start--setup)
- [Demo Credentials](#-demo-credentials)
- [API Reference](#-api-reference)
- [Database Schema Design](#-database-schema-design)

---

## 🛑 Problem Statement

In most educational institutions, student **On-Duty (OD)** (for symposiums, sports, internships, hackathons) and **Leave requests** are handled via manual methods:
- Physical paper forms signed and moved between mentors, class advisors, and HODs.
- Verbal approvals and messaging chats where proofs and dates get lost.
- **Critical Failure:** Approved ODs often never get recorded in the attendance register, leading to incorrect attendance drops below 75% and false detention notices.

---

## 💡 Proposed Solution

The **Automated Student OD & Leave Management System** provides:
* **Students:** Apply online, specify date/period ranges, select OD/Leave category, and attach digital proof (PDF, PNG, JPG).
* **Faculty / Mentors:** Review applications on a real-time dashboard, inspect certificate proofs, and approve or reject with audit comments.
* **Attendance Engine:** On approval, the system **automatically synchronizes** the student's attendance register for the target dates and periods to **"OD"** (which counts towards effective attendance percentage).
* **Deans / HODs:** View department rosters, real-time shortage alerts (<75%), and export complete attendance audits to CSV with 1 click.

---

## 💻 Tech Stack

- **Backend:** Node.js (v20+) & Express.js
- **Database & ODM:** MongoDB & Mongoose
- **Frontend:** React (Vite), Lucide Icons, Modern CSS Design System
- **Authentication:** JWT (JSON Web Tokens) with Role-Based Access Control (RBAC) & Bcrypt password hashing
- **File Uploads:** Multer (secure file storage in `/uploads` with type and size limits)
- **Tooling:** Concurrently for unified development server launching

---

## ⚡ Quick Start & Setup

### 1. Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher)
- [MongoDB](https://www.mongodb.com/) running locally on `localhost:27017`

### 2. Installation
Install all dependencies for root, backend, and frontend:
```bash
npm run install:all
```

### 3. Seed Database
Initialize collections and seed demo users, historical attendance, and sample applications:
```bash
npm run seed
```

### 4. Run Application
Start both the Express backend (`http://localhost:5000`) and the React frontend (`http://localhost:5173`):
```bash
# Windows 1-click launch
run.bat

# Or using npm
npm run dev
```

Visit **`http://localhost:5173`** in your browser.

---

## 🔑 Demo Credentials

Quick 1-click demo login buttons are provided on the login screen for each role:

| Role | Name | Email | Password | Identifier |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | Rahul Sharma | `student@college.edu` | `password123` | `CS21B001` |
| **Faculty** | Prof. Ramesh Kumar | `faculty@college.edu` | `password123` | `FAC-CSE-05` |
| **Admin / HOD** | Dr. Anita Rao | `admin@college.edu` | `password123` | `HOD-CSE-01` |

---

## 🔌 API Reference

### Authentication (`/api/auth`)
- `POST /api/auth/login` — Sign in with email and password, receives JWT token
- `POST /api/auth/register` — Register a student account with baseline attendance
- `GET /api/auth/me` — Retrieve currently logged-in user profile

### Student (`/api/student`)
- `GET /api/student/dashboard` — Get attendance metrics, recent attendance grid, and submitted applications
- `POST /api/student/apply` — Submit new OD / Leave application with attached proof (multipart form)

### Faculty (`/api/faculty`)
- `GET /api/faculty/dashboard` — Get pending verification queue with student attendance % and review history
- `POST /api/faculty/review` — Approve or reject application (automatically syncs attendance on approval)

### Administrator (`/api/admin`)
- `GET /api/admin/dashboard` — Institutional summary, student attendance roster, shortage alerts
- `GET /api/admin/export-csv` — Export complete student attendance and OD report as a CSV file

---

## 🗄️ Database Schema Design (MongoDB)

### 1. `users` Collection
Stores registered students, faculty reviewers, and administrators with role enforcement.

### 2. `applications` Collection
Tracks OD and Leave requests, target date/period ranges, uploaded document filenames, status (`PENDING`, `APPROVED`, `REJECTED`), reviewer remarks, and timestamps.

### 3. `attendance` Collection
Maintains student attendance per date and period (1-4). Enforces a unique compound index on `(student_id, date, period)`. Statuses: `PRESENT`, `ABSENT`, `OD`, `ON_LEAVE`.

### 4. `activity_logs` Collection
Audit trail of user actions, application submissions, and approvals.

---

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
