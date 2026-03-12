"""
CAPILLARY RISE v2.0 - INITIALIZATION MODULE
Mission: Bootstrap the autonomous liquidity intelligence organism
Core Function: Initialize Firebase and establish primary capillary mesh
"""
import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore, db
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('capillary.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class CapillaryConfig:
    """Central configuration for capillary mesh"""
    firebase_cred_path: str = "firebase_creds.json"
    default_capital_per_agent: float = 0.02  # ETH
    heartbeat_interval_seconds: int = 30
    max_concurrent_opportunities: int = 5
    risk_circuit_breaker_losses: int = 3
    
    # RPC endpoint rotation (to be populated via environment/browser tasks)
    rpc_endpoints: Dict[str, list] = None
    
    def __post_init__(self):
        if self.rpc_endpoints is None:
            self.rpc_endpoints = {
                'ethereum': [],
                'arbitrum': [],
                'polygon': [],
                'optimism': [],
                'bsc': [],
                'avalanche': []
            }

class FirebaseManager:
    """Singleton manager for Firebase connections with robust error handling"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.firestore_client = None
            self.realtime_db = None
            self._initialized = True
    
    def initialize(self, config: CapillaryConfig) -> bool:
        """
        Initialize Firebase connection with comprehensive error handling
        Returns: True if successful, False otherwise
        """
        try:
            # Validate credential file exists
            if not os.path.exists(config.firebase_cred_path):
                logger.error(f"Firebase credential file not found: {config.firebase_cred_path}")
                logger.info("Please create Firebase project via browser task and download service account JSON")
                return False
            
            # Load credentials
            cred = credentials.Certificate(config.firebase_cred_path)
            
            # Initialize app (handle multiple initializations)
            try:
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://curiosity-capillary-default-rtdb.firebaseio.com/'
                })
            except ValueError as e:
                if "already exists" not in str(e):
                    raise
                logger.warning("Firebase app already initialized, reusing")
            
            # Initialize clients
            self.firestore_client = firestore.client()
            self.realtime_db = db.reference()
            
            # Test connection
            self._test_connections()
            
            logger.info("✅ Firebase initialized successfully")
            return True
            
        except FileNotFoundError as e:
            logger.error(f"Credential file error: {e}")
            return False
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}", exc_info=True)
            return False
    
    def _test_connections(self) -> None:
        """Test both Firestore and Realtime DB connections"""
        # Test Firestore
        test_ref = self.firestore_client.collection('health_check').document('test')
        test_ref.set({'timestamp': firestore.SERVER_TIMESTAMP})
        test_ref.delete()
        
        # Test Realtime DB
        self.realtime_db.child('health_check').set({'status': 'ok'})
        self.realtime_db.child('health_check').delete()
        
        logger.debug("Firebase connection tests passed")
    
    def get_firestore(self) -> firestore.Client:
        """Get Firestore client with validation"""
        if self.firestore_client is None:
            raise RuntimeError("Firebase not initialized. Call initialize() first.")
        return self.firestore_client
    
    def get_realtime_db(self) -> db.Reference:
        """Get Realtime Database reference with validation"""
        if self.realtime_db is None:
            raise RuntimeError("Firebase not initialized. Call initialize() first.")
        return self.realtime_db

def initialize_capillary_mesh(config_path: str = None) -> Optional[tuple]:
    """
    Main initialization function for capillary mesh
    Returns: (FirebaseManager, CapillaryConfig) if successful, None otherwise
    """
    try:
        # Load configuration
        config = CapillaryConfig()
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        
        # Initialize Firebase
        fb_manager = FirebaseManager()
        if not fb_manager.initialize(config):
            logger.error("Failed to initialize Firebase. Cannot proceed.")
            return None
        
        # Initialize Firestore schema if needed
        _initialize_firestore_schema(fb_manager.get_firestore())
        
        logger.info("🚀 Capillary Mesh Initialized Successfully")
        logger.info(f"• Default capital per agent: {config.default_capital_per_agent} ETH")
        logger.info(f"• Target chains: {list(config.rpc_endpoints.keys())}")
        logger.info(f"• Heartbeat interval: {config.heartbeat_interval_seconds}s")
        
        return fb_manager, config
        
    except Exception as e:
        logger.error(f"Capillary mesh initialization failed: {e}", exc_info=True)
        return None

def _initialize_firestore_schema(firestore_client: firestore.Client) -> None:
    """Initialize required collections with proper indexes"""
    collections = ['agents', 'opportunities', 'intelligence', 'raw_mempool', 'analytics']
    
    for collection in collections:
        # Create collection reference (they're created automatically on first write)
        coll_ref = firestore_client.collection(collection)
        
        # Add a dummy document if empty (to ensure collection exists)
        docs = coll_ref.limit(1).stream()
        if not any(True for _ in docs):
            dummy_ref = coll_ref.document('_schema_init')
            dummy_ref.set({
                'initialized': firestore.SERVER_TIMESTAMP,
                'purpose': 'Collection initialization'
            })
            dummy_ref.delete()  # Clean up
            
    logger.info("Firestore schema initialized")

if __name__ == "__main__":
    # Command-line initialization
    import argparse
    parser = argparse.ArgumentParser(description="Initialize Capillary Rise v2.0")
    parser.add_argument("--config", help="Path to config JSON file")
    args = parser.parse_args()
    
    result = initialize_capillary_mesh(args.config)
    if result:
        print("✅ Initialization successful")
        sys.exit(0)
    else:
        print("❌ Initialization failed")
        sys.exit(1)