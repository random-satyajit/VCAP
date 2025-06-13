"""
Client for interacting with the Omniparser server.
Sends screenshots and receives UI element detections.
"""

import os
import base64
import logging
import requests
import json
import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from modules.gemma_client import BoundingBox  # Reuse the BoundingBox class

logger = logging.getLogger(__name__)

class OmniparserClient:
    """Client for the Omniparser API server."""
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        """
        Initialize the Omniparser client.
        
        Args:
            api_url: URL of the Omniparser API server
        """
        self.api_url = api_url
        self.session = requests.Session()
        logger.info(f"OmniparserClient initialized with API URL: {api_url}")
        
        # Test connection to the API
        try:
            self._test_connection()
            logger.info("Successfully connected to Omniparser API")
        except Exception as e:
            logger.error(f"Failed to connect to Omniparser API: {str(e)}")
            logger.error(f"Please ensure Omniparser server is running at {api_url}")
    
    def _test_connection(self):
        """Test connection to the API."""
        response = self.session.get(f"{self.api_url}/probe")
        response.raise_for_status()
        return response.json()
    
    def _encode_image(self, image_path: str) -> str:
        """
        Encode an image file to base64.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            Base64-encoded image string
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _parse_omniparser_response(self, response_data: Dict) -> List[BoundingBox]:
        """
        Parse the response from Omniparser into BoundingBox objects.
        """
        bounding_boxes = []
        
        # Log structure of response
        if "parsed_content_list" in response_data:
            content_list = response_data.get("parsed_content_list", [])
            logger.info(f"Omniparser returned {len(content_list)} items in parsed_content_list")
            
            # Print the first item as sample if available
            if content_list and len(content_list) > 0:
                logger.info(f"First item example: {json.dumps(content_list[0], indent=2)}")
        else:
            logger.warning("Response doesn't contain 'parsed_content_list' key")
            logger.info(f"Available keys: {list(response_data.keys())}")
        
        # Extract parsed content list from response
        parsed_content_list = response_data.get("parsed_content_list", [])
        
        for i, element in enumerate(parsed_content_list):
            # Extract coordinates and metadata
            try:
                # Log each element format for debugging
                logger.info(f"Processing element {i}: keys={list(element.keys())}")
                
                # Check how coordinates are stored
                if 'box_xyxy' in element:
                    box_coords = element['box_xyxy']
                    logger.info(f"Found box_xyxy format: {box_coords}")
                    x1, y1, x2, y2 = box_coords
                    
                    # Convert to our BoundingBox format
                    bbox = BoundingBox(
                        x=int(x1),
                        y=int(y1),
                        width=int(x2 - x1),
                        height=int(y2 - y1),
                        confidence=element.get('score', 0.9),
                        element_type=element.get('class', 'unknown'),
                        element_text=element.get('ocr', '')
                    )
                    bounding_boxes.append(bbox)
                elif 'bbox' in element:
                    # Alternative format
                    logger.info(f"Found bbox format: {element['bbox']}")
                    # Process alternative format...
                else:
                    logger.warning(f"No recognized box format in element: {list(element.keys())}")
                    
            except (KeyError, ValueError, IndexError) as e:
                logger.warning(f"Error parsing element {i}: {str(e)}")
        
        logger.info(f"Successfully extracted {len(bounding_boxes)} bounding boxes")
        return bounding_boxes
    
    def _format_bounding_boxes(self, bboxes: List[BoundingBox]) -> str:
        """
        Format bounding boxes into a readable string for logging.
        
        Args:
            bboxes: List of BoundingBox objects
            
        Returns:
            Formatted string representation
        """
        if not bboxes:
            return "No UI elements detected"
            
        formatted = []
        for i, bbox in enumerate(bboxes):
            element_text = bbox.element_text if bbox.element_text else "N/A"
            # Truncate long text
            if element_text and len(element_text) > 30:
                element_text = element_text[:27] + "..."
                
            formatted.append(
                f"[{i+1}] {bbox.element_type} (conf: {bbox.confidence:.2f}) at ({bbox.x},{bbox.y},{bbox.width}x{bbox.height}): '{element_text}'"
            )
        
        return "\n".join(formatted)
    
    def detect_ui_elements(self, image_path: str) -> List[BoundingBox]:
        """
        Send an image to Omniparser and get UI element detections.
        
        Args:
            image_path: Path to the screenshot image
        
        Returns:
            List of detected UI elements with bounding boxes
        
        Raises:
            RequestException: If the API request fails
            ValueError: If the response cannot be parsed
        """
        try:
            # Check if the image file exists
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            # Encode the image
            base64_image = self._encode_image(image_path)
            
            # Prepare the payload for Omniparser
            payload = {
                "base64_image": base64_image
            }
            
            # Send the request to Omniparser API
            logger.info(f"Sending request to {self.api_url}/parse/")
            response = self.session.post(
                f"{self.api_url}/parse/",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60  # Longer timeout for image processing
            )
            response.raise_for_status()
            
            # Parse the response
            response_data = response.json()
            
            # Create a clean copy without the base64 image data
            clean_response = response_data.copy()
            if "som_image_base64" in clean_response:
                clean_response.pop("som_image_base64")
                clean_response["som_image_base64_present"] = True
            
            # Save the clean JSON response to a file
            json_path = os.path.splitext(image_path)[0] + ".json"
            with open(json_path, "w", encoding="utf-8") as json_file:
                json.dump(clean_response, json_file, indent=2)
            logger.info(f"Saved clean Omniparser JSON response to {json_path}")

            # Log a clean version of the response (without the giant base64 string)
            logger.info(f"***OMNIPARSER RESPONSE SUMMARY***:")
            logger.info(f"Response keys: {list(response_data.keys())}")
            if "parsed_content_list" in response_data:
                parsed_items = response_data["parsed_content_list"]
                logger.info(f"Found {len(parsed_items)} UI elements")
                if parsed_items and len(parsed_items) > 0:
                    logger.info(f"First element example: {json.dumps(parsed_items[0], indent=2)}")
            
            # Log performance metrics if available
            if "latency" in response_data:
                logger.info(f"Omniparser processing time: {response_data['latency']:.2f} seconds")
            
            # Extract and convert bounding boxes
            bounding_boxes = self._parse_omniparser_response(response_data)
            
            # Save the annotated image if provided
            if "som_image_base64" in response_data:
                try:
                    annotated_dir = os.path.dirname(image_path)
                    annotated_path = os.path.join(annotated_dir, f"omniparser_{os.path.basename(image_path)}")
                    
                    # Decode and save the annotated image
                    img_data = base64.b64decode(response_data["som_image_base64"])
                    with open(annotated_path, "wb") as f:
                        f.write(img_data)
                    logger.info(f"Saved Omniparser annotated image to {annotated_path}")
                except Exception as e:
                    logger.warning(f"Failed to save annotated image: {str(e)}")
            
            # Log detected elements
            formatted_boxes = self._format_bounding_boxes(bounding_boxes)
            logger.info(f"Detected {len(bounding_boxes)} UI elements in {image_path}:")
            for line in formatted_boxes.split('\n'):
                logger.info(f"  {line}")
            
            return bounding_boxes
            
        except requests.RequestException as e:
            logger.error(f"Omniparser API request failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse Omniparser response: {str(e)}")
            raise ValueError(f"Invalid response from Omniparser API: {str(e)}")
    
    def close(self):
        """Close the session."""
        self.session.close()
        logger.info("Omniparser client session closed")