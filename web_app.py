"""
Enhanced Flask Web Server with Complete Log Monitoring
This version captures ALL logs from all modules and displays them in the web interface
"""

import os
import sys
import time
import json
import yaml
import glob
import queue
import threading
import logging
import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import requests

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global state for automation
automation_state = {
    'running': False,
    'status': 'Ready',
    'automation_thread': None,
    'stop_event': None,
    'game_name': 'Unknown Game',
    'log_monitors': []  # Multiple log monitors for different log files
}

# Enhanced Log File Monitor that captures everything
class ComprehensiveLogMonitor:
    """Monitors multiple log files and sends ALL content to web clients"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self.monitoring = False
        self.monitor_threads = []
        self.log_files = {}  # Dictionary to track multiple log files
        self.file_positions = {}  # Track read positions for each file
        
    def add_log_file(self, log_file_path, identifier=None):
        """Add a log file to monitor"""
        if not identifier:
            identifier = os.path.basename(log_file_path)
        
        self.log_files[identifier] = log_file_path
        self.file_positions[identifier] = 0
        
        # If already monitoring, start monitoring this new file too
        if self.monitoring:
            thread = threading.Thread(
                target=self._monitor_single_file,
                args=(identifier, log_file_path),
                daemon=True,
                name=f"LogMonitor-{identifier}"
            )
            thread.start()
            self.monitor_threads.append(thread)
            
        print(f"Added log file to monitor: {log_file_path}")
        
    def start_monitoring(self):
        """Start monitoring all configured log files"""
        if self.monitoring:
            return
            
        self.monitoring = True
        
        # Start a thread for each log file
        for identifier, log_file_path in self.log_files.items():
            thread = threading.Thread(
                target=self._monitor_single_file,
                args=(identifier, log_file_path),
                daemon=True,
                name=f"LogMonitor-{identifier}"
            )
            thread.start()
            self.monitor_threads.append(thread)
            
        print(f"Started monitoring {len(self.log_files)} log files")
        
    def stop_monitoring(self):
        """Stop monitoring all log files"""
        self.monitoring = False
        
        # Wait for all threads to finish
        for thread in self.monitor_threads:
            thread.join(timeout=1)
            
        self.monitor_threads.clear()
        print("Stopped all log file monitoring")
        
    def _monitor_single_file(self, identifier, log_file_path):
        """Monitor a single log file for new content"""
        print(f"Starting to monitor: {log_file_path}")
        
        # Wait for file to exist
        wait_count = 0
        while not os.path.exists(log_file_path) and self.monitoring and wait_count < 30:
            time.sleep(0.5)
            wait_count += 1
            
        if not os.path.exists(log_file_path):
            print(f"Log file not found after waiting: {log_file_path}")
            return
            
        while self.monitoring:
            try:
                # Check if file has new content
                current_size = os.path.getsize(log_file_path)
                last_position = self.file_positions.get(identifier, 0)
                
                if current_size > last_position:
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                        # Seek to last read position
                        file.seek(last_position)
                        
                        # Read all new lines
                        new_content = file.read()
                        self.file_positions[identifier] = file.tell()
                        
                        # Process and send each line
                        for line in new_content.splitlines():
                            if line.strip():
                                self._send_log_line(line)
                                
                time.sleep(0.1)  # Check every 100ms for responsive updates
                
            except Exception as e:
                print(f"Error monitoring {log_file_path}: {e}")
                time.sleep(1)
                
    def _send_log_line(self, line):
        """Parse and send a single log line to web clients"""
        try:
            # Try to parse standard Python logging format
            # Format: "2025-07-12 05:48:54,498 - module.name - LEVEL - Message"
            parts = line.split(' - ', 3)
            
            if len(parts) >= 4:
                timestamp_str = parts[0]
                module = parts[1]
                level = parts[2]
                message = parts[3]
                
                # Extract just time from timestamp
                try:
                    # Parse "2025-07-12 05:48:54,498" format
                    dt = datetime.datetime.strptime(timestamp_str.split(',')[0], '%Y-%m-%d %H:%M:%S')
                    time_only = dt.strftime('%H:%M:%S')
                except:
                    time_only = timestamp_str
                
                log_entry = {
                    'timestamp': time_only,
                    'level': level,
                    'message': message,
                    'module': module,
                    'raw': line  # Include raw line for debugging
                }
            else:
                # If we can't parse it, send as-is
                log_entry = {
                    'timestamp': time.strftime('%H:%M:%S'),
                    'level': 'INFO',
                    'message': line,
                    'module': 'system',
                    'raw': line
                }
            
            # Send to all connected clients
            self.socketio.emit('log_message', log_entry)
            
        except Exception as e:
            print(f"Error parsing log line: {e}")
            # Send raw line if parsing fails
            self.socketio.emit('log_message', {
                'timestamp': time.strftime('%H:%M:%S'),
                'level': 'INFO',
                'message': line,
                'module': 'system'
            })

# Create global log monitor
log_monitor = ComprehensiveLogMonitor(socketio)

# Configure comprehensive logging to capture ALL module outputs
def setup_comprehensive_logging(log_file_path):
    """Setup logging to capture ALL outputs from all modules"""
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set root logger to capture everything
    root_logger.setLevel(logging.DEBUG)
    
    # Create file handler that captures everything
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Add handler to root logger
    root_logger.addHandler(file_handler)
    
    # Also add console handler for debugging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(file_formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Ensure all module loggers propagate to root
    for logger_name in ['modules.network', 'modules.screenshot', 'modules.omniparser_client', 
                       'modules.annotator', 'modules.game_launcher', 'modules.simple_automation',
                       'modules.decision_engine', 'modules.gemma_client', 'modules.qwen_client',
                       'automation', 'werkzeug', 'root']:
        module_logger = logging.getLogger(logger_name)
        module_logger.propagate = True
        module_logger.setLevel(logging.DEBUG)
    
    print(f"Comprehensive logging configured to: {log_file_path}")
    return log_file_path

# Flask routes
@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')

@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """Start automation with comprehensive log monitoring"""
    global automation_state, log_monitor
    
    if automation_state['running']:
        return jsonify({'error': 'Automation is already running'}), 400
    
    try:
        settings = request.json
        
        # Validate settings
        required_fields = ['sut_ip', 'sut_port', 'config_path', 'max_iterations']
        for field in required_fields:
            if not settings.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Load configuration to get game name
        config_path = settings['config_path']
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        game_name = config.get('metadata', {}).get('game_name', 'Unknown Game')
        automation_state['game_name'] = game_name
        
        # Create run directory with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = f"logs/{game_name}/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)
        os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
        os.makedirs(f"{run_dir}/annotated", exist_ok=True)
        
        # Setup comprehensive logging
        main_log_file = f"{run_dir}/automation.log"
        setup_comprehensive_logging(main_log_file)
        
        # Also monitor the web server log
        web_log_file = f"logs/web_server_{datetime.datetime.now().strftime('%Y_%m_%d__%H_%M_%S')}.log"
        setup_comprehensive_logging(web_log_file)
        
        # Start monitoring both log files
        log_monitor.add_log_file(main_log_file, "automation")
        log_monitor.add_log_file(web_log_file, "web_server")
        log_monitor.start_monitoring()
        
        # Log startup
        logger = logging.getLogger('root')
        logger.info(f"Automation started with file-based logging: {main_log_file}")
        
        # Update state
        automation_state['stop_event'] = threading.Event()
        automation_state['running'] = True
        automation_state['status'] = 'Starting'
        automation_state['run_dir'] = run_dir
        
        # Start automation thread
        automation_state['automation_thread'] = threading.Thread(
            target=run_automation_process,
            args=(settings, run_dir),
            daemon=True,
            name="AutomationWorker"
        )
        automation_state['automation_thread'].start()
        
        # Send immediate status update
        socketio.emit('status_update', {'status': 'Starting', 'running': True})
        
        return jsonify({
            'status': 'success',
            'message': 'Automation started with comprehensive logging',
            'log_file': main_log_file,
            'run_dir': run_dir
        })
        
    except Exception as e:
        automation_state['running'] = False
        automation_state['status'] = 'Error'
        logging.error(f"Failed to start automation: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/automation/stop', methods=['POST'])
def stop_automation():
    """Stop automation and log monitoring"""
    global automation_state, log_monitor
    
    if not automation_state['running']:
        return jsonify({'error': 'Automation is not running'}), 400
    
    try:
        logger = logging.getLogger('root')
        logger.info("Automation and log monitoring stopped by user")
        
        # Signal stop
        if automation_state['stop_event']:
            automation_state['stop_event'].set()
        
        # Stop log monitoring
        log_monitor.stop_monitoring()
        
        # Update state
        automation_state['running'] = False
        automation_state['status'] = 'Stopped'
        
        # Send status update
        socketio.emit('status_update', {'status': 'Stopped', 'running': False})
        
        return jsonify({'status': 'success', 'message': 'Automation stopped'})
        
    except Exception as e:
        logging.error(f"Failed to stop automation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/automation/status', methods=['GET'])
def get_automation_status():
    """Get current automation status"""
    return jsonify({
        'running': automation_state['running'],
        'status': automation_state['status'],
        'game_name': automation_state['game_name']
    })

@app.route('/api/config/list', methods=['GET'])
def list_configs():
    """List available configuration files"""
    configs = []
    
    # Check config/games directory
    if os.path.exists('config/games'):
        for file in glob.glob('config/games/*.yaml'):
            configs.append({
                'path': file.replace('\\', '/'),
                'name': os.path.basename(file)
            })
    
    # Check config directory
    for file in glob.glob('config/*.yaml'):
        if 'template' not in file:
            configs.append({
                'path': file.replace('\\', '/'),
                'name': os.path.basename(file)
            })
    
    return jsonify(configs)

@app.route('/api/config/load', methods=['POST'])
def load_config():
    """Load and parse a configuration file"""
    try:
        config_path = request.json.get('path')
        if not config_path or not os.path.exists(config_path):
            return jsonify({'error': 'Config file not found'}), 404
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        metadata = config.get('metadata', {})
        
        # Determine config type
        if 'steps' in config:
            config_type = 'steps'
        elif 'states' in config and 'transitions' in config:
            config_type = 'state_machine'
        else:
            config_type = 'unknown'
        
        return jsonify({
            'game_name': metadata.get('game_name', 'Unknown Game'),
            'game_path': metadata.get('path', ''),
            'resolution': metadata.get('resolution', 'Any'),
            'preset': metadata.get('preset', 'Any'),
            'benchmark_duration': metadata.get('benchmark_duration', 'Unknown'),
            'config_type': config_type
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/omniparser/test', methods=['POST'])
def test_omniparser():
    """Test Omniparser connection"""
    try:
        url = request.json.get('url', 'http://localhost:8000')
        response = requests.get(f"{url}/probe", timeout=5)
        
        if response.status_code == 200:
            return jsonify({'status': 'success', 'message': 'Connected to Omniparser'})
        else:
            return jsonify({'status': 'error', 'message': f'HTTP {response.status_code}'}), 400
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger = logging.getLogger('root')
    logger.info('Web client connected')
    emit('connected', {'status': 'Connected to automation server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger = logging.getLogger('root')
    logger.info('Web client disconnected')

# Automation execution function
def run_automation_process(settings, run_dir):
    """Run the automation process with comprehensive logging"""
    logger = logging.getLogger('automation')
    
    try:
        logger.info("=== Automation Started ===")
        logger.info(f"Run directory: {run_dir}")
        logger.info(f"Log file: {run_dir}/automation.log")
        logger.info(f"Settings: {json.dumps(settings, indent=2)}")
        
        # Load configuration
        config_path = settings['config_path']
        logger.info(f"Loading configuration from: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Determine automation type
        if 'steps' in config:
            logger.info("Using SimpleAutomation for step-based configuration")
            run_simple_automation(settings, config, run_dir)
        else:
            logger.info("Using DecisionEngine for state machine configuration")
            run_state_machine_automation(settings, config, run_dir)
            
    except Exception as e:
        logger.error(f"Automation failed: {str(e)}", exc_info=True)
        automation_state['status'] = 'Error'
    finally:
        automation_state['running'] = False
        automation_state['status'] = 'Completed' if not automation_state['stop_event'].is_set() else 'Stopped'
        logger.info("=== Automation Thread Finished ===")
        socketio.emit('status_update', {
            'status': automation_state['status'], 
            'running': False
        })

def run_simple_automation(settings, config, run_dir):
    """Run simple step-based automation"""
    logger = logging.getLogger('automation')
    
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
        
        # Initialize components
        logger.info("Initializing automation components...")
        
        network = NetworkManager(settings['sut_ip'], int(settings['sut_port']))
        logger.info(f"Connected to SUT at {settings['sut_ip']}:{settings['sut_port']}")
        
        screenshot_mgr = ScreenshotManager(network)
        logger.info("Screenshot manager initialized")
        
        # Initialize vision model
        vision_model = None
        if settings.get('vision_model') == 'gemma':
            logger.info("Initializing Gemma vision model")
            vision_model = GemmaClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'qwen':
            logger.info("Initializing Qwen VL vision model")
            vision_model = QwenClient(settings.get('lm_studio_url', 'http://127.0.0.1:1234'))
        elif settings.get('vision_model') == 'omniparser':
            logger.info("Initializing Omniparser vision model")
            vision_model = OmniparserClient(settings.get('omniparser_url', 'http://localhost:8000'))
        
        annotator = Annotator()
        logger.info("Annotator initialized")
        
        game_launcher = GameLauncher(network)
        logger.info("Game launcher initialized")
        
        # Launch game if path provided
        if settings.get('game_path'):
            logger.info(f"Launching game from: {settings['game_path']}")
            game_launcher.launch(settings['game_path'])
            logger.info("Game launch command sent to SUT")
            
            # Wait for game to initialize
            startup_wait = config.get('metadata', {}).get('startup_wait', 30)
            logger.info(f"Waiting {startup_wait} seconds for game to initialize...")
            
            for i in range(startup_wait):
                if automation_state['stop_event'].is_set():
                    logger.info("Game initialization interrupted by stop request")
                    break
                    
                remaining = startup_wait - i
                if i == 0:
                    logger.info(f"Game initializing... {remaining} seconds remaining")
                elif i % 5 == 0:
                    logger.info(f"Game initializing... {remaining} seconds remaining")
                    
                time.sleep(1)
                
            logger.info("Game initialization completed")
        
        # Create and run SimpleAutomation
        logger.info("Starting automation execution...")
        simple_auto = SimpleAutomation(
            config_path=settings['config_path'],
            network=network,
            screenshot_mgr=screenshot_mgr,
            vision_model=vision_model,
            stop_event=automation_state['stop_event'],
            run_dir=run_dir,
            annotator=annotator
        )
        
        logger.info("SimpleAutomation instance created, beginning execution")
        success = simple_auto.run()
        
        if success:
            logger.info("SimpleAutomation completed successfully")
        else:
            logger.warning("SimpleAutomation completed with errors")
            
    except Exception as e:
        logger.error(f"Error in simple automation: {str(e)}", exc_info=True)
        raise
    finally:
        # Cleanup
        logger.info("Cleaning up network connections...")
        if 'network' in locals():
            network.close()
        if 'vision_model' in locals() and hasattr(vision_model, 'close'):
            vision_model.close()
        logger.info("Cleanup completed")
        
        if automation_state['stop_event'].is_set():
            logger.info("=== Automation Stopped by User ===")
        else:
            logger.info("=== Automation Completed ===")

def run_state_machine_automation(settings, config, run_dir):
    """Run state machine based automation"""
    # Similar implementation to simple automation but using DecisionEngine
    logger = logging.getLogger('automation')
    logger.info("State machine automation not fully implemented in this example")
    # ... implementation similar to run_simple_automation but with DecisionEngine

# Start the Flask app
def start_web_server(host='0.0.0.0', port=5000):
    """Start the Flask web server"""
    print(f"\n{'='*60}")
    print(f"Starting Enhanced Web Automation Server")
    print(f"{'='*60}")
    print(f"Server URL: http://localhost:{port}")
    print(f"{'='*60}\n")
    
    # Create initial web server log
    web_log = f"logs/web_server_{datetime.datetime.now().strftime('%Y_%m_%d__%H_%M_%S')}.log"
    os.makedirs("logs", exist_ok=True)
    setup_comprehensive_logging(web_log)
    
    socketio.run(app, host=host, port=port, debug=False)

if __name__ == '__main__':
    start_web_server()