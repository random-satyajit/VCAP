"""
Simple step-by-step automation module for game UI navigation.
Uses a direct procedural approach instead of complex state machines.
"""

import os
import time
import logging
import yaml
from typing import List, Dict, Any, Optional

from modules.gemma_client import BoundingBox

logger = logging.getLogger(__name__)

class SimpleAutomation:
    """Simplified step-by-step automation for game UI workflows."""
    
    def __init__(self, config_path, network, screenshot_mgr, vision_model, stop_event=None, run_dir=None, annotator=None):
        """Initialize with all necessary components."""
        self.config_path = config_path
        self.network = network
        self.screenshot_mgr = screenshot_mgr
        self.vision_model = vision_model
        self.stop_event = stop_event
        self.annotator = annotator
        
        # Load configuration using SimpleConfigParser if available
        try:
            from modules.simple_config_parser import SimpleConfigParser
            config_parser = SimpleConfigParser(config_path)
            self.config = config_parser.get_config()
            logger.info("Using SimpleConfigParser for step-based configuration")
        except (ImportError, ValueError):
            # Fall back to direct YAML loading
            logger.info("SimpleConfigParser not available, loading YAML directly")
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        
        # Game metadata
        self.game_name = self.config.get("metadata", {}).get("game_name", "Unknown Game")
        self.run_dir = run_dir or f"logs/{self.game_name}"
        
        logger.info(f"SimpleAutomation initialized for {self.game_name}")
            
    def run(self):
        """Run the simplified step-by-step automation."""
        # Get steps from configuration
        steps = self.config.get("steps", {})
        
        # If no steps defined, try to convert from state machine format
        if not steps:
            logger.info("No steps defined in config, attempting to convert from state machine format")
            steps = self._convert_states_to_steps()
            
        if not steps:
            logger.error("No steps defined and couldn't convert from state machine format")
            return False
        
        # Convert all step keys to strings to handle both integer and string keys
        normalized_steps = {}
        for key, value in steps.items():
            normalized_steps[str(key)] = value
        steps = normalized_steps
        
        # Debug: Log the available steps
        logger.info(f"Available steps: {list(steps.keys())}")
        
        current_step = 1
        max_retries = 3
        retries = 0
        
        logger.info(f"Starting automation with {len(steps)} steps")
        
        while current_step <= len(steps):
            step_key = str(current_step)
            
            if step_key not in steps:
                logger.error(f"Step {step_key} not found in configuration. Available steps: {list(steps.keys())}")
                return False
                
            step = steps[step_key]
            logger.info(f"Executing step {current_step}: {step.get('description', 'No description')}")
            
            # Check for stop event
            if self.stop_event and self.stop_event.is_set():
                logger.info("Stop event detected, ending automation")
                break
            
            # Capture screenshot
            screenshot_path = f"{self.run_dir}/screenshots/screenshot_{current_step}.png"
            try:
                self.screenshot_mgr.capture(screenshot_path)
            except Exception as e:
                logger.error(f"Failed to capture screenshot: {str(e)}")
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Max retries reached for screenshot capture, failing")
                    return False
                continue
            
            # Detect UI elements
            try:
                bounding_boxes = self.vision_model.detect_ui_elements(screenshot_path)
            except Exception as e:
                logger.error(f"Failed to detect UI elements: {str(e)}")
                retries += 1
                if retries >= max_retries:
                    logger.error(f"Max retries reached for UI detection, failing")
                    return False
                continue
            
            # Annotate screenshot if annotator available
            if self.annotator:
                try:
                    annotated_path = f"{self.run_dir}/annotated/annotated_{current_step}.png"
                    self.annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
                    logger.info(f"Annotated screenshot saved: {annotated_path}")
                except Exception as e:
                    logger.warning(f"Failed to create annotated screenshot: {str(e)}")
            
            # Process step based on type
            if "find_and_click" in step:
                # Find and click element
                target = step["find_and_click"]
                element = self._find_matching_element(target, bounding_boxes)
                
                if element:
                    # Calculate center point for click
                    center_x = element.x + (element.width // 2)
                    center_y = element.y + (element.height // 2)
                    
                    # Execute click
                    action = {"type": "click", "x": center_x, "y": center_y}
                    try:
                        response = self.network.send_action(action)
                        logger.info(f"Clicked on '{element.element_text}' at ({center_x}, {center_y})")
                        logger.debug(f"Network response: {response}")
                    except Exception as e:
                        logger.error(f"Failed to send click action: {str(e)}")
                        retries += 1
                        if retries >= max_retries:
                            logger.error(f"Max retries reached for click action, failing")
                            return False
                        continue
                    
                    # Wait for expected delay
                    expected_delay = step.get("expected_delay", 2)
                    logger.info(f"Waiting {expected_delay} seconds after click...")
                    time.sleep(expected_delay)
                    
                    # Verify success if specified
                    if step.get("verify_success"):
                        logger.info("Verifying step success...")
                        # Capture new screenshot for verification
                        verify_path = f"{self.run_dir}/screenshots/verify_{current_step}.png"
                        try:
                            self.screenshot_mgr.capture(verify_path)
                            verify_boxes = self.vision_model.detect_ui_elements(verify_path)
                            
                            # Annotate verification screenshot if annotator available
                            if self.annotator:
                                try:
                                    annotated_verify_path = f"{self.run_dir}/annotated/verify_{current_step}.png"
                                    self.annotator.draw_bounding_boxes(verify_path, verify_boxes, annotated_verify_path)
                                except Exception as e:
                                    logger.warning(f"Failed to create verification annotation: {str(e)}")
                            
                            # Check for verification elements
                            success = True
                            for verify_element in step["verify_success"]:
                                if not self._find_matching_element(verify_element, verify_boxes):
                                    success = False
                                    logger.warning(f"Verification failed: {verify_element.get('text', 'Unknown element')} not found")
                            
                            if success:
                                logger.info(f"Step {current_step} completed successfully")
                                current_step += 1
                                retries = 0  # Reset retry counter on success
                            else:
                                retries += 1
                                logger.warning(f"Step {current_step} verification failed, retry {retries}/{max_retries}")
                                if retries >= max_retries:
                                    logger.error(f"Max retries reached for step {current_step}, failing")
                                    return False
                                # Execute fallback if verification fails
                                self._execute_fallback()
                        except Exception as e:
                            logger.error(f"Failed during verification: {str(e)}")
                            retries += 1
                            if retries >= max_retries:
                                logger.error(f"Max retries reached during verification, failing")
                                return False
                            continue
                    else:
                        # No verification needed, move to next step
                        logger.info(f"Step {current_step} completed (no verification required)")
                        current_step += 1
                        retries = 0  # Reset retry counter on success
                else:
                    retries += 1
                    target_text = target.get('text', 'Unknown')
                    target_type = target.get('type', 'any')
                    logger.warning(f"Target element '{target_text}' (type: {target_type}) not found, retry {retries}/{max_retries}")
                    
                    # Log available elements for debugging
                    if bounding_boxes:
                        logger.info("Available UI elements:")
                        for i, bbox in enumerate(bounding_boxes):
                            logger.info(f"  {i+1}. Type: {bbox.element_type}, Text: '{bbox.element_text}'")
                    else:
                        logger.info("No UI elements detected")
                    
                    if retries >= max_retries:
                        logger.error(f"Max retries reached for step {current_step}, failing")
                        return False
                    # Execute fallback if target not found
                    self._execute_fallback()
                    
            elif "action" in step and step["action"] == "wait":
                # Wait action
                duration = step.get("duration", 10)
                logger.info(f"Waiting for {duration} seconds")
                
                # Wait in smaller increments to allow for interruption
                for i in range(duration):
                    if self.stop_event and self.stop_event.is_set():
                        logger.info("Wait interrupted by stop event")
                        break
                    time.sleep(1)
                    if i % 10 == 0 and i > 0:  # Log progress for long waits
                        logger.info(f"Still waiting... {i}/{duration} seconds elapsed")
                
                # Move to next step after wait
                logger.info(f"Wait completed for step {current_step}")
                current_step += 1
                retries = 0  # Reset retry counter
            else:
                logger.error(f"Unknown step type in step {current_step}: {step}")
                return False
                
        if current_step > len(steps):
            logger.info("All steps completed successfully!")
            return True
        else:
            logger.info("Automation stopped before completion")
            return False
    
    def _find_matching_element(self, target_def, bounding_boxes):
        """Find a UI element matching the target definition."""
        target_type = target_def.get("type", "any")
        target_text = target_def.get("text", "")
        match_type = target_def.get("text_match", "contains")
        
        logger.debug(f"Looking for element: type='{target_type}', text='{target_text}', match='{match_type}'")
        
        for bbox in bounding_boxes:
            # Check element type
            type_match = (target_type == "any" or bbox.element_type == target_type)
            
            # Check text content with specified matching strategy
            text_match = False
            if bbox.element_text and target_text:
                bbox_text_lower = bbox.element_text.lower()
                target_text_lower = target_text.lower()
                
                if match_type == "exact":
                    text_match = target_text_lower == bbox_text_lower
                elif match_type == "contains":
                    text_match = target_text_lower in bbox_text_lower
                elif match_type == "startswith":
                    text_match = bbox_text_lower.startswith(target_text_lower)
                elif match_type == "endswith":
                    text_match = bbox_text_lower.endswith(target_text_lower)
                else:
                    logger.warning(f"Unknown text_match type: {match_type}, using 'contains'")
                    text_match = target_text_lower in bbox_text_lower
            elif not target_text:  # If no text requirement, match any element of the right type
                text_match = True
            
            if type_match and text_match:
                logger.debug(f"Found matching element: type='{bbox.element_type}', text='{bbox.element_text}'")
                return bbox
                
        logger.debug("No matching element found")
        return None
        
    def _execute_fallback(self):
        """Execute fallback action if step fails."""
        fallback = self.config.get("fallbacks", {}).get("general", {})
        if fallback:
            action_type = fallback.get("action")
            if action_type == "key":
                key = fallback.get("key", "Escape")
                logger.info(f"Executing fallback: Press key {key}")
                try:
                    self.network.send_action({"type": "key", "key": key})
                except Exception as e:
                    logger.error(f"Failed to execute fallback key action: {str(e)}")
            elif action_type == "click":
                x = fallback.get("x", 0)
                y = fallback.get("y", 0)
                logger.info(f"Executing fallback: Click at ({x}, {y})")
                try:
                    self.network.send_action({"type": "click", "x": x, "y": y})
                except Exception as e:
                    logger.error(f"Failed to execute fallback click action: {str(e)}")
        else:
            logger.info("No fallback action defined, pressing Escape key as default")
            try:
                self.network.send_action({"type": "key", "key": "Escape"})
            except Exception as e:
                logger.error(f"Failed to execute default fallback action: {str(e)}")
                
        # Wait after fallback
        fallback_delay = fallback.get("expected_delay", 1) if fallback else 1
        logger.info(f"Waiting {fallback_delay} seconds after fallback action")
        time.sleep(fallback_delay)
        
    def _convert_states_to_steps(self):
        """
        Attempt to convert state machine format to step format.
        This allows using existing YAML files with the simple automation.
        """
        steps = {}
        states = self.config.get("states", {})
        transitions = self.config.get("transitions", {})
        initial_state = self.config.get("initial_state")
        
        if not states or not transitions or not initial_state:
            logger.warning("Missing required state machine components for conversion")
            return {}
            
        # Start with initial state
        current_state = initial_state
        step_num = 1
        visited_states = set()
        
        # Prevent infinite loops
        while current_state not in visited_states and step_num <= 10:
            visited_states.add(current_state)
            
            # Find transitions from current state
            for transition_key, transition in transitions.items():
                if transition_key.startswith(f"{current_state}->"):
                    to_state = transition_key.split("->")[1]
                    action_type = transition.get("action")
                    
                    # Create step based on transition type
                    if action_type == "click":
                        target = transition.get("target", {})
                        
                        step = {
                            "description": f"Click to go from {current_state} to {to_state}",
                            "find_and_click": {
                                "type": target.get("type", "any"),
                                "text": target.get("text", ""),
                                "text_match": target.get("text_match", "contains")
                            },
                            "expected_delay": transition.get("expected_delay", 2)
                        }
                        
                        # Add verification if target state has required elements
                        if to_state in states:
                            verify = []
                            for req in states[to_state].get("required_elements", []):
                                verify.append({
                                    "type": req.get("type", "any"),
                                    "text": req.get("text", ""),
                                    "text_match": req.get("text_match", "contains")
                                })
                            if verify:
                                step["verify_success"] = verify
                        
                        steps[str(step_num)] = step
                        step_num += 1
                        current_state = to_state
                        break
                        
                    elif action_type == "wait":
                        step = {
                            "description": f"Wait during {current_state}",
                            "action": "wait",
                            "duration": transition.get("duration", 10)
                        }
                        steps[str(step_num)] = step
                        step_num += 1
                        current_state = to_state
                        break
        
        logger.info(f"Converted state machine to {len(steps)} steps")
        return steps