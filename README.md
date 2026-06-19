# Multi-Agent Traffic Negotiation Simulator

<p align="center">
  Multi-agent traffic simulation platform for autonomous vehicle coordination, communication, negotiation, and reinforcement learning.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-Backend-blue" />
  <img src="https://img.shields.io/badge/FastAPI-API-green" />
  <img src="https://img.shields.io/badge/React-Frontend-61DAFB" />
  <img src="https://img.shields.io/badge/Multi--Agent-Systems-orange" />
  <img src="https://img.shields.io/badge/Reinforcement-Learning-purple" />
</p>

---

## Overview

Urban traffic congestion continues to impact mobility, fuel efficiency, economic productivity, and environmental sustainability. Traditional traffic management systems often rely on centralized control mechanisms and fixed policies that struggle to adapt to rapidly changing traffic conditions.

This project explores a decentralized alternative where autonomous vehicles operate as intelligent agents capable of perceiving their environment, communicating with nearby agents, negotiating decisions, and learning cooperative behaviors.

The simulator serves as a platform for studying how autonomous vehicles can coordinate safely and efficiently while balancing individual objectives with collective traffic goals.

---

## Key Capabilities

### Autonomous Vehicle Agents

Each vehicle is modeled as an independent agent with:

* Position awareness
* Speed and motion control
* Direction and destination tracking
* Waiting time monitoring
* Priority handling
* State-based behavior

### Agent Communication

Agents exchange information about:

* Position
* Speed
* Direction
* Intent
* Local traffic conditions

Enabling cooperative and decentralized decision-making.

### Negotiation Framework

Vehicles can coordinate actions through negotiation mechanisms that support:

* Conflict resolution
* Priority determination
* Cooperative yielding
* Resource sharing
* Safe traffic movement

### Reinforcement Learning Environment

The simulator is designed as a training environment for learning:

* Efficient navigation policies
* Cooperative strategies
* Congestion reduction behaviors
* Safety-aware decision making
* Traffic optimization techniques

---

## System Architecture

```text
┌─────────────────────────────┐
│     Traffic Environment     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│     Vehicle Agents          │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│     Communication Layer     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│     Negotiation Engine      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Reinforcement Learning Layer│
└─────────────────────────────┘
```

---

## Agent Lifecycle

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

Each agent continuously evaluates its environment and updates its behavior according to surrounding traffic conditions.

---

## Features

### Simulation Engine

* Real-time traffic simulation
* Dynamic vehicle generation
* Agent lifecycle management
* Safety monitoring
* Collision detection
* Configurable traffic density

### Multi-Agent Framework

* Autonomous vehicle agents
* State-driven behavior model
* Decentralized coordination
* Negotiation support
* Extensible communication architecture

### Analytics & Monitoring

* Traffic flow statistics
* Safety metrics
* Agent state monitoring
* Throughput analysis
* Real-time dashboard

### Interactive Dashboard

* Live simulation visualization
* Agent monitoring
* Traffic analytics
* Safety analytics
* Simulation controls

---

## Technology Stack

| Layer      | Technology                       |
| ---------- | -------------------------------- |
| Backend    | Python, FastAPI                  |
| Frontend   | React, Vite                      |
| Simulation | Custom Traffic Engine            |
| Agents     | Autonomous Agent Model           |
| AI         | Reinforcement Learning           |

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

Backend URL:

```text
http://localhost:8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

## Running the Simulator

1. Start the backend server.
2. Start the frontend application.
3. Open the dashboard in your browser.
4. Configure traffic density.
5. Observe agent behavior and system metrics in real time.

---

## Metrics

### Traffic Metrics

* Active Vehicles
* Waiting Vehicles
* Crossing Vehicles
* Throughput
* Total Spawned Vehicles

### Safety Metrics

* Safe Crossings
* Failed Crossings
* Collisions
* Passing Accuracy

### Agent Metrics

* Agent States
* Waiting Times
* Negotiation Statistics
* Communication Statistics

---

## Research Applications

This platform can be used to study:

* Multi-Agent Systems
* Autonomous Vehicles
* Vehicle-to-Vehicle Communication
* Reinforcement Learning
* Cooperative Decision Making
* Distributed Coordination
* Intelligent Transportation Systems
* Traffic Optimization

---

## Future Extensions

The architecture is designed to support a wide range of traffic scenarios, including:

* Lane-change negotiation
* Highway merging
* Roundabouts
* Multi-intersection networks
* Urban road networks
* Emergency vehicle prioritization
* Large-scale agent coordination

---

## License

This project is intended for educational, research, and experimentation purposes.
