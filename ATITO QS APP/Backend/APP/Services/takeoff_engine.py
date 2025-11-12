# backend/app/services/takeoff_engine.py
"""
Quantity Takeoff Engine
Extracts quantities from processed drawings and applies waste factors
Author: Eng. STEPHEN ODHIAMBO
"""

from typing import Dict, List, Any, Tuple
import math
from sqlalchemy.orm import Session

from app.config import settings, MATERIAL_RECIPES
from app.models.boq import BOQItem
from app.models.project import Project


class TakeoffEngine:
    """
    Automated quantity takeoff engine
    Processes AI-detected elements and calculates quantities
    """
    
    def __init__(self, project: Project, db: Session):
        self.project = project
        self.db = db
        self.quantities = {}
        self.confidence_scores = {}
    
    def calculate_wall_quantities(self, walls: List[Dict]) -> Dict[str, Any]:
        """
        Calculate wall quantities
        Unit: sqm (square meters)
        """
        total_area = 0.0
        total_length = 0.0
        wall_details = []
        
        for wall in walls:
            # Extract dimensions from AI detection
            bbox = wall.get("bbox", [])
            if len(bbox) >= 4:
                # Calculate dimensions (requires scale calibration)
                length = abs(bbox[2] - bbox[0])
                height = abs(bbox[3] - bbox[1])
                
                # Assume average wall height if not specified (3m typical)
                wall_height = self.project.metadata.get("typical_wall_height", 3.0)
                
                # Area calculation
                area = length * wall_height
                total_area += area
                total_length += length
                
                wall_details.append({
                    "location": wall.get("location", "Unknown"),
                    "length": length,
                    "height": wall_height,
                    "area": area,
                    "confidence": wall.get("confidence", 0.8)
                })
        
        # Apply waste factor
        gross_area = total_area * settings.WASTE_BLOCKWORK
        
        return {
            "element_type": "wall",
            "unit": "sqm",
            "net_quantity": total_area,
            "waste_factor": settings.WASTE_BLOCKWORK,
            "gross_quantity": gross_area,
            "details": wall_details,
            "total_length": total_length
        }
    
    def calculate_column_quantities(self, columns: List[Dict]) -> Dict[str, Any]:
        """
        Calculate column quantities
        Unit: No. (number of columns)
        Also calculates concrete volume in cubic meters
        """
        column_count = len(columns)
        column_details = []
        total_volume = 0.0
        
        for column in columns:
            # Typical column dimensions (can be extracted from drawings)
            typical_size = self.project.metadata.get("typical_column_size", 0.3)  # 300x300mm
            typical_height = self.project.metadata.get("floor_height", 3.0)  # 3m
            
            # Volume per column
            volume = typical_size * typical_size * typical_height
            total_volume += volume
            
            column_details.append({
                "location": column.get("location", "Unknown"),
                "size": f"{typical_size}x{typical_size}m",
                "height": typical_height,
                "volume": volume,
                "confidence": column.get("confidence", 0.8)
            })
        
        # Apply waste factor for concrete
        gross_volume = total_volume * settings.WASTE_CONCRETE
        
        return {
            "element_type": "column",
            "unit": "No.",
            "count": column_count,
            "total_volume_m3": total_volume,
            "gross_volume_m3": gross_volume,
            "waste_factor": settings.WASTE_CONCRETE,
            "details": column_details
        }
    
    def calculate_beam_quantities(self, beams: List[Dict]) -> Dict[str, Any]:
        """
        Calculate beam quantities
        Unit: m (linear meters)
        """
        total_length = 0.0
        beam_details = []
        total_volume = 0.0
        
        for beam in beams:
            # Extract length from AI detection
            bbox = beam.get("bbox", [])
            if len(bbox) >= 4:
                length = abs(bbox[2] - bbox[0])
                total_length += length
                
                # Typical beam cross-section
                typical_width = self.project.metadata.get("typical_beam_width", 0.3)
                typical_depth = self.project.metadata.get("typical_beam_depth", 0.45)
                
                volume = length * typical_width * typical_depth
                total_volume += volume
                
                beam_details.append({
                    "location": beam.get("location", "Unknown"),
                    "length": length,
                    "cross_section": f"{typical_width}x{typical_depth}m",
                    "volume": volume,
                    "confidence": beam.get("confidence", 0.8)
                })
        
        # Apply waste factor
        gross_length = total_length * settings.WASTE_CONCRETE
        gross_volume = total_volume * settings.WASTE_CONCRETE
        
        return {
            "element_type": "beam",
            "unit": "m",
            "net_length": total_length,
            "gross_length": gross_length,
            "total_volume_m3": total_volume,
            "gross_volume_m3": gross_volume,
            "waste_factor": settings.WASTE_CONCRETE,
            "details": beam_details
        }
    
    def calculate_slab_quantities(self, slabs: List[Dict]) -> Dict[str, Any]:
        """
        Calculate slab quantities
        Unit: sqm (square meters)
        """
        total_area = 0.0
        slab_details = []
        total_volume = 0.0
        
        # Use floor area from project metadata if available
        if self.project.floor_area:
            total_area = self.project.floor_area * self.project.number_of_floors
        else:
            # Calculate from AI detection
            for slab in slabs:
                bbox = slab.get("bbox", [])
                if len(bbox) >= 4:
                    area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
                    total_area += area
        
        # Typical slab thickness
        slab_thickness = self.project.metadata.get("slab_thickness", 0.15)  # 150mm
        total_volume = total_area * slab_thickness
        
        # Apply waste factor
        gross_area = total_area * settings.WASTE_CONCRETE
        gross_volume = total_volume * settings.WASTE_CONCRETE
        
        return {
            "element_type": "slab",
            "unit": "sqm",
            "net_area": total_area,
            "gross_area": gross_area,
            "thickness": slab_thickness,
            "total_volume_m3": total_volume,
            "gross_volume_m3": gross_volume,
            "waste_factor": settings.WASTE_CONCRETE
        }
    
    def calculate_door_quantities(self, doors: List[Dict]) -> Dict[str, Any]:
        """
        Calculate door quantities
        Unit: No. (number of doors)
        """
        door_count = len(doors)
        door_details = []
        
        # Categorize doors by size
        door_types = {
            "standard_3x7": 0,
            "standard_3x8": 0,
            "double_door": 0
        }
        
        for door in doors:
            # Default to standard door
            door_type = "standard_3x7"
            door_types[door_type] += 1
            
            door_details.append({
                "location": door.get("location", "Unknown"),
                "type": door_type,
                "confidence": door.get("confidence", 0.8)
            })
        
        return {
            "element_type": "door",
            "unit": "No.",
            "total_count": door_count,
            "breakdown": door_types,
            "details": door_details
        }
    
    def calculate_window_quantities(self, windows: List[Dict]) -> Dict[str, Any]:
        """
        Calculate window quantities
        Unit: No. (number of windows)
        """
        window_count = len(windows)
        window_details = []
        
        for window in windows:
            window_details.append({
                "location": window.get("location", "Unknown"),
                "confidence": window.get("confidence", 0.8)
            })
        
        return {
            "element_type": "window",
            "unit": "No.",
            "total_count": window_count,
            "details": window_details
        }
    
    def calculate_roof_quantities(self) -> Dict[str, Any]:
        """
        Calculate roof quantities based on floor area
        Unit: sqm (square meters)
        """
        # Roof area typically slightly larger than floor area
        if self.project.floor_area:
            # Add 10% for overhang
            roof_area = self.project.floor_area * 1.1
            
            # Apply waste factor
            gross_area = roof_area * settings.WASTE_ROOFING
            
            return {
                "element_type": "roof",
                "unit": "sqm",
                "net_area": roof_area,
                "gross_area": gross_area,
                "waste_factor": settings.WASTE_ROOFING
            }
        
        return {
            "element_type": "roof",
            "unit": "sqm",
            "net_area": 0.0,
            "gross_area": 0.0
        }
    
    def process_ai_detections(self, ai_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process AI detection results and calculate all quantities
        """
        if not ai_results.get("success"):
            return {
                "success": False,
                "error": "AI processing failed"
            }
        
        detections = ai_results["elements"]["detections"]
        
        # Categorize detections by type
        walls = [d for d in detections if d["class_name"] == "wall"]
        columns = [d for d in detections if d["class_name"] == "column"]
        beams = [d for d in detections if d["class_name"] == "beam"]
        slabs = [d for d in detections if d["class_name"] in ["slab", "floor"]]
        doors = [d for d in detections if d["class_name"] == "door"]
        windows = [d for d in detections if d["class_name"] == "window"]
        
        # Calculate quantities for each element type
        quantities = {
            "walls": self.calculate_wall_quantities(walls),
            "columns": self.calculate_column_quantities(columns),
            "beams": self.calculate_beam_quantities(beams),
            "slabs": self.calculate_slab_quantities(slabs),
            "doors": self.calculate_door_quantities(doors),
            "windows": self.calculate_window_quantities(windows),
            "roof": self.calculate_roof_quantities()
        }
        
        return {
            "success": True,
            "quantities": quantities,
            "overall_confidence": ai_results.get("overall_confidence", 0.0),
            "needs_review": ai_results.get("needs_review", False)
        }


# backend/app/services/boq_generator.py
"""
Bill of Quantities (BoQ) Generator
Generates structured BoQ from quantities and material recipes
Author: Eng. STEPHEN ODHIAMBO
"""

from typing import Dict, List, Any
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.config import settings, MATERIAL_RECIPES, BOQ_CATEGORIES
from app.models.boq import BOQItem
from app.models.material import Material
from app.models.project import Project


class BOQGenerator:
    """
    Generate comprehensive Bill of Quantities
    Follows KESMM4 standards and Kenyan BOQ format
    """
    
    def __init__(self, project: Project, db: Session):
        self.project = project
        self.db = db
        self.boq_items = []
        self.item_counter = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0, "H": 0}
    
    def get_material_rate(self, material_code: str) -> float:
        """
        Get material unit rate from database
        Apply county location factor
        """
        material = self.db.query(Material).filter(
            Material.material_code == material_code
        ).first()
        
        if not material:
            return 0.0
        
        base_rate = material.unit_price
        
        # Apply county location factor
        from app.config import COUNTY_LOCATION_FACTORS
        location_factor = COUNTY_LOCATION_FACTORS.get(self.project.county, 1.0)
        
        return base_rate * location_factor
    
    def generate_item_number(self, category_code: str) -> str:
        """
        Generate sequential item number
        Format: A.1, A.2, B.1, etc.
        """
        self.item_counter[category_code] += 1
        return f"{category_code}.{self.item_counter[category_code]}"
    
    def create_preliminaries_section(self) -> List[BOQItem]:
        """
        Section A: Preliminaries
        Includes mobilization, insurances, temporary works, etc.
        """
        items = []
        
        # Calculate base cost for preliminaries calculation
        # This will be updated after all other items are costed
        
        prelim_items = [
            {
                "description": "Mobilization and demobilization",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 1.0
            },
            {
                "description": "Contractor's all-risk insurance",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 0.5
            },
            {
                "description": "Site offices and stores",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 1.0
            },
            {
                "description": "Water for construction",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 0.5
            },
            {
                "description": "Temporary works",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 1.0
            },
            {
                "description": "Safety and security",
                "unit": "Sum",
                "quantity": 1.0,
                "percentage": 1.0
            }
        ]
        
        for item_data in prelim_items:
            item = BOQItem(
                project_id=self.project.id,
                item_number=self.generate_item_number("A"),
                category="Preliminaries",
                description=item_data["description"],
                unit=item_data["unit"],
                net_quantity=item_data["quantity"],
                waste_factor=1.0,
                gross_quantity=item_data["quantity"],
                unit_rate=0.0,  # Will be calculated as percentage of project cost
                total_cost=0.0,
                ai_extracted=False,
                needs_review=False,
                remarks="To be calculated as percentage of project subtotal"
            )
            items.append(item)
        
        return items
    
    def create_substructure_section(self, quantities: Dict) -> List[BOQItem]:
        """
        Section B: Substructure
        Includes excavation, foundation concrete, hardcore, DPM, etc.
        """
        items = []
        
        # Calculate foundation area (typically 10-15% of floor area)
        floor_area = self.project.floor_area or 0
        foundation_area = floor_area * 0.12
        
        # Calculate excavation volume
        excavation_depth = 1.5  # Average 1.5m depth
        excavation_volume = foundation_area * excavation_depth
        
        substructure_items = [
            {
                "description": "Site clearance and topsoil stripping",
                "unit": "sqm",
                "quantity": floor_area * 1.2,
                "waste": 1.05
            },
            {
                "description": f"Excavation in {self.project.soil_type or 'ordinary'} soil for foundations",
                "unit": "m3",
                "quantity": excavation_volume,
                "waste": 1.10
            },
            {
                "description": "Hardcore filling and compaction",
                "unit": "m3",
                "quantity": foundation_area * 0.15,
                "waste": 1.10
            },
            {
                "description": "Blinding concrete (1:3:6) 50mm thick",
                "unit": "sqm",
                "quantity": foundation_area,
                "waste": settings.WASTE_CONCRETE
            },
            {
                "description": "Foundation concrete (C25/30)",
                "unit": "m3",
                "quantity": foundation_area * 0.25,
                "waste": settings.WASTE_CONCRETE
            },
            {
                "description": "Damp proof membrane (1000 gauge polythene)",
                "unit": "sqm",
                "quantity": floor_area,
                "waste": 1.10
            },
            {
                "description": "Anti-termite treatment",
                "unit": "sqm",
                "quantity": floor_area,
                "waste": 1.05
            },
            {
                "description": "Ground floor slab concrete (C25/30) 150mm thick",
                "unit": "sqm",
                "quantity": floor_area,
                "waste": settings.WASTE_CONCRETE
            }
        ]
        
        for item_data in substructure_items:
            net_qty = item_data["quantity"]
            waste = item_data.get("waste", 1.0)
            gross_qty = net_qty * waste
            
            item = BOQItem(
                project_id=self.project.id,
                item_number=self.generate_item_number("B"),
                category="Substructure",
                description=item_data["description"],
                unit=item_data["unit"],
                net_quantity=net_qty,
                waste_factor=waste,
                gross_quantity=gross_qty,
                unit_rate=0.0,  # Will be populated by costing engine
                total_cost=0.0,
                ai_extracted=False,
                confidence_score=0.85
            )
            items.append(item)
        
        return items
    
    def create_superstructure_section(self, quantities: Dict) -> List[BOQItem]:
        """
        Section C: Superstructure
        Includes walls, columns, beams, slabs using AI-extracted quantities
        """
        items = []
        
        # Walls
        if "walls" in quantities:
            wall_data = quantities["walls"]
            items.extend(self._create_wall_items(wall_data))
        
        # Columns
        if "columns" in quantities:
            column_data = quantities["columns"]
            items.extend(self._create_column_items(column_data))
        
        # Beams
        if "beams" in quantities:
            beam_data = quantities["beams"]
            items.extend(self._create_beam_items(beam_data))
        
        # Slabs
        if "slabs" in quantities:
            slab_data = quantities["slabs"]
            items.extend(self._create_slab_items(slab_data))
        
        # Doors
        if "doors" in quantities:
            door_data = quantities["doors"]
            items.extend(self._create_door_items(door_data))
        
        # Windows
        if "windows" in quantities:
            window_data = quantities["windows"]
            items.extend(self._create_window_items(window_data))
        
        return items
    
    def _create_wall_items(self, wall_data: Dict) -> List[BOQItem]:
        """Create BoQ items for walls with material breakdown"""
        items = []
        
        # Main wall item
        wall_area = wall_data["gross_quantity"]
        
        item = BOQItem(
            project_id=self.project.id,
            item_number=self.generate_item_number("C"),
            category="Superstructure",
            sub_category="Walls",
            description="225mm thick hollow concrete blockwork in mortar (1:4)",
            unit="sqm",
            net_quantity=wall_data["net_quantity"],
            waste_factor=wall_data["waste_factor"],
            gross_quantity=wall_area,
            ai_extracted=True,
            confidence_score=0.90,
            remarks="AI-extracted from drawings"
        )
        
        # Calculate materials breakdown using recipe
        recipe = MATERIAL_RECIPES["wall_per_sqm"]
        materials_breakdown = {}
        
        for material, qty_per_unit in recipe.items():
            materials_breakdown[material] = {
                "quantity_per_sqm": qty_per_unit,
                "total_quantity": qty_per_unit * wall_area,
                "unit": self._get_material_unit(material)
            }
        
        item.materials_breakdown = materials_breakdown
        items.append(item)
        
        # Add constituent materials as sub-items
        for material, data in materials_breakdown.items():
            sub_item = BOQItem(
                project_id=self.project.id,
                item_number=f"{item.item_number}.{len(items)}",
                category="Superstructure",
                sub_category="Wall Materials",
                description=self._format_material_description(material),
                unit=data["unit"],
                net_quantity=data["total_quantity"],
                waste_factor=1.0,
                gross_quantity=data["total_quantity"],
                ai_extracted=True
            )
            items.append(sub_item)
        
        return items
    
    def _get_material_unit(self, material_code: str) -> str:
        """Get standard unit for material"""
        unit_map = {
            "cement": "bags",
            "sand": "lorry",
            "ballast": "lorry",
            "bricks": "No.",
            "bars": "pcs",
            "nails": "kg",
            "timber": "ft",
            "paint": "liter"
        }
        
        for key, unit in unit_map.items():
            if key in material_code.lower():
                return unit
        
        return "unit"
    
    def _format_material_description(self, material_code: str) -> str:
        """Format material code to readable description"""
        return material_code.replace("_", " ").title()
    
    def _create_column_items(self, column_data: Dict) -> List[BOQItem]:
        """Create BoQ items for columns"""
        # Similar pattern to walls - to be fully implemented
        items = []
        # Implementation details...
        return items
    
    def _create_beam_items(self, beam_data: Dict) -> List[BOQItem]:
        """Create BoQ items for beams"""
        items = []
        # Implementation details...
        return items
    
    def _create_slab_items(self, slab_data: Dict) -> List[BOQItem]:
        """Create BoQ items for slabs"""
        items = []
        # Implementation details...
        return items
    
    def _create_door_items(self, door_data: Dict) -> List[BOQItem]:
        """Create BoQ items for doors"""
        items = []
        # Implementation details...
        return items
    
    def _create_window_items(self, window_data: Dict) -> List[BOQItem]:
        """Create BoQ items for windows"""
        items = []
        # Implementation details...
        return items
    
    def generate_boq(self, quantities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main BoQ generation function
        Generates complete structured BoQ
        """
        all_items = []
        
        # A. Preliminaries
        all_items.extend(self.create_preliminaries_section())
        
        # B. Substructure
        all_items.extend(self.create_substructure_section(quantities))
        
        # C. Superstructure
        all_items.extend(self.create_superstructure_section(quantities))
        
        # Save all items to database
        for item in all_items:
            self.db.add(item)
        
        self.db.commit()
        
        return {
            "success": True,
            "total_items": len(all_items),
            "categories": list(set(item.category for item in all_items)),
            "message": "BoQ generated successfully"
        }
