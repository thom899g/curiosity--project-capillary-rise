"""
CAPILLARY AGENTS - DISTRIBUTED AGENT SYSTEM
Core Function: Implement the triune brain system (Listener, Analyst, Executor)
"""
import asyncio
import time
import random
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
from web3 import Web3
from firebase_admin import firestore

logger = logging.getLogger(__name__)

class AgentType(Enum):
    LISTENER = "listener"
    ANALYST = "analyst"
    EXECUTOR = "executor"

class AgentStatus(Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    FAILED = "failed"
    TRAINING = "training"

@dataclass
class AgentMetrics:
    """Performance metrics for agent monitoring"""
    opportunities_processed: int = 0
    successes: int = 0
    failures: int = 0
    total_profit_eth: float = 0.0
    avg_execution_time_ms: float = 0.0
    last_activity: float = field(default_factory=time.time)
    
    def success_rate(self) -> float:
        if self.opportunities_processed == 0:
            return 0.0
        return self.successes / self.opportunities_processed
    
    def record_success(self, profit_eth: float, exec_time_ms: float):
        self.opportunities_processed += 1
        self.successes += 1
        self.total_profit_eth += profit_eth
        self._update_avg_time(exec_time_ms)
        self.last_activity = time.time()
    
    def record_failure(self, exec_time_ms: float):
        self.opportunities_processed += 1
        self.failures += 1
        self._update_avg_time(exec_time_ms)
        self.last_activity = time.time()
    
    def _update_avg_time(self, new_time_ms: float):
        total_time = self.avg_execution_time_ms * (self.opportunities_processed - 1)
        self.avg_execution_time_ms = (total_time + new_time_ms) / self.opportunities_processed

class BaseAgent:
    """Base class for all capillary agents with common functionality"""
    
    def __init__(self, agent_id: str, agent_type: AgentType, chain: str, 
                 firestore_client: firestore.Client, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.chain = chain
        self.firestore = firestore_client
        self.config = config
        self.metrics = AgentMetrics()
        self.status = AgentStatus.ACTIVE
        self.heartbeat_interval = config.get('heartbeat_interval_seconds', 30)
        self.should_run = True
        
        # Register agent
        self._register_agent()
    
    def _register_agent(self) -> None:
        """Register agent in Firestore"""
        try:
            agent_ref = self.firestore.collection('agents').document(self.agent_id)
            agent_ref.set({
                'agent_id': self.agent_id,
                'type': self.agent_type.value,
                'chain': self.chain,
                'status': self.status.value,
                'created_at': firestore.SERVER_TIMESTAMP,
                'config': self.config,
                'metrics': asdict(self.metrics)
            })
            logger.info(f"Registered agent {self.agent_id} ({self.agent_type.value}) for {self.chain}")
        except Exception as e:
            logger.error(f"Failed to register agent {self.agent_id}: {e}")
    
    def update_heartbeat(self) -> None:
        """Update agent heartbeat in Firestore"""
        try:
            agent_ref = self.firestore.collection('agents').document(self.agent_id)
            agent_ref.update({
                'last_heartbeat': firestore.SERVER_TIMESTAMP,
                'status': self.status.value,
                'metrics': asdict(self.metrics)
            })
        except Exception as e:
            logger.error(f"Heartbeat update failed for {self.agent_id}: {e}")
    
    def change_status(self, new_status: AgentStatus) -> None:
        """Update agent status with validation"""
        old_status = self.status
        self.status = new_status
        
        try:
            agent_ref = self.firestore.collection('agents').document(self.agent_id)
            agent_ref.update({
                'status': new_status.value,
                'status_changed_at': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"Agent {self.agent_id} status changed: {old_status.value} -> {new_status.value}")
        except Exception as e:
            logger.error(f"Failed to update agent status: {e}")
            self.status = old_status  # Revert on error
    
    def run_heartbeat_loop(self) -> None:
        """Background heartbeat loop with jitter"""
        import threading
        
        def heartbeat_worker():
            while self.should_run:
                try:
                    self.update_heartbeat()
                except Exception as e:
                    logger.error(f"Heartbeat error for {self.agent_id}: {e}")
                
                # Jitter: 30s ± 5s
                sleep_time = self.heartbeat_interval + random.uniform(-5, 5)
                time.sleep(sleep_time)
        
        thread = threading.Thread(target=heartbeat_worker, daemon=True)
        thread.start()
        logger.debug(f"Heartbeat loop started for {self.agent_id}")
    
    def stop(self) -> None:
        """Graceful agent shutdown"""
        self.should_run = False
        self.change_status(AgentStatus.DORMANT)
        logger.info(f"Agent {self.agent_id} stopped")

class ListenerAgent(BaseAgent):
    """Layer 1: Instinctual - Monitors mempool for opportunities"""
    
    def __init__(self, agent_id: str, chain: str, rpc_endpoints: List[str],
                 firestore_client: firestore.Client, config: Dict[str, Any]):
        super().__init__(agent_id, AgentType.LISTENER, chain, firestore_client, config)
        self.rpc_endpoints = rpc_endpoints
        self.current_endpoint_idx = 0
        self.web3 = self._initialize_web3()
        self.pending_txs = set()
    
    def _initialize_web3(self) -> Web3:
        """Initialize Web3 with failover endpoints"""
        endpoint = self.rpc_endpoints[self.current_endpoint_idx % len(self.rpc_endpoints)]
        try:
            w3 = Web3(Web3.WebsocketProvider(endpoint))
            if w3.is_connected():
                logger.info(f"Listener {self.agent_id} connected to {endpoint[:30]}...")
                return w3
            else:
                raise ConnectionError("Web3 connection failed")
        except Exception as e:
            logger.error(f"Failed to connect to {endpoint[:30]}: {e}")
            # Rotate to next endpoint
            self.current_endpoint_idx += 1
            return self._initialize_web3()
    
    async def listen_for_pending_transactions(self) -> None:
        """Subscribe to pending transactions with anomaly detection"""
        from sklearn.ensemble import IsolationForest
        import pandas as pd
        import numpy as np
        
        # Initialize anomaly detection
        anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
        gas_price_history = []
        
        while self.should_run:
            try:
                # Subscribe to pending transactions
                subscription_id = self.web3.eth.subscribe('pendingTransactions')
                
                for _ in range(100):  # Process batch of transactions
                    try:
                        tx_hash = await asyn