import { useState, useEffect, useRef } from 'react';
import './TrafficVisualization.css';

const API_URL = 'http://localhost:8000';
const POLL_INTERVAL = 500; // Backend update interval (ms)
const INTERPOLATION_SPEED = 0.15; // Smooth interpolation factor

export default function TrafficVisualization() {
  const [trafficState, setTrafficState] = useState({ vehicles: [] });
  const [roadInfo, setRoadInfo] = useState(null);
  const [intersectionState, setIntersectionState] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  
  // Store interpolated positions for smooth movement
  const vehiclePositionsRef = useRef(new Map());
  const animationFrameRef = useRef(null);

  // Fetch road configuration once on moun