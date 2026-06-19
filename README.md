# Multi-Agent Traffic Negotiation Simulator

An autonomous intersection management simulator where vehicles act as intelligent agents that coordinate intersection access through communication and negotiation instead of relying on traditional traffic signals.

---

## Overview

Traditional intersections depend on traffic lights and fixed timing systems to regulate vehicle movement. While effective, these systems cannot adapt dynamically to changing traffic conditions and often introduce unnecessary delays.

This project explores an alternative approach where vehicles behave as autonomous agents capable of sharing information, coordinating actions, and negotiating access to an intersection.

The simulator provides a controlled environment for studying:

* Autonomous traffic coordination
* Vehicle-to-Vehicle (V2V) communication
* Multi-agent decision making
* Collision avoidance strategies
* Traffic efficiency and throughput
* Intelligent transportation systems

---

## Problem Statement

Conventional traffic control systems face several limitations:

* Fixed traffic signal timings
* Unnecessary waiting during low traffic conditions
* Limited adaptability to real-time traffic flow
* Inefficient utilization of intersection space

The goal of this project is to investigate whether intelligent autonomous agents can coordinate intersection access more efficiently while maintaining safety.

---

## How It Works

The simulator models a four-way road intersection where vehicles are represented as autonomous agents.

Each agent maintains information such as:

* Position
* Speed
* Direction
* Destination
* Waiting time
* Priority
* Internal state

Agents progress through a state-based lifecycle:

```text
APPROACHING
    ↓
NEGOTIATING
    ↓
WAITING
    ↓
CROSSING
    ↓
EXITED
```

The system continuously updates vehicle movement, intersection occupancy, safety constraints, and performance metrics.

---

## Features

### Autonomous Vehicle Agents

* Agent-based vehicle representation
* State-driven behavior model
* Waiting time and priority tracking
* Real-time state transitions

### Intersection Simulation

* Four-way intersection environment
* Continuous vehicle spawning
* Dynamic traffic density control
* Vehicle movement and path management

### Safety Monitoring

* Collision detection
* Safe crossing tracking
* Passing accuracy metrics
* Traffic flow statistics

### Visualization Dashboard

* Real-time simulation rendering
* Agent state monitoring
* Traffic metrics
* Safety metrics
* Simulation controls

---

## Technology Stack

### Backend

* Python
* FastAPI

### Frontend

* React
* Vite

### Simulation

* Custom traffic simulation engine
* Agent-based vehicle model

---

## Installation

### Clone Repository

```bash
git clone <repository-url>
cd <repository-name>
```

### Backend Setup

```bash
pip install -r requirements.txt
```

Start backend:

```bash
uvicorn backend.main:app --reload
```

Backend runs on:

```text
http://localhost:8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

---

## Usage

1. Start both backend and frontend servers.
2. Open the frontend in a browser.
3. Adjust traffic density using the control panel.
4. Observe vehicle behavior at the intersection.
5. Monitor traffic and safety metrics in real time.

---

## Metrics

The simulator tracks:

### Traffic Metrics

* Active vehicles
* Waiting vehicles
* Crossing vehicles
* Total spawned vehicles

### Safety Metrics

* Collisions
* Safe crossings
* Failed crossings
* Passing accuracy

---

## Research Applications

This project can be used to study:

* Autonomous traffic management
* Multi-agent systems
* Intelligent transportation systems
* Cooperative vehicle behavior
* Traffic optimization strategies
* Reinforcement learning environments

---

## License

This project is intended for educational, research, and experimentation purposes.
