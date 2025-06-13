"""
Enhanced configuration parser module for game-specific benchmark configurations.
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ConfigParser:
    """Handles loading and parsing game benchmark YAML configurations."""
    
    def __init__(self, config_path: str):
        """
        Initialize the config parser with a game-specific configuration.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Raises:
            FileNotFoundError: If the config file doesn't exist
            ValueError: If the config file is invalid
        """
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
        
        # Extract game metadata
        self.game_name = self.config.get("metadata", {}).get("game_name", "Unknown Game")
        logger.info(f"ConfigParser initialized for {self.game_name} using {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load the YAML configuration file.
        
        Returns:
            Parsed configuration as a dictionary
        
        Raises:
            FileNotFoundError: If the config file doesn't exist
            yaml.YAMLError: If the YAML is invalid
        """
        if not os.path.exists(self.config_path):
            logger.error(f"Config file not found: {self.config_path}")
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML config: {str(e)}")
            raise
    
    def _validate_config(self) -> bool:
        """
        Validate the configuration structure with enhanced checks for game benchmarks.
        
        Returns:
            True if valid
        
        Raises:
            ValueError: If the config is invalid
        """
        # Check for required sections
        required_sections = ["states", "transitions", "initial_state", "target_state"]
        for section in required_sections:
            if section not in self.config:
                logger.error(f"Missing required section '{section}' in config")
                raise ValueError(f"Invalid config: missing '{section}' section")
        
        # Validate metadata section
        metadata = self.config.get("metadata", {})
        if not metadata.get("game_name"):
            logger.warning("No game_name specified in metadata")
            
        # Check if benchmark duration is present
        if "benchmark_duration" not in metadata:
            logger.warning("No benchmark_duration specified in metadata, using default")
            
        # Validate states
        states = self.config.get("states", {})
        if not isinstance(states, dict) or not states:
            logger.error("States section must be a non-empty dictionary")
            raise ValueError("Invalid config: states section must be a non-empty dictionary")
        
        # Validate transitions
        transitions = self.config.get("transitions", {})
        if not isinstance(transitions, dict) or not transitions:
            logger.error("Transitions section must be a non-empty dictionary")
            raise ValueError("Invalid config: transitions section must be a non-empty dictionary")
        
        # Validate states referenced in transitions
        for transition_key in transitions:
            try:
                from_state, to_state = transition_key.split("->")
                
                if from_state not in states and from_state != "initial":
                    logger.warning(f"Transition references undefined from_state: {from_state}")
                
                if to_state not in states and to_state != "completed":
                    logger.warning(f"Transition references undefined to_state: {to_state}")
            except ValueError:
                logger.error(f"Invalid transition key format: {transition_key}")
                raise ValueError(f"Invalid transition key: {transition_key}, must be 'from_state->to_state'")
        
        # Validate initial and target states
        initial_state = self.config.get("initial_state")
        target_state = self.config.get("target_state")
        
        if initial_state not in states and initial_state != "initial":
            logger.warning(f"Initial state '{initial_state}' not defined in states section")
        
        if target_state not in states and target_state != "completed":
            logger.warning(f"Target state '{target_state}' not defined in states section")
        
        # Validate fallbacks section if present
        fallbacks = self.config.get("fallbacks", {})
        if fallbacks and not isinstance(fallbacks, dict):
            logger.error("Fallbacks section must be a dictionary")
            raise ValueError("Invalid config: fallbacks section must be a dictionary")
        
        logger.info("Configuration validation successful")
        return True
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the parsed configuration.
        
        Returns:
            Configuration dictionary
        """
        return self.config
    
    def get_state_definition(self, state_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the definition for a specific state.
        
        Args:
            state_name: Name of the state
        
        Returns:
            State definition dictionary or None if not found
        """
        states = self.config.get("states", {})
        return states.get(state_name)
        
    def get_game_metadata(self) -> Dict[str, Any]:
        """
        Get game metadata from the configuration.
        
        Returns:
            Metadata dictionary with game information
        """
        return self.config.get("metadata", {})