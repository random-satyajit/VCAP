"""
Flask Web Application for Game UI Navigation Automation Tool
Replaces the heavy Tkinter GUI with a lightweight browser-based interface.
"""

import os
import sys
import time
import threading
import json
import logging
import queue
import yaml
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import datetime

# Add logging handler for web interface
class WebSocketHandler(logging.Handler):
    """Send logging records to web clients via WebSocket"""
    def __init__(self, socketio):
        super().__init__()
        self.socketio = socketio

    def emit(self, record):
        # Include more detailed information in the log entry
        log_entry = {
            'timestamp': time.strftime('%H:%M:%S', time.localtime(record.created)),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.name,
            'line': record.lineno if hasattr(record, 'lineno') else None
        }
        
        # If there's exception info, include it
        if record.exc_info:
            import traceback
            log_entry['exception'] = traceback.format_exception(*record.exc_info)
        
        self.socketio.emit('log_message', log_entry)

class HybridConfigParser:
    """Handles loading and parsing both state machine and step-based YAML configurations."""
    
    def __init__(self, config_path: str):
        """Initialize the hybrid config parser."""
        self.config_path = config_path
        self.config = self._load_config()
        self.config_type = self._detect_config_type()
        self._validate_config()
        
        # Extract game metadata
        self.game_name = self.config.get("metadata", {}).get("game_name", "Unknown Game")
    
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

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'katana_automation_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
automation_state = {
    'running': False,
    'status': 'Ready',
    'current_run_dir': None,
    'game_name': 'Unknown Game',
    'automation_thread': None,
    'stop_event': None
}

# Setup logging
def setup_logging():
    """Setup logging to both file and WebSocket"""
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
    
    # WebSocket handler
    websocket_handler = WebSocketHandler(socketio)
    logger.addHandler(websocket_handler)
    
    return logger

logger = setup_logging()

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/config/list')
def list_configs():
    """List available configuration files"""
    configs = []
    
    # Check config/games/ directory
    games_dir = "config/games"
    if os.path.exists(games_dir):
        for file in os.listdir(games_dir):
            if file.endswith('.yaml') or file.endswith('.yml'):
                configs.append(os.path.join(games_dir, file))
    
    # Check config/ directory
    config_dir = "config"
    if os.path.exists(config_dir):
        for file in os.listdir(config_dir):
            if file.endswith('.yaml') or file.endswith('.yml'):
                if 'games' not in file:  # Avoid duplicates
                    configs.append(os.path.join(config_dir, file))
    
    return jsonify(configs)

@app.route('/api/config/load', methods=['POST'])
def load_config():
    """Load and parse a configuration file"""
    try:
        config_path = request.json.get('path')
        if not config_path or not os.path.exists(config_path):
            return jsonify({'error': 'Config file not found'}), 404
        
        config_parser = HybridConfigParser(config_path)
        config = config_parser.get_config()
        metadata = config_parser.get_game_metadata()
        
        game_info = {
            'game_name': metadata.get("game_name", os.path.basename(config_path).replace('.yaml', '')),
            'benchmark_duration': metadata.get("benchmark_duration", "Unknown"),
            'resolution': metadata.get("resolution", "Any"),
            'preset': metadata.get("preset", "Any"),
            'config_type': config_parser.get_config_type(),
            'game_path': metadata.get("path", "")
        }
        
        automation_state['game_name'] = game_info['game_name']
        
        return jsonify(game_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/omniparser/test', methods=['POST'])
def test_omniparser():
    """Test connection to Omniparser server"""
    try:
        import requests
        url = request.json.get('url')
        response = requests.get(f"{url}/probe", timeout=5)
        if response.status_code == 200:
            return jsonify({'status': 'success', 'message': 'Connected successfully'})
        else:
            return jsonify({'status': 'error', 'message': f'HTTP {response.status_code}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """Start the automation process"""
    global automation_state
    
    if automation_state['running']:
        return jsonify({'error': 'Automation is already running'}), 400
    
    try:
        settings = request.json
        
        # Validate settings
        required_fields = ['sut_ip', 'sut_port', 'config_path', 'max_iterations']
        for field in required_fields:
            if not settings.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Start automation in a separate thread
        automation_state['stop_event'] = threading.Event()
        automation_state['running'] = True
        automation_state['status'] = 'Starting'
        
        automation_state['automation_thread'] = threading.Thread(
            target=run_automation_process,
            args=(settings,),
            daemon=True
        )
        automation_state['automation_thread'].start()
        
        socketio.emit('status_update', {'status': 'Starting', 'running': True})
        logger.info("Automation process starting...")
        
        return jsonify({'status': 'success', 'message': 'Automation started'})
        
    except Exception as e:
        automation_state['running'] = False
        automation_state['status'] = 'Error'
        logger.error(f"Failed to start automation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/automation/stop', methods=['POST'])
def stop_automation():
    """Stop the automation process"""
    global automation_state
    
    if not automation_state['running']:
        return jsonify({'error': 'Automation is not running'}), 400
    
    try:
        if automation_state['stop_event']:
            automation_state['stop_event'].set()
        
        automation_state['running'] = False
        automation_state['status'] = 'Stopped'
        
        socketio.emit('status_update', {'status': 'Stopped', 'running': False})
        logger.info("Automation process stopped by user")
        
        return jsonify({'status': 'success', 'message': 'Automation stopped'})
        
    except Exception as e:
        logger.error(f"Failed to stop automation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """Clear the log display (client-side action)"""
    socketio.emit('clear_logs')
    return jsonify({'status': 'success'})

@app.route('/api/status')
def get_status():
    """Get current automation status"""
    return jsonify({
        'running': automation_state['running'],
        'status': automation_state['status'],
        'game_name': automation_state['game_name']
    })

def run_automation_process(settings):
    """Run the automation process based on settings"""
    global automation_state
    
    try:
        # Load configuration
        config_parser = HybridConfigParser(settings['config_path'])
        config = config_parser.get_config()
        
        if config_parser.is_step_based():
            logger.info("Using SimpleAutomation for step-based configuration")
            success = run_simple_automation(config_parser, config, settings)
        else:
            logger.info("Using state machine automation")
            success = run_state_machine_automation(config_parser, config, settings)
        
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

def run_simple_automation(config_parser, config, settings):
    """Run SimpleAutomation process"""
    try:
        from modules.simple_automation import SimpleAutomation
        from modules.network import NetworkManager
        from modules.screenshot import ScreenshotManager
        from modules.gemma_client import GemmaClient
        from modules.qwen_client import QwenClient
        from modules.omniparser_client import OmniparserClient
        from modules.annotator import Annotator
        from modules.game_launcher import GameLauncher
        
        # Create run directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        game_dir = f"logs/{automation_state['game_name']}"
        os.makedirs(game_dir, exist_ok=True)
        run_dir = f"{game_dir}/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)
        os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
        os.makedirs(f"{run_dir}/annotated", exist_ok=True)
        
        automation_state['current_run_dir'] = run_dir
        
        # Initialize components
        network = NetworkManager(settings['sut_ip'], int(settings['sut_port']))
        screenshot_mgr = ScreenshotManager(network)
        
        # Initialize vision model
        if settings['vision_model'] == 'gemma':
            vision_model = GemmaClient(settings['lm_studio_url'])
        elif settings['vision_model'] == 'qwen':
            vision_model = QwenClient(settings['lm_studio_url'])
        elif settings['vision_model'] == 'omniparser':
            vision_model = OmniparserClient(settings['omniparser_url'])
        
        annotator = Annotator()
        game_launcher = GameLauncher(network)
        
        # Launch game if path provided
        if settings.get('game_path'):
            logger.info(f"Launching game from: {settings['game_path']}")
            game_launcher.launch(settings['game_path'])
            
            # Wait for startup
            startup_wait = config_parser.get_game_metadata().get("startup_wait", 30)
            logger.info(f"Waiting {startup_wait} seconds for game to initialize...")
            for i in range(startup_wait):
                if automation_state['stop_event'] and automation_state['stop_event'].is_set():
                    return False
                time.sleep(1)
                socketio.emit('status_update', {
                    'status': f'Initializing ({startup_wait-i}s)', 
                    'running': True
                })
        
        automation_state['status'] = 'Running'
        socketio.emit('status_update', {'status': 'Running', 'running': True})
        
        # Run simple automation
        simple_auto = SimpleAutomation(
            config_path=settings['config_path'],
            network=network,
            screenshot_mgr=screenshot_mgr,
            vision_model=vision_model,
            stop_event=automation_state['stop_event'],
            run_dir=run_dir,
            annotator=annotator
        )
        
        success = simple_auto.run()
        
        # Cleanup
        network.close()
        if hasattr(vision_model, 'close'):
            vision_model.close()
            
        return success
        
    except Exception as e:
        logger.error(f"SimpleAutomation failed: {str(e)}", exc_info=True)
        return False

def run_state_machine_automation(config_parser, config, settings):
    """Run state machine automation process"""
    try:
        from modules.decision_engine import DecisionEngine
        from modules.network import NetworkManager
        from modules.screenshot import ScreenshotManager
        from modules.gemma_client import GemmaClient
        from modules.qwen_client import QwenClient
        from modules.omniparser_client import OmniparserClient
        from modules.annotator import Annotator
        from modules.game_launcher import GameLauncher
        
        # Create run directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        game_dir = f"logs/{automation_state['game_name']}"
        os.makedirs(game_dir, exist_ok=True)
        run_dir = f"{game_dir}/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)
        os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
        os.makedirs(f"{run_dir}/annotated", exist_ok=True)
        
        automation_state['current_run_dir'] = run_dir
        
        # Initialize components
        network = NetworkManager(settings['sut_ip'], int(settings['sut_port']))
        screenshot_mgr = ScreenshotManager(network)
        
        # Initialize vision model
        if settings['vision_model'] == 'gemma':
            vision_model = GemmaClient(settings['lm_studio_url'])
        elif settings['vision_model'] == 'qwen':
            vision_model = QwenClient(settings['lm_studio_url'])
        elif settings['vision_model'] == 'omniparser':
            vision_model = OmniparserClient(settings['omniparser_url'])
        
        annotator = Annotator()
        decision_engine = DecisionEngine(config)
        game_launcher = GameLauncher(network)
        
        # Launch game if path provided
        if settings.get('game_path'):
            logger.info(f"Launching game from: {settings['game_path']}")
            game_launcher.launch(settings['game_path'])
            
            # Wait for startup
            startup_wait = config_parser.get_game_metadata().get("startup_wait", 30)
            logger.info(f"Waiting {startup_wait} seconds for game to initialize...")
            for i in range(startup_wait):
                if automation_state['stop_event'] and automation_state['stop_event'].is_set():
                    return False
                time.sleep(1)
                socketio.emit('status_update', {
                    'status': f'Initializing ({startup_wait-i}s)', 
                    'running': True
                })
        
        automation_state['status'] = 'Running'
        socketio.emit('status_update', {'status': 'Running', 'running': True})
        
        # Main automation loop
        iteration = 0
        current_state = "initial"
        target_state = decision_engine.get_target_state()
        max_iterations = int(settings['max_iterations'])
        
        while (current_state != target_state and 
               iteration < max_iterations and 
               not (automation_state['stop_event'] and automation_state['stop_event'].is_set())):
            
            iteration += 1
            logger.info(f"Iteration {iteration}: Current state: {current_state}")
            
            # Capture screenshot
            screenshot_path = f"{run_dir}/screenshots/screenshot_{iteration}.png"
            screenshot_mgr.capture(screenshot_path)
            
            # Process with vision model
            bounding_boxes = vision_model.detect_ui_elements(screenshot_path)
            logger.info(f"Detected {len(bounding_boxes)} UI elements")
            
            # Annotate screenshot
            annotated_path = f"{run_dir}/annotated/annotated_{iteration}.png"
            annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
            
            # Determine next action
            previous_state = current_state
            next_action, new_state = decision_engine.determine_next_action(current_state, bounding_boxes)
            
            # Execute action
            if next_action and not (automation_state['stop_event'] and automation_state['stop_event'].is_set()):
                if next_action.get("type") == "wait":
                    duration = next_action.get("duration", 1)
                    logger.info(f"Waiting for {duration} seconds...")
                    for i in range(duration):
                        if automation_state['stop_event'] and automation_state['stop_event'].is_set():
                            break
                        time.sleep(1)
                else:
                    network.send_action(next_action)
            
            current_state = new_state
            time.sleep(1)  # Brief pause between iterations
        
        # Cleanup
        network.close()
        if hasattr(vision_model, 'close'):
            vision_model.close()
        
        return current_state == target_state
        
    except Exception as e:
        logger.error(f"State machine automation failed: {str(e)}", exc_info=True)
        return False

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Web client connected")
    emit('status_update', {
        'status': automation_state['status'],
        'running': automation_state['running']
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Web client disconnected")

if __name__ == '__main__':
    # Ensure modules can be imported
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("Starting Katana Web Interface...")
    print("Open your browser and go to: http://localhost:5000")
    
    # Run the Flask app with SocketIO
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)