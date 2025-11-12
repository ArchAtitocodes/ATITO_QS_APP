# backend/app/services/ocr_ai_service.py
"""
OCR Service with Google Vision API (primary) and Tesseract (fallback)
Author: Eng. STEPHEN ODHIAMBO
"""

import os
from typing import Dict, List, Any, Optional, Tuple
from PIL import Image
import pytesseract
from google.cloud import vision
import io
import re

from app.config import settings


class OCRService:
    """Optical Character Recognition service with dual-engine support"""
    
    def __init__(self):
        """Initialize OCR engines"""
        # Initialize Google Vision client if credentials available
        self.vision_client = None
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            try:
                self.vision_client = vision.ImageAnnotatorClient()
            except Exception as e:
                print(f"Warning: Could not initialize Google Vision API: {str(e)}")
    
    def extract_text_google_vision(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text using Google Vision API (primary method)
        Returns text with confidence scores
        """
        if not self.vision_client:
            return {
                "success": False,
                "error": "Google Vision API not configured",
                "text": "",
                "confidence": 0.0
            }
        
        try:
            # Read image file
            with io.open(image_path, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            
            # Perform text detection
            response = self.vision_client.text_detection(image=image)
            texts = response.text_annotations
            
            if not texts:
                return {
                    "success": True,
                    "text": "",
                    "confidence": 0.0,
                    "annotations": []
                }
            
            # First annotation contains all text
            full_text = texts[0].description
            
            # Extract individual word annotations with confidence
            annotations = []
            for text in texts[1:]:  # Skip first (full text)
                annotations.append({
                    "text": text.description,
                    "confidence": text.confidence if hasattr(text, 'confidence') else 1.0,
                    "bounding_box": [
                        {
                            "x": vertex.x,
                            "y": vertex.y
                        } for vertex in text.bounding_poly.vertices
                    ]
                })
            
            # Calculate average confidence
            avg_confidence = sum(a['confidence'] for a in annotations) / len(annotations) if annotations else 1.0
            
            return {
                "success": True,
                "text": full_text,
                "confidence": avg_confidence,
                "annotations": annotations,
                "method": "google_vision"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0
            }
    
    def extract_text_tesseract(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text using Tesseract OCR (fallback method)
        """
        try:
            # Open image
            image = Image.open(image_path)
            
            # Perform OCR with confidence data
            ocr_data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config='--psm 6'  # Assume uniform text block
            )
            
            # Extract text and calculate confidence
            texts = []
            confidences = []
            
            for i, conf in enumerate(ocr_data['conf']):
                if conf > 0:  # Valid detection
                    text = ocr_data['text'][i].strip()
                    if text:
                        texts.append(text)
                        confidences.append(float(conf) / 100.0)
            
            full_text = ' '.join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {
                "success": True,
                "text": full_text,
                "confidence": avg_confidence,
                "method": "tesseract"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0
            }
    
    def extract_text(self, image_path: str, force_tesseract: bool = False) -> Dict[str, Any]:
        """
        Extract text with automatic fallback
        Primary: Google Vision API
        Fallback: Tesseract OCR
        """
        if force_tesseract:
            return self.extract_text_tesseract(image_path)
        
        # Try Google Vision first
        result = self.extract_text_google_vision(image_path)
        
        # If Google Vision fails or confidence too low, fallback to Tesseract
        if not result["success"] or result["confidence"] < settings.OCR_CONFIDENCE_THRESHOLD:
            print(f"Google Vision confidence low ({result['confidence']:.2f}), falling back to Tesseract")
            tesseract_result = self.extract_text_tesseract(image_path)
            
            # Use whichever has higher confidence
            if tesseract_result["success"] and tesseract_result["confidence"] > result["confidence"]:
                return tesseract_result
        
        return result
    
    def extract_dimensions(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract dimension measurements from text
        Looks for patterns like: 3000, 3.0m, 3000mm, etc.
        """
        dimensions = []
        
        # Patterns for dimensions
        patterns = [
            r'(\d+\.?\d*)\s*mm',  # millimeters
            r'(\d+\.?\d*)\s*m(?!\w)',  # meters (not followed by more letters)
            r'(\d+\.?\d*)\s*cm',  # centimeters
            r'(\d+)x(\d+)',  # dimensions like 3000x2400
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                dimensions.append({
                    "value": match.group(0),
                    "position": match.span(),
                    "pattern": pattern
                })
        
        return dimensions


# backend/app/services/ai_service.py
"""
AI Service for object detection and element recognition
Uses YOLOv8 for detecting architectural elements
Author: Eng. STEPHEN ODHIAMBO
"""

import torch
from ultralytics import YOLO
from typing import Dict, List, Any, Tuple
import cv2
import numpy as np
from PIL import Image

from app.config import settings


class AIService:
    """AI service for drawing analysis and element detection"""
    
    def __init__(self):
        """Initialize AI models"""
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {self.device}")
        
        # Load YOLOv8 model
        try:
            self.model = YOLO(settings.MODEL_PATH)
            self.model.to(self.device)
            print(f"Loaded YOLOv8 model from {settings.MODEL_PATH}")
        except Exception as e:
            print(f"Warning: Could not load YOLOv8 model: {str(e)}")
            self.model = None
    
    def detect_elements(self, image_path: str) -> Dict[str, Any]:
        """
        Detect architectural elements in drawing using YOLOv8
        Elements: walls, columns, beams, doors, windows, slabs
        """
        if not self.model:
            return {
                "success": False,
                "error": "Model not loaded",
                "detections": []
            }
        
        try:
            # Run inference
            results = self.model(image_path)
            
            # Process results
            detections = []
            for result in results:
                boxes = result.boxes
                
                for i in range(len(boxes)):
                    detection = {
                        "class_id": int(boxes.cls[i]),
                        "class_name": result.names[int(boxes.cls[i])],
                        "confidence": float(boxes.conf[i]),
                        "bbox": boxes.xyxy[i].tolist(),  # [x1, y1, x2, y2]
                        "center": self._calculate_center(boxes.xyxy[i].tolist())
                    }
                    detections.append(detection)
            
            return {
                "success": True,
                "detections": detections,
                "image_shape": results[0].orig_shape
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "detections": []
            }
    
    def _calculate_center(self, bbox: List[float]) -> Tuple[float, float]:
        """Calculate center point of bounding box"""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    
    def identify_drawing_type(self, image_path: str) -> Dict[str, Any]:
        """
        Identify the type of drawing: floor plan, elevation, section, etc.
        Uses heuristics based on detected elements and layout
        """
        detections = self.detect_elements(image_path)
        
        if not detections["success"]:
            return {
                "drawing_type": "unknown",
                "confidence": 0.0
            }
        
        # Count element types
        element_counts = {}
        for det in detections["detections"]:
            class_name = det["class_name"]
            element_counts[class_name] = element_counts.get(class_name, 0) + 1
        
        # Heuristics for drawing type
        # Floor plans typically have walls, doors, windows
        # Elevations have fewer walls, more windows
        # Sections show height dimensions
        
        if element_counts.get("wall", 0) > 4 and element_counts.get("door", 0) > 0:
            return {
                "drawing_type": "floor_plan",
                "confidence": 0.85,
                "elements": element_counts
            }
        elif element_counts.get("window", 0) > element_counts.get("wall", 0):
            return {
                "drawing_type": "elevation",
                "confidence": 0.75,
                "elements": element_counts
            }
        else:
            return {
                "drawing_type": "section",
                "confidence": 0.60,
                "elements": element_counts
            }
    
    def extract_dimensions_from_detection(self, detections: List[Dict]) -> List[Dict[str, Any]]:
        """
        Calculate dimensions based on detected elements
        Measures distances between elements
        """
        dimensions = []
        
        # Sort detections by position for easier processing
        sorted_dets = sorted(detections, key=lambda x: x["center"][0])
        
        # Calculate horizontal distances between consecutive elements
        for i in range(len(sorted_dets) - 1):
            elem1 = sorted_dets[i]
            elem2 = sorted_dets[i + 1]
            
            distance = elem2["center"][0] - elem1["center"][0]
            
            dimensions.append({
                "type": "horizontal",
                "from": elem1["class_name"],
                "to": elem2["class_name"],
                "distance_pixels": distance,
                "confidence": min(elem1["confidence"], elem2["confidence"])
            })
        
        return dimensions
    
    def analyze_structural_system(self, detections: List[Dict]) -> Dict[str, Any]:
        """
        Analyze structural system based on detected elements
        Determines if RC frame, load bearing, etc.
        """
        column_count = sum(1 for d in detections if d["class_name"] == "column")
        beam_count = sum(1 for d in detections if d["class_name"] == "beam")
        wall_count = sum(1 for d in detections if d["class_name"] == "wall")
        
        # Heuristics
        if column_count > 4 and beam_count > 4:
            return {
                "system_type": "rc_frame",
                "confidence": 0.85,
                "reasoning": f"Detected {column_count} columns and {beam_count} beams"
            }
        elif wall_count > 8 and column_count < 2:
            return {
                "system_type": "load_bearing",
                "confidence": 0.80,
                "reasoning": f"Detected {wall_count} walls with minimal columns"
            }
        else:
            return {
                "system_type": "composite",
                "confidence": 0.60,
                "reasoning": "Mixed structural elements detected"
            }
    
    def calculate_areas(self, detections: List[Dict], image_shape: Tuple[int, int]) -> Dict[str, Any]:
        """
        Calculate approximate areas based on detected elements
        Note: This requires scale calibration for accurate results
        """
        areas = {
            "walls": 0.0,
            "slabs": 0.0,
            "openings": 0.0
        }
        
        for det in detections:
            bbox = det["bbox"]
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            
            # Categorize by element type
            if det["class_name"] == "wall":
                areas["walls"] += area_pixels
            elif det["class_name"] in ["slab", "floor"]:
                areas["slabs"] += area_pixels
            elif det["class_name"] in ["door", "window"]:
                areas["openings"] += area_pixels
        
        return {
            "areas_pixels": areas,
            "image_dimensions": image_shape,
            "note": "Requires scale calibration for actual dimensions"
        }
    
    def process_drawing(self, image_path: str) -> Dict[str, Any]:
        """
        Complete AI processing pipeline for a drawing
        Returns comprehensive analysis
        """
        # Detect elements
        detection_result = self.detect_elements(image_path)
        
        if not detection_result["success"]:
            return {
                "success": False,
                "error": detection_result["error"]
            }
        
        detections = detection_result["detections"]
        
        # Identify drawing type
        drawing_type = self.identify_drawing_type(image_path)
        
        # Extract dimensions
        dimensions = self.extract_dimensions_from_detection(detections)
        
        # Analyze structural system
        structural_system = self.analyze_structural_system(detections)
        
        # Calculate areas
        areas = self.calculate_areas(detections, detection_result["image_shape"])
        
        # Calculate overall confidence score
        avg_confidence = sum(d["confidence"] for d in detections) / len(detections) if detections else 0.0
        
        return {
            "success": True,
            "drawing_type": drawing_type,
            "structural_system": structural_system,
            "elements": {
                "count": len(detections),
                "detections": detections
            },
            "dimensions": dimensions,
            "areas": areas,
            "overall_confidence": avg_confidence,
            "needs_review": avg_confidence < settings.AI_CONFIDENCE_THRESHOLD
        }


# backend/app/services/dimension_extraction_service.py
"""
Dimension Extraction Service
Combines OCR and AI to extract and validate dimensions
Author: Eng. STEPHEN ODHIAMBO
"""

import re
from typing import Dict, List, Any, Optional


class DimensionExtractionService:
    """Extract and validate dimensions from drawings"""
    
    def __init__(self):
        self.ocr_service = OCRService()
        self.ai_service = AIService()
    
    def extract_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract dimensions from OCR text
        """
        dimensions = []
        
        # Regex patterns for various dimension formats
        patterns = {
            'metric_mm': r'(\d+\.?\d*)\s*mm',
            'metric_m': r'(\d+\.?\d*)\s*m(?!\w)',
            'metric_cm': r'(\d+\.?\d*)\s*cm',
            'dimension_pair': r'(\d+)\s*x\s*(\d+)',
            'dimension_feet': r"(\d+)'\s*-?\s*(\d+)?\"?",
            'simple_number': r'\b(\d{3,5})\b'  # 3-5 digit numbers (likely dimensions)
        }
        
        for pattern_name, pattern in patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                dim = {
                    "raw_value": match.group(0),
                    "pattern_type": pattern_name,
                    "position": match.span()
                }
                
                # Convert to standard unit (mm)
                if pattern_name == 'metric_mm':
                    dim["value_mm"] = float(match.group(1))
                elif pattern_name == 'metric_m':
                    dim["value_mm"] = float(match.group(1)) * 1000
                elif pattern_name == 'metric_cm':
                    dim["value_mm"] = float(match.group(1)) * 10
                elif pattern_name == 'dimension_pair':
                    dim["value_mm"] = [float(match.group(1)), float(match.group(2))]
                elif pattern_name == 'simple_number':
                    dim["value_mm"] = float(match.group(1))  # Assume mm
                
                dimensions.append(dim)
        
        return dimensions
    
    def validate_dimensions(self, dimensions: List[Dict]) -> List[Dict]:
        """
        Validate extracted dimensions for reasonableness
        Building dimensions typically range from 100mm to 100,000mm
        """
        validated = []
        
        for dim in dimensions:
            value = dim.get("value_mm")
            if isinstance(value, list):
                # Validate both values in pair
                if all(100 <= v <= 100000 for v in value):
                    dim["valid"] = True
                    validated.append(dim)
            elif isinstance(value, (int, float)):
                if 100 <= value <= 100000:
                    dim["valid"] = True
                    validated.append(dim)
        
        return validated
    
    def correlate_with_ai_detection(
        self,
        ocr_dimensions: List[Dict],
        ai_detections: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Correlate OCR-extracted dimensions with AI-detected elements
        Assigns dimensions to nearest detected elements
        """
        correlated = []
        
        for dimension in ocr_dimensions:
            # Find nearest AI detection
            # This would require position information from both OCR and AI
            # Simplified version:
            correlated.append({
                "dimension": dimension,
                "assigned_to": "unknown",  # Would be determined by proximity
                "confidence": 0.70
            })
        
        return correlated
    
    def extract_scale(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract drawing scale from text
        Common formats: 1:100, 1:50, 1/4" = 1'-0"
        """
        scale_patterns = [
            r'1\s*:\s*(\d+)',  # 1:100
            r'scale\s*:\s*1\s*:\s*(\d+)',  # Scale: 1:100
            r'(\d+)\s*:\s*1',  # 100:1 (less common)
        ]
        
        for pattern in scale_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                scale_value = int(match.group(1))
                return {
                    "scale": f"1:{scale_value}",
                    "ratio": scale_value,
                    "confidence": 0.90
                }
        
        return None
    
    def process_drawing_dimensions(
        self,
        image_path: str
    ) -> Dict[str, Any]:
        """
        Complete dimension extraction pipeline
        """
        # Extract text via OCR
        ocr_result = self.ocr_service.extract_text(image_path)
        
        # Extract dimensions from text
        text_dimensions = self.extract_from_text(ocr_result["text"])
        
        # Validate dimensions
        valid_dimensions = self.validate_dimensions(text_dimensions)
        
        # Extract scale
        scale = self.extract_scale(ocr_result["text"])
        
        # Get AI analysis
        ai_result = self.ai_service.process_drawing(image_path)
        
        # Correlate dimensions with detected elements
        correlated = []
        if ai_result["success"]:
            correlated = self.correlate_with_ai_detection(
                valid_dimensions,
                ai_result["elements"]["detections"]
            )
        
        return {
            "success": True,
            "ocr_confidence": ocr_result["confidence"],
            "ai_confidence": ai_result.get("overall_confidence", 0.0),
            "scale": scale,
            "dimensions": {
                "total_found": len(text_dimensions),
                "valid": len(valid_dimensions),
                "details": valid_dimensions
            },
            "correlated_dimensions": correlated,
            "needs_review": (
                ocr_result["confidence"] < settings.OCR_CONFIDENCE_THRESHOLD or
                ai_result.get("overall_confidence", 0) < settings.AI_CONFIDENCE_THRESHOLD
            )
        }
