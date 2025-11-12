# backend/app/services/file_upload_parser.py
"""
File Upload and Management Service
Handles secure file uploads, validation, and storage
Author: Eng. STEPHEN ODHIAMBO
"""

import os
import uuid
import shutil
from typing import List, Optional, Dict, Any
from fastapi import UploadFile, HTTPException, status
from pathlib import Path
import magic
import hashlib

from app.config import settings


class FileService:
    """Service for handling file uploads and management"""
    
    @staticmethod
    def get_file_extension(filename: str) -> str:
        """Extract file extension from filename"""
        return filename.split('.')[-1].lower() if '.' in filename else ''
    
    @staticmethod
    def validate_file(file: UploadFile) -> bool:
        """Validate uploaded file"""
        # Check file extension
        ext = FileService.get_file_extension(file.filename)
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type .{ext} not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
        
        return True
    
    @staticmethod
    def generate_unique_filename(original_filename: str) -> str:
        """Generate unique filename while preserving extension"""
        ext = FileService.get_file_extension(original_filename)
        unique_id = str(uuid.uuid4())
        return f"{unique_id}.{ext}"
    
    @staticmethod
    async def save_upload_file(
        file: UploadFile,
        project_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Save uploaded file to disk and return metadata
        """
        # Validate file
        FileService.validate_file(file)
        
        # Create directory structure: uploads/user_id/project_id/
        upload_path = Path(settings.UPLOAD_DIR) / str(user_id) / str(project_id)
        upload_path.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        unique_filename = FileService.generate_unique_filename(file.filename)
        file_path = upload_path / unique_filename
        
        # Read file content
        content = await file.read()
        
        # Check file size
        file_size = len(content)
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE / (1024*1024)}MB"
            )
        
        # Calculate file hash for integrity
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Detect MIME type
        mime_type = magic.from_buffer(content, mime=True)
        
        return {
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "relative_path": f"{user_id}/{project_id}/{unique_filename}",
            "file_size": file_size,
            "file_hash": file_hash,
            "mime_type": mime_type,
            "extension": FileService.get_file_extension(file.filename)
        }
    
    @staticmethod
    def delete_file(file_path: str) -> bool:
        """Delete a file from disk"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {file_path}: {str(e)}")
            return False
    
    @staticmethod
    def delete_project_files(user_id: str, project_id: str) -> bool:
        """Delete all files for a project"""
        try:
            project_path = Path(settings.UPLOAD_DIR) / str(user_id) / str(project_id)
            if project_path.exists():
                shutil.rmtree(project_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting project files: {str(e)}")
            return False


# backend/app/parsers/pdf_parser.py
"""
PDF Parser using PyMuPDF (fitz) and pdfplumber
Extracts vector graphics, text, and rasterizes pages
"""

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
import io
from typing import Dict, List, Any, Tuple
import numpy as np


class PDFParser:
    """Parse PDF files and extract content"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = fitz.open(file_path)
        self.metadata = self.extract_metadata()
    
    def extract_metadata(self) -> Dict[str, Any]:
        """Extract PDF metadata"""
        return {
            "page_count": len(self.doc),
            "title": self.doc.metadata.get("title", ""),
            "author": self.doc.metadata.get("author", ""),
            "subject": self.doc.metadata.get("subject", ""),
            "creator": self.doc.metadata.get("creator", ""),
        }
    
    def extract_text(self, page_num: int = 0) -> str:
        """Extract text from a specific page"""
        if page_num >= len(self.doc):
            return ""
        
        page = self.doc[page_num]
        return page.get_text()
    
    def extract_all_text(self) -> str:
        """Extract text from all pages"""
        text = ""
        for page in self.doc:
            text += page.get_text() + "\n"
        return text
    
    def extract_vector_data(self, page_num: int = 0) -> List[Dict[str, Any]]:
        """Extract vector graphics data (lines, rectangles, etc.)"""
        if page_num >= len(self.doc):
            return []
        
        page = self.doc[page_num]
        drawings = page.get_drawings()
        
        vector_data = []
        for drawing in drawings:
            vector_data.append({
                "type": drawing["type"],
                "rect": drawing["rect"],
                "items": drawing.get("items", [])
            })
        
        return vector_data
    
    def rasterize_page(self, page_num: int = 0, dpi: int = 300) -> Image.Image:
        """Rasterize a page to an image for OCR"""
        if page_num >= len(self.doc):
            raise ValueError(f"Page {page_num} does not exist")
        
        page = self.doc[page_num]
        
        # Calculate zoom factor for desired DPI
        # Default is 72 DPI, so zoom = desired_dpi / 72
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Render page to pixmap
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        return img
    
    def extract_tables(self, page_num: int = 0) -> List[List[str]]:
        """Extract tables from PDF using pdfplumber"""
        with pdfplumber.open(self.file_path) as pdf:
            if page_num >= len(pdf.pages):
                return []
            
            page = pdf.pages[page_num]
            tables = page.extract_tables()
            
            return tables or []
    
    def get_page_dimensions(self, page_num: int = 0) -> Tuple[float, float]:
        """Get page dimensions in points"""
        if page_num >= len(self.doc):
            return (0, 0)
        
        page = self.doc[page_num]
        rect = page.rect
        return (rect.width, rect.height)
    
    def process_pdf(self) -> Dict[str, Any]:
        """
        Complete PDF processing pipeline
        Returns comprehensive data structure
        """
        result = {
            "metadata": self.metadata,
            "pages": []
        }
        
        for page_num in range(len(self.doc)):
            page_data = {
                "page_number": page_num + 1,
                "dimensions": self.get_page_dimensions(page_num),
                "text": self.extract_text(page_num),
                "vector_data": self.extract_vector_data(page_num),
                "tables": self.extract_tables(page_num),
                "raster_image": None  # Will be processed by OCR service
            }
            result["pages"].append(page_data)
        
        return result
    
    def close(self):
        """Close the PDF document"""
        if self.doc:
            self.doc.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# backend/app/parsers/dwg_parser.py
"""
DWG/DXF Parser using ezdxf
Extracts geometric entities and layer information
"""

import ezdxf
from typing import Dict, List, Any, Tuple


class DWGParser:
    """Parse DWG/DXF files and extract CAD data"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            self.doc = ezdxf.readfile(file_path)
            self.modelspace = self.doc.modelspace()
        except Exception as e:
            raise ValueError(f"Failed to parse DWG/DXF file: {str(e)}")
    
    def extract_metadata(self) -> Dict[str, Any]:
        """Extract DWG metadata"""
        header = self.doc.header
        return {
            "dxf_version": self.doc.dxfversion,
            "units": header.get("$INSUNITS", 0),
            "drawing_limits": {
                "min": header.get("$LIMMIN", (0, 0)),
                "max": header.get("$LIMMAX", (0, 0))
            }
        }
    
    def extract_layers(self) -> List[Dict[str, Any]]:
        """Extract layer information"""
        layers = []
        for layer in self.doc.layers:
            layers.append({
                "name": layer.dxf.name,
                "color": layer.dxf.color,
                "linetype": layer.dxf.linetype,
                "is_off": layer.is_off(),
                "is_frozen": layer.is_frozen(),
                "is_locked": layer.is_locked()
            })
        return layers
    
    def extract_lines(self) -> List[Dict[str, Any]]:
        """Extract all line entities"""
        lines = []
        for line in self.modelspace.query('LINE'):
            lines.append({
                "type": "LINE",
                "layer": line.dxf.layer,
                "start": (line.dxf.start.x, line.dxf.start.y, line.dxf.start.z),
                "end": (line.dxf.end.x, line.dxf.end.y, line.dxf.end.z),
                "length": line.dxf.start.distance(line.dxf.end)
            })
        return lines
    
    def extract_circles(self) -> List[Dict[str, Any]]:
        """Extract all circle entities"""
        circles = []
        for circle in self.modelspace.query('CIRCLE'):
            circles.append({
                "type": "CIRCLE",
                "layer": circle.dxf.layer,
                "center": (circle.dxf.center.x, circle.dxf.center.y, circle.dxf.center.z),
                "radius": circle.dxf.radius
            })
        return circles
    
    def extract_polylines(self) -> List[Dict[str, Any]]:
        """Extract all polyline entities"""
        polylines = []
        for polyline in self.modelspace.query('LWPOLYLINE'):
            points = [(p[0], p[1]) for p in polyline.get_points()]
            polylines.append({
                "type": "POLYLINE",
                "layer": polyline.dxf.layer,
                "points": points,
                "is_closed": polyline.closed
            })
        return polylines
    
    def extract_text(self) -> List[Dict[str, Any]]:
        """Extract all text entities"""
        texts = []
        for text in self.modelspace.query('TEXT'):
            texts.append({
                "type": "TEXT",
                "layer": text.dxf.layer,
                "content": text.dxf.text,
                "position": (text.dxf.insert.x, text.dxf.insert.y, text.dxf.insert.z),
                "height": text.dxf.height,
                "rotation": text.dxf.rotation
            })
        
        # Also extract MTEXT (multiline text)
        for mtext in self.modelspace.query('MTEXT'):
            texts.append({
                "type": "MTEXT",
                "layer": mtext.dxf.layer,
                "content": mtext.text,
                "position": (mtext.dxf.insert.x, mtext.dxf.insert.y, mtext.dxf.insert.z),
                "height": mtext.dxf.char_height
            })
        
        return texts
    
    def extract_dimensions(self) -> List[Dict[str, Any]]:
        """Extract dimension entities"""
        dimensions = []
        for dim in self.modelspace.query('DIMENSION'):
            dimensions.append({
                "type": "DIMENSION",
                "layer": dim.dxf.layer,
                "measurement": dim.get_measurement() if hasattr(dim, 'get_measurement') else None
            })
        return dimensions
    
    def extract_blocks(self) -> List[Dict[str, Any]]:
        """Extract block references (symbols)"""
        blocks = []
        for insert in self.modelspace.query('INSERT'):
            blocks.append({
                "type": "BLOCK",
                "name": insert.dxf.name,
                "layer": insert.dxf.layer,
                "position": (insert.dxf.insert.x, insert.dxf.insert.y, insert.dxf.insert.z),
                "scale": (insert.dxf.xscale, insert.dxf.yscale, insert.dxf.zscale),
                "rotation": insert.dxf.rotation
            })
        return blocks
    
    def calculate_bounding_box(self) -> Dict[str, Tuple[float, float]]:
        """Calculate overall bounding box of all entities"""
        all_points = []
        
        # Collect all points from lines
        for line in self.modelspace.query('LINE'):
            all_points.append((line.dxf.start.x, line.dxf.start.y))
            all_points.append((line.dxf.end.x, line.dxf.end.y))
        
        # Collect points from polylines
        for polyline in self.modelspace.query('LWPOLYLINE'):
            all_points.extend([(p[0], p[1]) for p in polyline.get_points()])
        
        if not all_points:
            return {"min": (0, 0), "max": (0, 0)}
        
        xs, ys = zip(*all_points)
        return {
            "min": (min(xs), min(ys)),
            "max": (max(xs), max(ys))
        }
    
    def process_dwg(self) -> Dict[str, Any]:
        """
        Complete DWG/DXF processing pipeline
        Returns comprehensive data structure
        """
        return {
            "metadata": self.extract_metadata(),
            "layers": self.extract_layers(),
            "bounding_box": self.calculate_bounding_box(),
            "entities": {
                "lines": self.extract_lines(),
                "circles": self.extract_circles(),
                "polylines": self.extract_polylines(),
                "text": self.extract_text(),
                "dimensions": self.extract_dimensions(),
                "blocks": self.extract_blocks()
            }
        }


# backend/app/parsers/ifc_parser.py
"""
IFC Parser using IfcOpenShell
Extracts BIM data and semantic information
"""

import ifcopenshell
import ifcopenshell.geom
from typing import Dict, List, Any


class IFCParser:
    """Parse IFC files and extract BIM data"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            self.ifc_file = ifcopenshell.open(file_path)
        except Exception as e:
            raise ValueError(f"Failed to parse IFC file: {str(e)}")
    
    def extract_project_info(self) -> Dict[str, Any]:
        """Extract project information"""
        project = self.ifc_file.by_type("IfcProject")[0]
        return {
            "name": project.Name,
            "description": project.Description,
            "global_id": project.GlobalId
        }
    
    def extract_buildings(self) -> List[Dict[str, Any]]:
        """Extract building information"""
        buildings = []
        for building in self.ifc_file.by_type("IfcBuilding"):
            buildings.append({
                "name": building.Name,
                "description": building.Description,
                "global_id": building.GlobalId,
                "elevation": building.ElevationOfRefHeight if hasattr(building, 'ElevationOfRefHeight') else None
            })
        return buildings
    
    def extract_storeys(self) -> List[Dict[str, Any]]:
        """Extract building storey information"""
        storeys = []
        for storey in self.ifc_file.by_type("IfcBuildingStorey"):
            storeys.append({
                "name": storey.Name,
                "description": storey.Description,
                "global_id": storey.GlobalId,
                "elevation": storey.Elevation if hasattr(storey, 'Elevation') else None
            })
        return storeys
    
    def extract_walls(self) -> List[Dict[str, Any]]:
        """Extract wall elements"""
        walls = []
        for wall in self.ifc_file.by_type("IfcWall"):
            walls.append({
                "type": "WALL",
                "name": wall.Name,
                "global_id": wall.GlobalId,
                "description": wall.Description
            })
        return walls
    
    def extract_slabs(self) -> List[Dict[str, Any]]:
        """Extract slab elements"""
        slabs = []
        for slab in self.ifc_file.by_type("IfcSlab"):
            slabs.append({
                "type": "SLAB",
                "name": slab.Name,
                "global_id": slab.GlobalId,
                "predefined_type": slab.PredefinedType if hasattr(slab, 'PredefinedType') else None
            })
        return slabs
    
    def extract_columns(self) -> List[Dict[str, Any]]:
        """Extract column elements"""
        columns = []
        for column in self.ifc_file.by_type("IfcColumn"):
            columns.append({
                "type": "COLUMN",
                "name": column.Name,
                "global_id": column.GlobalId
            })
        return columns
    
    def extract_beams(self) -> List[Dict[str, Any]]:
        """Extract beam elements"""
        beams = []
        for beam in self.ifc_file.by_type("IfcBeam"):
            beams.append({
                "type": "BEAM",
                "name": beam.Name,
                "global_id": beam.GlobalId
            })
        return beams
    
    def extract_doors(self) -> List[Dict[str, Any]]:
        """Extract door elements"""
        doors = []
        for door in self.ifc_file.by_type("IfcDoor"):
            doors.append({
                "type": "DOOR",
                "name": door.Name,
                "global_id": door.GlobalId,
                "overall_height": door.OverallHeight if hasattr(door, 'OverallHeight') else None,
                "overall_width": door.OverallWidth if hasattr(door, 'OverallWidth') else None
            })
        return doors
    
    def extract_windows(self) -> List[Dict[str, Any]]:
        """Extract window elements"""
        windows = []
        for window in self.ifc_file.by_type("IfcWindow"):
            windows.append({
                "type": "WINDOW",
                "name": window.Name,
                "global_id": window.GlobalId,
                "overall_height": window.OverallHeight if hasattr(window, 'OverallHeight') else None,
                "overall_width": window.OverallWidth if hasattr(window, 'OverallWidth') else None
            })
        return windows
    
    def extract_quantities(self) -> Dict[str, Any]:
        """Extract quantity takeoff data"""
        quantities = {
            "walls": {"count": 0, "area": 0, "volume": 0},
            "slabs": {"count": 0, "area": 0, "volume": 0},
            "columns": {"count": 0, "height": 0, "volume": 0},
            "beams": {"count": 0, "length": 0, "volume": 0},
            "doors": {"count": 0},
            "windows": {"count": 0}
        }
        
        # Count elements (basic quantities - detailed extraction would require geometry processing)
        quantities["walls"]["count"] = len(self.ifc_file.by_type("IfcWall"))
        quantities["slabs"]["count"] = len(self.ifc_file.by_type("IfcSlab"))
        quantities["columns"]["count"] = len(self.ifc_file.by_type("IfcColumn"))
        quantities["beams"]["count"] = len(self.ifc_file.by_type("IfcBeam"))
        quantities["doors"]["count"] = len(self.ifc_file.by_type("IfcDoor"))
        quantities["windows"]["count"] = len(self.ifc_file.by_type("IfcWindow"))
        
        return quantities
    
    def process_ifc(self) -> Dict[str, Any]:
        """
        Complete IFC processing pipeline
        Returns comprehensive data structure
        """
        return {
            "project": self.extract_project_info(),
            "buildings": self.extract_buildings(),
            "storeys": self.extract_storeys(),
            "elements": {
                "walls": self.extract_walls(),
                "slabs": self.extract_slabs(),
                "columns": self.extract_columns(),
                "beams": self.extract_beams(),
                "doors": self.extract_doors(),
                "windows": self.extract_windows()
            },
            "quantities": self.extract_quantities()
        }


# backend/app/parsers/image_parser.py
"""
Image Parser for JPEG/PNG drawings
Preprocesses images for OCR and AI analysis
"""

from PIL import Image
import cv2
import numpy as np
from typing import Dict, Any, Tuple


class ImageParser:
    """Parse and preprocess image files"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.image = Image.open(file_path)
        self.cv_image = cv2.imread(file_path)
    
    def get_image_info(self) -> Dict[str, Any]:
        """Get basic image information"""
        return {
            "format": self.image.format,
            "mode": self.image.mode,
            "size": self.image.size,
            "width": self.image.width,
            "height": self.image.height
        }
    
    def preprocess_for_ocr(self) -> np.ndarray:
        """
        Preprocess image for better OCR results
        - Convert to grayscale
        - Denoise
        - Threshold
        """
        # Convert to grayscale
        gray = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2GRAY)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # Adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            denoised, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        return thresh
    
    def detect_lines(self) -> Dict[str, Any]:
        """Detect lines in the image using Hough Transform"""
        gray = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        lines = cv2.HoughLinesP(
            edges, 1, np.pi/180, 100,
            minLineLength=100, maxLineGap=10
        )
        
        return {
            "line_count": len(lines) if lines is not None else 0,
            "lines": lines.tolist() if lines is not None else []
        }
    
    def process_image(self) -> Dict[str, Any]:
        """
        Complete image processing pipeline
        """
        return {
            "info": self.get_image_info(),
            "preprocessed": True,
            "line_detection": self.detect_lines()
        }
