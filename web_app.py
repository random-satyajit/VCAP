"""
Enhanced Flask Web Application for Game UI Navigation Automation Tool
Rewritten to exactly match the GUI application's look and functionality.
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import logging
import queue
import yaml
import glob
import json
import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Enhanced logging handler for web interface
class WebSocketHandler(logging.Handler):
    """Send logging records to web clients via WebSocket - matches GUI QueueHandler"""
    def __init__(self, socketio):
        super().__init__()
        self.socketio = socketio

    def emit(self, record):
        # Format exactly like GUI app
        log_entry = {
            'timestamp': time.strftime('%H:%M:%S', time.localtime(record.created)),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.name,
            'line': record.lineno if hasattr(record, 'lineno') else None
        }
        
        # Include exception info if present
        if record.exc_info:
            import traceback
            log_entry['exception'] = traceback.format_exception(*record.exc_info)
        
        self.socketio.emit('log_message', log_entry)

class HybridConfigParser:
    """Exact copy of HybridConfigParser from GUI app"""
    
    def __init__(self, config_path: str):
        """Initialize the hybrid config parser."""
        self.config_path = config_path
        self.config = self._load_config()
        self.config_type = self._detect_config_type()
        self._validate_config()
        
        # Extract game metadata
        self.game_name = self.config.get("metadata", {}).get("game_name", "Unknown Game")
        logging.getLogger(__name__).info(f"HybridConfigParser initialized for {self.game_name} using {config_path} (type: {self.config_type})")
    
    def _load_config(self):
        """Load the YAML configuration file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML config: {str(e)}")
    
    def _detect_config_type(self):
        """Detect whether this is a step-based or state machine configuration."""
        if "steps" in self.config:
            return "steps"
        elif "states" in self.config and "transitions" in self.config:
            return "state_machine"
        else:
            logging.getLogger(__name__).warning("Could not determine config type, defaulting to state_machine")
            return "state_machine"
    
    def _validate_config(self):
        """Validate the configuration structure based on detected type."""
        if self.config_type == "steps":
            return self._validate_steps_config()
        else:
            return self._validate_state_machine_config()
    
    def _validate_steps_config(self):
        """Validate step-based configuration."""
        if "steps" not in self.config:
            raise ValueError("Invalid config: missing 'steps' section")
        
        steps = self.config.get("steps", {})
        if not isinstance(steps, dict) or not steps:
            raise ValueError("Invalid config: steps section must be a non-empty dictionary")
        
        return True
    
    def _validate_state_machine_config(self):
        """Validate state machine configuration."""
        required_sections = ["states", "transitions", "initial_state", "target_state"]
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Invalid config: missing '{section}' section")
        
        return True
    
    def get_config(self):
        """Get the parsed configuration."""
        return self.config
    
    def get_config_type(self):
        """Get the detected configuration type."""
        return self.config_type
    
    def is_step_based(self):
        """Check if this is a step-based configuration."""
        return self.config_type == "steps"
    
    def get_state_definition(self, state_name: str):
        """Get the definition for a specific state (state machine configs only)."""
        if self.config_type != "state_machine":
            return None
        states = self.config.get("states", {})
        return states.get(state_name)
    
    def get_game_metadata(self):
        """Get game metadata from the configuration."""
        return self.config.get("metadata", {})

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'katana_automation_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global automation state - matches GUI app structure
automation_state = {
    'running': False,
    'status': 'Ready',
    'automation_thread': None,
    'stop_event': None,
    'game_name': 'Unknown Game',
    'current_run_dir': None,
    'path_auto_loaded': False
}

def setup_logger():
    """Setup logging exactly like GUI app"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler(f"logs/web_run_{time.strftime('%Y_%m_%d__%H_%M_%S')}.log")
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # WebSocket handler for GUI
    websocket_handler = WebSocketHandler(socketio)
    websocket_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                           datefmt='%H:%M:%S')
    websocket_handler.setFormatter(websocket_formatter)
    logger.addHandler(websocket_handler)
    
    return logger

logger = setup_logger()

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/config/list')
def list_configs():
    """List available configuration files - matches GUI browse functionality"""
    configs = []
    
    # Check config/games/ directory first
    games_dir = "config/games"
    if os.path.exists(games_dir):
        for file in glob.glob(f"{games_dir}/*.yaml"):
            configs.append(file.replace('\\', '/'))
        for file in glob.glob(f"{games_dir}/*.yml"):
            configs.append(file.replace('\\', '/'))
    
    # Check config/ directory
    config_dir = "config"
    if os.path.exists(config_dir):
        for file in glob.glob(f"{config_dir}/*.yaml"):
            if 'template' not in file.lower() and 'games' not in file:
                configs.append(file.replace('\\', '/'))
        for file in glob.glob(f"{config_dir}/*.yml"):
            if 'template' not in file.lower() and 'games' not in file:
                configs.append(file.replace('\\', '/'))
    
    return jsonify(configs)

@app.route('/api/config/load', methods=['POST'])
def load_config():
    """Load and parse configuration file - exactly like GUI load_game_info"""
    try:
        config_path = request.json.get('path')
        if not config_path or not os.path.exists(config_path):
            return jsonify({'error': 'Config file not found'}), 404
        
        # Use HybridConfigParser exactly like GUI
        config_parser = HybridConfigParser(config_path)
        config = config_parser.get_config()
        metadata = config_parser.get_game_metadata()
        
        # Extract game information exactly like GUI
        game_name = metadata.get("game_name", os.path.basename(config_path).replace('.yaml', ''))
        benchmark_duration = metadata.get("benchmark_duration", "Unknown")
        resolution = metadata.get("resolution", "Any")
        preset = metadata.get("preset", "Any")
        
        # Update global state
        automation_state['game_name'] = game_name
        
        game_info = {
            'game_name': game_name,
            'benchmark_duration': benchmark_duration,
            'resolution': resolution,
            'preset': preset,
            'config_type': config_parser.get_config_type(),
            'game_path': metadata.get("path", "")  # Auto-populate game path
        }
        
        logger.info(f"Loaded config for game: {game_name} (type: {config_parser.get_config_type()})")
        
        return jsonify(game_info)
        
    except Exception as e:
        logger.error(f"Failed to load game config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/omniparser/test', methods=['POST'])
def test_omniparser():
    """Test Omniparser connection - matches GUI test_omniparser_connection"""
    try:
        import requests
        url = request.json.get('url', 'http://localhost:8000')
        response = requests.get(f"{url}/probe", timeout=5)
        
        if response.status_code == 200:
            logger.info("Successfully connected to Omniparser server!")
            return jsonify({'status': 'success', 'message': 'Successfully connected to Omniparser server!'})
        else:
            logger.error(f"Failed to connect to Omniparser server: HTTP {response.status_code}")
            return jsonify({'status': 'error', 'message': f'Failed to connect to Omniparser server: HTTP {response.status_code}'}), 400
            
    except Exception as e:
        logger.error(f"Failed to connect to Omniparser server: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Failed to connect to Omniparser server: {str(e)}'}), 400

@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """Start automation - matches GUI start_automation exactly"""
    global automation_state
    
    if automation_state['running']:
        return jsonify({'error': 'Automation is already running'}), 400
    
    try:
        settings = request.json
        
        # Validate inputs exactly like GUI
        try:
            port = int(settings['sut_port'])
            iterations = int(settings['max_iterations'])
            if port <= 0 or iterations <= 0:
                raise ValueError("Port and max iterations must be positive integers")
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        if not settings.get('sut_ip'):
            return jsonify({'error': 'SUT IP address is required'}), 400
            
        if not settings.get('config_path') or not os.path.exists(settings['config_path']):
            return jsonify({'error': 'Config file does not exist'}), 400
        
        # Load game info to ensure we have the game name
        try:
            config_parser = HybridConfigParser(settings['config_path'])
            automation_state['game_name'] = config_parser.get_game_metadata().get('game_name', 'Unknown Game')
        except Exception as e:
            logger.error(f"Failed to parse config: {str(e)}")
            return jsonify({'error': f'Invalid config file: {str(e)}'}), 400
        
        # Clear stop event and update state
        automation_state['stop_event'] = threading.Event()
        automation_state['running'] = True
        automation_state['status'] = 'Running'
        
        # Start automation in separate thread
        automation_state['automation_thread'] = threading.Thread(
            target=run_automation_process,
            args=(settings,),
            daemon=True
        )
        automation_state['automation_thread'].start()
        
        # Send status update
        socketio.emit('status_update', {'status': 'Running', 'running': True})
        logger.info(f"Starting automation process for {automation_state['game_name']}...")
        
        return jsonify({'status': 'success', 'message': 'Automation started'})
        
    except Exception as e:
        automation_state['running'] = False
        automation_state['status'] = 'Error'
        logger.error(f"Failed to start automation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/automation/stop', methods=['POST'])
def stop_automation():
    """Stop automation - matches GUI stop_automation"""
    global automation_state
    
    if not automation_state['running']:
        return jsonify({'error': 'Automation is not running'}), 400
    
    try:
        logger.info("Stopping automation process...")
        
        if automation_state['stop_event']:
            automation_state['stop_event'].set()
        
        automation_state['running'] = False
        automation_state['status'] = 'Stopped'
        
        socketio.emit('status_update', {'status': 'Stopped', 'running': False})
        
        return jsonify({'status': 'success', 'message': 'Automation stopped'})
        
    except Exception as e:
        logger.error(f"Failed to stop automation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Clear logs - matches GUI clear_logs"""
    socketio.emit('clear_logs')
    return jsonify({'status': 'success'})

@app.route('/api/status')
def get_status():
    """Get current status"""
    return jsonify({
        'running': automation_state['running'],
        'status': automation_state['status'],
        'game_name': automation_state['game_name']
    })

# WebSocket events - match GUI app behavior
@socketio.on('connect')
def handle_connect():
    """Handle client connection - matches GUI"""
    logger.info("Web client connected")
    emit('status_update', {
        'status': automation_state['status'],
        'running': automation_state['running']
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Web client disconnected")

def run_automation_process(settings):
    """Run automation process - matches GUI run_automation exactly"""
    global automation_state
    
    try:
        # Parse configuration with hybrid parser
        config_parser = HybridConfigParser(settings['config_path'])
        config = config_parser.get_config()
        
        if config_parser.is_step_based():
            # Use SimpleAutomation for step-based configs
            logger.info("Using SimpleAutomation for step-based configuration")
            success = _run_simple_automation(config_parser, config, settings)
        else:
            # Use state machine automation
            logger.info("Using state machine automation")
            success = _run_state_machine_automation(config_parser, config, settings)
        
        # Update final status
        if success:
            automation_state['status'] = 'Completed'
            socketio.emit('status_update', {'status': 'Completed', 'running': False})
        elif automation_state['stop_event'] and automation_state['stop_event'].is_set():
            automation_state['status'] = 'Stopped'
            socketio.emit('status_update', {'status': 'Stopped', 'running': False})
        else:
            automation_state['status'] = 'Failed'
            socketio.emit('status_update', {'status': 'Failed', 'running': False})
            
    except Exception as e:
        logger.error(f"Error in automation process: {str(e)}", exc_info=True)
        automation_state['status'] = 'Error'
        socketio.emit('status_update', {'status': 'Error', 'running': False})
    finally:
        automation_state['running'] = False
        logger.info("Automation process completed")

def _run_simple_automation(config_parser, config, settings):
    """Run SimpleAutomation - matches GUI _run_simple_automation exactly"""
    try:
        # Import required modules
        from modules.network import NetworkManager
        from modules.screenshot import ScreenshotManager
        from modules.gemma_client import GemmaClient
        from modules.qwen_client import QwenClient
        from modules.omniparser_client import OmniparserClient
        from modules.annotator import Annotator
        from modules.simple_automation import SimpleAutomation
        from modules.game_launcher import GameLauncher
        
        # Create timestamp for this run
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create game-specific directory structure
        os.makedirs("logs", exist_ok=True)
        game_dir = f"logs/{automation_state['game_name']}" if automation_state['game_name'] else "logs"
        os.makedirs(game_dir, exist_ok=True)

        # Create run-specific directory
        run_dir = f"{game_dir}/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)
        os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
        os.makedirs(f"{run_dir}/annotated", exist_ok=True)
        
        # Store the current run directory
        automation_state['current_run_dir'] = run_dir
        
        # Set up run-specific logging
        run_log_file = f"{run_dir}/automation.log"
        run_file_handler = logging.FileHandler(run_log_file)
        run_file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        run_file_handler.setFormatter(run_file_formatter)
        logging.getLogger().addHandler(run_file_handler)
        
        logger.info(f"Created run directory: {run_dir}")
        logger.info(f"Logs will be saved to: {run_log_file}")
        
        # Initialize components
        logger.info(f"Connecting to SUT at {settings['sut_ip']}:{settings['sut_port']}")
        network = NetworkManager(settings['sut_ip'], int(settings['sut_port']))
        
        logger.info("Initializing components...")
        screenshot_mgr = ScreenshotManager(network)
        
        # Initialize the vision model based on user selection
        if settings.get('vision_model') == 'gemma':
            logger.info("Using Gemma for UI detection")
            vision_model = GemmaClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'qwen':
            logger.info("Using Qwen VL for UI detection")
            vision_model = QwenClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'omniparser':
            logger.info("Using Omniparser for UI detection")
            vision_model = OmniparserClient(settings.get('omniparser_url', 'http://localhost:8000'))
        else:
            logger.info("Using default Gemma for UI detection")
            vision_model = GemmaClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
            
        annotator = Annotator()
        game_launcher = GameLauncher(network)
        
        # Get game metadata
        game_metadata = config_parser.get_game_metadata()
        logger.info(f"Game metadata loaded: {game_metadata}")
        startup_wait = game_metadata.get("startup_wait", 30)
        
        try:
            # Launch the game only if a path is provided
            if settings.get('game_path'):
                logger.info(f"Launching game from: {settings['game_path']}")
                game_launcher.launch(settings['game_path'])
                
                # Wait for game to initialize
                logger.info(f"Waiting {startup_wait} seconds for game to fully initialize...")
                wait_time = startup_wait
                for i in range(wait_time):
                    if automation_state['stop_event'].is_set():
                        break
                    time.sleep(1)
                    if i % 5 == 0:
                        socketio.emit('status_update', {
                            'status': f'Initializing ({wait_time-i}s)', 
                            'running': True
                        })
            else:
                logger.info("No game path provided, assuming game is already running")
            
            if automation_state['stop_event'].is_set():
                logger.info("Automation stopped during initialization")
                return False
                
            socketio.emit('status_update', {'status': 'Running', 'running': True})
            
            # Use SimpleAutomation
            logger.info("Starting SimpleAutomation...")
            
            # Configure simple automation with run-specific directory
            simple_auto = SimpleAutomation(
                config_path=settings['config_path'],
                network=network,
                screenshot_mgr=screenshot_mgr,
                vision_model=vision_model,
                stop_event=automation_state['stop_event'],
                run_dir=run_dir,
                annotator=annotator
            )
            
            # Run the simple automation
            success = simple_auto.run()
            
            return success
                
        except Exception as e:
            logger.error(f"Error in simple automation execution: {str(e)}", exc_info=True)
            return False
            
        finally:
            # Cleanup
            if 'network' in locals():
                network.close()
            if 'vision_model' in locals() and hasattr(vision_model, 'close'):
                vision_model.close()
            # Remove the run-specific log handler
            if 'run_file_handler' in locals():
                logging.getLogger().removeHandler(run_file_handler)
                
    except Exception as e:
        logger.error(f"SimpleAutomation failed: {str(e)}", exc_info=True)
        return False

def _run_state_machine_automation(config_parser, config, settings):
    """Run state machine automation - matches GUI _run_state_machine_automation exactly"""
    try:
        # Import required modules
        from modules.network import NetworkManager
        from modules.screenshot import ScreenshotManager
        from modules.gemma_client import GemmaClient
        from modules.qwen_client import QwenClient
        from modules.omniparser_client import OmniparserClient
        from modules.annotator import Annotator
        from modules.decision_engine import DecisionEngine
        from modules.game_launcher import GameLauncher
        
        # Create timestamp for this run
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create game-specific directory structure
        os.makedirs("logs", exist_ok=True)
        game_dir = f"logs/{automation_state['game_name']}" if automation_state['game_name'] else "logs"
        os.makedirs(game_dir, exist_ok=True)

        # Create run-specific directory
        run_dir = f"{game_dir}/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)
        os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
        os.makedirs(f"{run_dir}/annotated", exist_ok=True)
        
        # Store the current run directory
        automation_state['current_run_dir'] = run_dir
        
        # Set up run-specific logging
        run_log_file = f"{run_dir}/automation.log"
        run_file_handler = logging.FileHandler(run_log_file)
        run_file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        run_file_handler.setFormatter(run_file_formatter)
        logging.getLogger().addHandler(run_file_handler)
        
        logger.info(f"Created run directory: {run_dir}")
        logger.info(f"Logs will be saved to: {run_log_file}")
        
        # Initialize components
        logger.info(f"Connecting to SUT at {settings['sut_ip']}:{settings['sut_port']}")
        network = NetworkManager(settings['sut_ip'], int(settings['sut_port']))
        
        logger.info("Initializing components...")
        screenshot_mgr = ScreenshotManager(network)
        
        # Initialize the vision model based on user selection
        if settings.get('vision_model') == 'gemma':
            logger.info("Using Gemma for UI detection")
            vision_model = GemmaClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'qwen':
            logger.info("Using Qwen VL for UI detection")
            vision_model = QwenClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'omniparser':
            logger.info("Using Omniparser for UI detection")
            vision_model = OmniparserClient(settings.get('omniparser_url', 'http://localhost:8000'))
        else:
            logger.info("Using default Gemma for UI detection")
            vision_model = GemmaClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
            
        annotator = Annotator()
        decision_engine = DecisionEngine(config)
        game_launcher = GameLauncher(network)
        
        # Get game metadata
        game_metadata = config_parser.get_game_metadata()
        logger.info(f"Game metadata loaded: {game_metadata}")
        startup_wait = game_metadata.get("startup_wait", 30)
        
        try:
            # Launch the game only if a path is provided
            if settings.get('game_path'):
                logger.info(f"Launching game from: {settings['game_path']}")
                game_launcher.launch(settings['game_path'])
                
                # Wait for game to initialize
                logger.info(f"Waiting {startup_wait} seconds for game to fully initialize...")
                wait_time = startup_wait
                for i in range(wait_time):
                    if automation_state['stop_event'].is_set():
                        break
                    time.sleep(1)
                    if i % 5 == 0:
                        socketio.emit('status_update', {
                            'status': f'Initializing ({wait_time-i}s)', 
                            'running': True
                        })
            else:
                logger.info("No game path provided, assuming game is already running")
            
            if automation_state['stop_event'].is_set():
                logger.info("Automation stopped during initialization")
                return False
                
            socketio.emit('status_update', {'status': 'Running', 'running': True})
            
            # Main execution loop - state machine approach
            iteration = 0
            current_state = "initial"
            target_state = decision_engine.get_target_state()
            
            # Track time spent in each state to detect timeouts
            state_start_time = time.time()
            max_time_in_state = 60  # Default maximum seconds to remain in the same state
            
            while (current_state != target_state and 
                   iteration < int(settings['max_iterations']) and 
                   not automation_state['stop_event'].is_set()):
                
                iteration += 1
                logger.info(f"Iteration {iteration}: Current state: {current_state}")
                
                # Get state-specific timeout
                state_def = config_parser.get_state_definition(current_state)
                state_timeout = state_def.get("timeout", max_time_in_state) if state_def else max_time_in_state
                
                # Check for timeout in current state
                time_in_state = time.time() - state_start_time
                if time_in_state > state_timeout:
                    logger.warning(f"Timeout in state {current_state} after {time_in_state:.1f} seconds (limit: {state_timeout}s)")
                    
                    # Get fallback action
                    fallback_action = decision_engine.get_fallback_action(current_state)
                    logger.info(f"Using fallback action for timeout: {fallback_action}")
                    
                    # Execute fallback action
                    network.send_action(fallback_action)
                    logger.info("Executed timeout recovery action")
                    time.sleep(2)
                    
                    # Reset timeout timer
                    state_start_time = time.time()
                    continue
                
                # Capture screenshot
                screenshot_path = f"{run_dir}/screenshots/screenshot_{iteration}.png"
                screenshot_mgr.capture(screenshot_path)
                logger.info(f"Screenshot captured: {screenshot_path}")
                
                # Process with vision model
                bounding_boxes = vision_model.detect_ui_elements(screenshot_path)
                logger.info(f"Detected {len(bounding_boxes)} UI elements")
                
                # Annotate screenshot
                annotated_path = f"{run_dir}/annotated/annotated_{iteration}.png"
                annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
                logger.info(f"Annotated screenshot saved: {annotated_path}")
                
                # Determine next action
                previous_state = current_state
                next_action, new_state = decision_engine.determine_next_action(
                    current_state, bounding_boxes
                )
                
                # Format the action for better logging
                action_str = ""
                if next_action:
                    if next_action.get("type") == "click":
                        action_str = f"Click at ({next_action.get('x')}, {next_action.get('y')})"
                    elif next_action.get("type") == "key":
                        action_str = f"Press key {next_action.get('key')}"
                    elif next_action.get("type") == "wait":
                        action_str = f"Wait for {next_action.get('duration')} seconds"
                    else:
                        action_str = str(next_action)
                        
                logger.info(f"Next action: {action_str}, transitioning to state: {new_state}")
                
                # Execute action
                if next_action and not automation_state['stop_event'].is_set():
                    logger.info(f"Executing action: {action_str}")
                    
                    # Handle "wait" actions locally instead of sending to SUT
                    if next_action.get("type") == "wait":
                        duration = next_action.get("duration", 1)
                        logger.info(f"Waiting for {duration} seconds...")
                        
                        # Wait in small increments so we can check for stop events
                        for i in range(duration):
                            if automation_state['stop_event'].is_set():
                                logger.info("Wait interrupted by stop event")
                                break
                            time.sleep(1)
                            if i % 10 == 0 and i > 0:  # Log every 10 seconds for long waits
                                logger.info(f"Still waiting... {i}/{duration} seconds elapsed")
                                
                        logger.info(f"Wait completed")
                    else:
                        # Send other action types to SUT
                        network.send_action(next_action)
                        
                    logger.info(f"Action completed: {action_str}")
                
                # Update state
                current_state = new_state
                if previous_state != current_state:
                    # Reset timeout timer when state changes
                    state_start_time = time.time()
                    logger.info(f"State changed from {previous_state} to {current_state}")
                
                # Get delay from transition if specified
                transition_key = f"{previous_state}->{current_state}"
                transition = config.get("transitions", {}).get(transition_key, {})
                delay = transition.get("expected_delay", 1)
                
                time.sleep(delay)  # Wait before next iteration
            
            # Check if we reached the target state
            if current_state == target_state:
                logger.info(f"Successfully reached target state: {target_state}")
                
                # Report benchmark results if available
                if hasattr(decision_engine, "state_context") and "benchmark_duration" in decision_engine.state_context:
                    benchmark_duration = decision_engine.state_context["benchmark_duration"]
                    logger.info(f"Benchmark completed in {benchmark_duration:.2f} seconds")
                    
                return True
            elif automation_state['stop_event'].is_set():
                logger.info("Automation process was manually stopped")
                return False
            else:
                logger.warning(f"Failed to reach target state. Stopped at: {current_state}")
                return False
                
        except Exception as e:
            logger.error(f"Error in state machine execution: {str(e)}", exc_info=True)
            return False
        
        finally:
            # Cleanup
            if 'network' in locals():
                network.close()
            if 'vision_model' in locals() and hasattr(vision_model, 'close'):
                vision_model.close()
            # Remove the run-specific log handler
            if 'run_file_handler' in locals():
                logging.getLogger().removeHandler(run_file_handler)
                
    except Exception as e:
        logger.error(f"State machine automation failed: {str(e)}", exc_info=True)
        return False

if __name__ == '__main__':
    # Ensure modules can be imported
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("Starting Katana Web Interface...")
    print("Open your browser and go to: http://localhost:5000")
    
    # Run the Flask app with SocketIO
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)