"""
SUT Service - Run this on the System Under Test (SUT)
This service handles requests from the ARL development PC.
"""

import os
import time
import json
import subprocess
import threading
from flask import Flask, request, jsonify, send_file
import pyautogui
from io import BytesIO
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sut_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variables
game_process = None
game_lock = threading.Lock()

@app.route('/status', methods=['GET'])
def status():
    """Endpoint to check if the service is running."""
    return jsonify({"status": "running"})

@app.route('/screenshot', methods=['GET'])
def screenshot():
    """Capture and return a screenshot."""
    try:
        # Capture the entire screen
        screenshot = pyautogui.screenshot()
        
        # Save to a bytes buffer
        img_buffer = BytesIO()
        screenshot.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        logger.info("Screenshot captured")
        return send_file(img_buffer, mimetype='image/png')
    except Exception as e:
        logger.error(f"Error capturing screenshot: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/launch', methods=['POST'])
def launch_game():
    """Launch a game."""
    global game_process
    
    try:
        data = request.json
        game_path = data.get('path', '')
        
        if not game_path or not os.path.exists(game_path):
            logger.error(f"Game path not found: {game_path}")
            return jsonify({"status": "error", "error": "Game executable not found"}), 404
        
        with game_lock:
            # Terminate existing game if running
            if game_process and game_process.poll() is None:
                logger.info("Terminating existing game process")
                game_process.terminate()
                game_process.wait(timeout=5)
            
            # Launch the game
            logger.info(f"Launching game: {game_path}")
            game_process = subprocess.Popen(game_path)
            
            # Wait a moment to check if process started successfully
            time.sleep(1)
            if game_process.poll() is not None:
                logger.error("Game process failed to start")
                return jsonify({"status": "error", "error": "Game process failed to start"}), 500
        
        return jsonify({"status": "success", "pid": game_process.pid})
    except Exception as e:
        logger.error(f"Error launching game: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/action', methods=['POST'])
def perform_action():
    """Perform an action (click, key press, etc.)."""
    try:
        data = request.json
        action_type = data.get('type', '')
        
        if action_type == 'click':
            x = data.get('x', 0)
            y = data.get('y', 0)
            logger.info(f"Performing click at ({x}, {y})")
            pyautogui.click(x=x, y=y)
            return jsonify({"status": "success"})
            
        elif action_type == 'key':
            key = data.get('key', '')
            logger.info(f"Pressing key: {key}")
            pyautogui.press(key)
            return jsonify({"status": "success"})
            
        elif action_type == 'wait':
            duration = data.get('duration', 1)
            logger.info(f"Waiting for {duration} seconds")
            time.sleep(duration)
            return jsonify({"status": "success"})
            
        elif action_type == 'terminate_game':
            with game_lock:
                if game_process and game_process.poll() is None:
                    logger.info("Terminating game")
                    game_process.terminate()
                    game_process.wait(timeout=5)
                    return jsonify({"status": "success"})
                else:
                    return jsonify({"status": "success", "message": "No running game to terminate"})
        else:
            logger.error(f"Unknown action type: {action_type}")
            return jsonify({"status": "error", "error": f"Unknown action type: {action_type}"}), 400
            
    except Exception as e:
        logger.error(f"Error performing action: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='SUT Service')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the service on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()
    
    logger.info(f"Starting SUT Service on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port)