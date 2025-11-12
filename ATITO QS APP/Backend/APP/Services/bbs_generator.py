# backend/app/services/bbs_generator.py
"""
Bar Bending Schedule (BBS) Generator
BS 8666:2005 Compliant
Generates detailed reinforcement schedules with bend allowances
Author: Eng. STEPHEN ODHIAMBO
"""

from typing import Dict, List, Any, Tuple
from sqlalchemy.orm import Session
import math

from app.config import settings, BS8666_SHAPE_CODES, BS8666_BEND_ALLOWANCES
from app.models.bbs import BBSItem
from app.models.project import Project


class BBSGenerator:
    """
    Generate Bar Bending Schedule compliant with BS 8666:2005
    """
    
    # Steel density: 7850 kg/m³
    STEEL_DENSITY = 7850
    
    # Bar weights per meter (kg/m) based on diameter
    BAR_WEIGHTS = {
        6: 0.222,   # R6
        8: 0.395,   # R8/T8
        10: 0.616,  # T10
        12: 0.888,  # T12
        16: 1.579,  # T16
        20: 2.466,  # T20
        25: 3.854,  # T25
        32: 6.313,  # T32
        40: 9.864   # T40
    }
    
    def __init__(self, project: Project, db: Session):
        self.project = project
        self.db = db
        self.bar_mark_counter = 1
        self.bbs_items = []
    
    def get_bar_weight_per_meter(self, diameter: int) -> float:
        """Get weight per meter for bar diameter"""
        return self.BAR_WEIGHTS.get(diameter, 0.0)
    
    def get_bend_allowance(self, diameter: int) -> float:
        """Get bend allowance for bar diameter per BS 8666"""
        return BS8666_BEND_ALLOWANCES.get(diameter, 0)
    
    def generate_bar_mark(self) -> str:
        """Generate sequential bar mark"""
        mark = f"B{self.bar_mark_counter:03d}"
        self.bar_mark_counter += 1
        return mark
    
    def calculate_straight_bar_length(
        self,
        total_length: float,
        cover: float = 50
    ) -> float:
        """
        Calculate straight bar length
        Shape Code: 00
        
        Args:
            total_length: Total length in mm
            cover: Concrete cover in mm
        """
        # Subtract cover from both ends
        return total_length - (2 * cover)
    
    def calculate_l_bar_length(
        self,
        length_a: float,
        length_b: float,
        diameter: int,
        cover: float = 50
    ) -> Tuple[float, Dict]:
        """
        Calculate L-bar length
        Shape Code: 11
        
        Args:
            length_a: First leg length in mm
            length_b: Second leg length in mm
            diameter: Bar diameter in mm
            cover: Concrete cover in mm
        """
        bend_allowance = self.get_bend_allowance(diameter)
        
        # Adjust for cover
        adj_length_a = length_a - cover
        adj_length_b = length_b - cover
        
        # Total length including bend allowance
        total_length = adj_length_a + adj_length_b - bend_allowance
        
        dimensions = {
            "A": adj_length_a,
            "B": adj_length_b,
            "bend_allowance": bend_allowance
        }
        
        return total_length, dimensions
    
    def calculate_u_bar_length(
        self,
        length_a: float,
        length_b: float,
        length_c: float,
        diameter: int,
        cover: float = 50
    ) -> Tuple[float, Dict]:
        """
        Calculate U-bar (stirrup) length
        Shape Code: 13
        
        Args:
            length_a: First vertical leg
            length_b: Horizontal leg
            length_c: Second vertical leg
            diameter: Bar diameter
            cover: Concrete cover
        """
        bend_allowance = self.get_bend_allowance(diameter)
        
        # Adjust for cover
        adj_length_a = length_a - cover
        adj_length_b = length_b - (2 * cover)
        adj_length_c = length_c - cover
        
        # Total length with 2 bends
        total_length = adj_length_a + adj_length_b + adj_length_c - (2 * bend_allowance)
        
        dimensions = {
            "A": adj_length_a,
            "B": adj_length_b,
            "C": adj_length_c,
            "bend_allowance": bend_allowance
        }
        
        return total_length, dimensions
    
    def calculate_stirrup_length(
        self,
        width: float,
        depth: float,
        diameter: int,
        cover: float = 50
    ) -> Tuple[float, Dict]:
        """
        Calculate closed stirrup/link length
        Shape Code: 20 or 21
        
        Args:
            width: Beam/column width in mm
            depth: Beam/column depth in mm
            diameter: Bar diameter
            cover: Concrete cover
        """
        bend_allowance = self.get_bend_allowance(diameter)
        
        # Adjust for cover on all sides
        adj_width = width - (2 * cover)
        adj_depth = depth - (2 * cover)
        
        # Perimeter with 4 corners (4 bends)
        perimeter = 2 * (adj_width + adj_depth)
        
        # Subtract bend allowances for 4 corners
        total_length = perimeter - (4 * bend_allowance)
        
        # Add hook length (typically 10 x diameter)
        hook_length = 10 * diameter
        total_length += hook_length
        
        dimensions = {
            "width": adj_width,
            "depth": adj_depth,
            "perimeter": perimeter,
            "bend_allowance": bend_allowance,
            "hook_length": hook_length
        }
        
        return total_length, dimensions
    
    def round_weight_to_nearest_50kg(self, weight: float) -> float:
        """Round total weight to nearest 50kg as per requirements"""
        return round(weight / 50) * 50
    
    def generate_column_reinforcement(
        self,
        column_data: Dict,
        column_count: int
    ) -> List[BBSItem]:
        """
        Generate BBS for columns
        Typical: 4T16 main bars + R8 links @ 200mm c/c
        """
        items = []
        
        # Column dimensions
        column_size = self.project.metadata.get("typical_column_size", 300)  # 300x300mm
        column_height = self.project.metadata.get("floor_height", 3000)  # 3000mm
        
        # Main bars (longitudinal)
        main_bar_dia = 16  # T16
        main_bar_count_per_column = 4
        total_main_bars = main_bar_count_per_column * column_count
        
        # Calculate straight length
        main_bar_length = self.calculate_straight_bar_length(column_height, cover=50)
        
        # Add starter bars (lap length = 40 x diameter)
        lap_length = 40 * main_bar_dia
        main_bar_length += lap_length
        
        total_main_bar_weight = (
            (main_bar_length / 1000) *  # Convert to meters
            self.get_bar_weight_per_meter(main_bar_dia) *
            total_main_bars
        )
        
        # Round to nearest 50kg
        rounded_weight = self.round_weight_to_nearest_50kg(total_main_bar_weight)
        
        main_bar_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Column",
            member_location="All columns",
            bar_diameter=main_bar_dia,
            bar_type="T",
            shape_code="00",  # Straight with starter
            length_a=main_bar_length,
            total_length=main_bar_length,
            number_of_bars=total_main_bars,
            unit_weight=self.get_bar_weight_per_meter(main_bar_dia),
            total_weight=rounded_weight,
            remarks=f"Main reinforcement, {main_bar_count_per_column} bars per column"
        )
        items.append(main_bar_item)
        
        # Links/Stirrups
        link_dia = 8  # R8
        link_spacing = 200  # 200mm c/c
        
        # Number of links per column
        links_per_column = math.ceil(column_height / link_spacing)
        total_links = links_per_column * column_count
        
        # Calculate stirrup length
        link_length, _ = self.calculate_stirrup_length(
            width=column_size,
            depth=column_size,
            diameter=link_dia,
            cover=50
        )
        
        total_link_weight = (
            (link_length / 1000) *
            self.get_bar_weight_per_meter(link_dia) *
            total_links
        )
        
        rounded_link_weight = self.round_weight_to_nearest_50kg(total_link_weight)
        
        link_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Column",
            member_location="All columns",
            bar_diameter=link_dia,
            bar_type="R",
            shape_code="21",  # Closed stirrup
            length_a=column_size,
            length_b=column_size,
            total_length=link_length,
            number_of_bars=total_links,
            unit_weight=self.get_bar_weight_per_meter(link_dia),
            total_weight=rounded_link_weight,
            remarks=f"Links @ {link_spacing}mm c/c"
        )
        items.append(link_item)
        
        return items
    
    def generate_beam_reinforcement(
        self,
        beam_data: Dict,
        total_beam_length: float
    ) -> List[BBSItem]:
        """
        Generate BBS for beams
        Typical: 3T16 bottom + 2T16 top + R8 stirrups @ 200mm c/c
        """
        items = []
        
        # Beam dimensions
        beam_width = self.project.metadata.get("typical_beam_width", 300)
        beam_depth = self.project.metadata.get("typical_beam_depth", 450)
        
        # Bottom bars (main tension reinforcement)
        bottom_bar_dia = 16  # T16
        bottom_bar_count = 3
        
        # Average beam length (from quantity takeoff)
        avg_beam_length = 4000  # 4m typical
        number_of_beams = math.ceil(total_beam_length / avg_beam_length)
        
        total_bottom_bars = bottom_bar_count * number_of_beams
        
        bottom_bar_length = self.calculate_straight_bar_length(avg_beam_length, cover=50)
        
        total_bottom_weight = (
            (bottom_bar_length / 1000) *
            self.get_bar_weight_per_meter(bottom_bar_dia) *
            total_bottom_bars
        )
        
        rounded_bottom_weight = self.round_weight_to_nearest_50kg(total_bottom_weight)
        
        bottom_bar_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Beam",
            member_location="All beams",
            bar_diameter=bottom_bar_dia,
            bar_type="T",
            shape_code="00",
            length_a=bottom_bar_length,
            total_length=bottom_bar_length,
            number_of_bars=total_bottom_bars,
            unit_weight=self.get_bar_weight_per_meter(bottom_bar_dia),
            total_weight=rounded_bottom_weight,
            remarks="Bottom bars (tension reinforcement)"
        )
        items.append(bottom_bar_item)
        
        # Top bars (compression reinforcement)
        top_bar_dia = 16
        top_bar_count = 2
        total_top_bars = top_bar_count * number_of_beams
        
        top_bar_length = self.calculate_straight_bar_length(avg_beam_length, cover=50)
        
        total_top_weight = (
            (top_bar_length / 1000) *
            self.get_bar_weight_per_meter(top_bar_dia) *
            total_top_bars
        )
        
        rounded_top_weight = self.round_weight_to_nearest_50kg(total_top_weight)
        
        top_bar_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Beam",
            member_location="All beams",
            bar_diameter=top_bar_dia,
            bar_type="T",
            shape_code="00",
            length_a=top_bar_length,
            total_length=top_bar_length,
            number_of_bars=total_top_bars,
            unit_weight=self.get_bar_weight_per_meter(top_bar_dia),
            total_weight=rounded_top_weight,
            remarks="Top bars (compression reinforcement)"
        )
        items.append(top_bar_item)
        
        # Stirrups
        stirrup_dia = 8  # R8
        stirrup_spacing = 200  # 200mm c/c
        
        stirrups_per_beam = math.ceil(avg_beam_length / stirrup_spacing)
        total_stirrups = stirrups_per_beam * number_of_beams
        
        stirrup_length, _ = self.calculate_stirrup_length(
            width=beam_width,
            depth=beam_depth,
            diameter=stirrup_dia,
            cover=50
        )
        
        total_stirrup_weight = (
            (stirrup_length / 1000) *
            self.get_bar_weight_per_meter(stirrup_dia) *
            total_stirrups
        )
        
        rounded_stirrup_weight = self.round_weight_to_nearest_50kg(total_stirrup_weight)
        
        stirrup_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Beam",
            member_location="All beams",
            bar_diameter=stirrup_dia,
            bar_type="R",
            shape_code="21",
            length_a=beam_width,
            length_b=beam_depth,
            total_length=stirrup_length,
            number_of_bars=total_stirrups,
            unit_weight=self.get_bar_weight_per_meter(stirrup_dia),
            total_weight=rounded_stirrup_weight,
            remarks=f"Stirrups @ {stirrup_spacing}mm c/c"
        )
        items.append(stirrup_item)
        
        return items
    
    def generate_slab_reinforcement(
        self,
        slab_data: Dict,
        total_slab_area: float
    ) -> List[BBSItem]:
        """
        Generate BBS for slabs
        Typical: T12 @ 200mm c/c both ways (top and bottom)
        """
        items = []
        
        slab_thickness = self.project.metadata.get("slab_thickness", 150)
        
        # Main bars (bottom) - both directions
        main_bar_dia = 12  # T12
        bar_spacing = 200  # 200mm c/c
        
        # Calculate number of bars needed
        # Assume square slab for simplicity
        slab_side = math.sqrt(total_slab_area)
        
        # Bars in one direction
        bars_direction_1 = math.ceil(slab_side * 1000 / bar_spacing)
        bar_length_direction_1 = slab_side * 1000
        
        # Bars in perpendicular direction
        bars_direction_2 = math.ceil(slab_side * 1000 / bar_spacing)
        bar_length_direction_2 = slab_side * 1000
        
        total_bars_bottom = bars_direction_1 + bars_direction_2
        
        avg_bar_length = (bar_length_direction_1 + bar_length_direction_2) / 2
        
        total_bottom_weight = (
            (avg_bar_length / 1000) *
            self.get_bar_weight_per_meter(main_bar_dia) *
            total_bars_bottom
        )
        
        rounded_bottom_weight = self.round_weight_to_nearest_50kg(total_bottom_weight)
        
        bottom_mesh_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Slab",
            member_location="All slabs",
            bar_diameter=main_bar_dia,
            bar_type="T",
            shape_code="00",
            length_a=avg_bar_length,
            total_length=avg_bar_length,
            number_of_bars=total_bars_bottom,
            unit_weight=self.get_bar_weight_per_meter(main_bar_dia),
            total_weight=rounded_bottom_weight,
            remarks=f"Bottom mesh @ {bar_spacing}mm c/c both ways"
        )
        items.append(bottom_mesh_item)
        
        # Top bars (distribution) - typically smaller
        top_bar_dia = 10  # T10
        total_bars_top = total_bars_bottom  # Same layout
        
        total_top_weight = (
            (avg_bar_length / 1000) *
            self.get_bar_weight_per_meter(top_bar_dia) *
            total_bars_top
        )
        
        rounded_top_weight = self.round_weight_to_nearest_50kg(total_top_weight)
        
        top_mesh_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Slab",
            member_location="All slabs",
            bar_diameter=top_bar_dia,
            bar_type="T",
            shape_code="00",
            length_a=avg_bar_length,
            total_length=avg_bar_length,
            number_of_bars=total_bars_top,
            unit_weight=self.get_bar_weight_per_meter(top_bar_dia),
            total_weight=rounded_top_weight,
            remarks=f"Top mesh (distribution) @ {bar_spacing}mm c/c both ways"
        )
        items.append(top_mesh_item)
        
        return items
    
    def generate_foundation_reinforcement(
        self,
        floor_area: float
    ) -> List[BBSItem]:
        """
        Generate BBS for foundation
        Typical: T16 bars for foundation base
        """
        items = []
        
        # Foundation area (typically 10-12% of floor area)
        foundation_area = floor_area * 0.12
        
        foundation_bar_dia = 16  # T16
        bar_spacing = 200  # 200mm c/c
        
        # Calculate bars both ways
        foundation_side = math.sqrt(foundation_area)
        bars_per_direction = math.ceil(foundation_side * 1000 / bar_spacing)
        bar_length = foundation_side * 1000
        
        total_bars = bars_per_direction * 2  # Both directions
        
        total_weight = (
            (bar_length / 1000) *
            self.get_bar_weight_per_meter(foundation_bar_dia) *
            total_bars
        )
        
        rounded_weight = self.round_weight_to_nearest_50kg(total_weight)
        
        foundation_item = BBSItem(
            project_id=self.project.id,
            bar_mark=self.generate_bar_mark(),
            member_type="Foundation",
            member_location="Strip/pad foundations",
            bar_diameter=foundation_bar_dia,
            bar_type="T",
            shape_code="00",
            length_a=bar_length,
            total_length=bar_length,
            number_of_bars=total_bars,
            unit_weight=self.get_bar_weight_per_meter(foundation_bar_dia),
            total_weight=rounded_weight,
            remarks=f"Foundation reinforcement @ {bar_spacing}mm c/c both ways"
        )
        items.append(foundation_item)
        
        return items
    
    def generate_bbs(self, quantities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main BBS generation function
        Generates complete Bar Bending Schedule
        """
        all_items = []
        
        # Extract quantities from takeoff
        columns = quantities.get("columns", {})
        beams = quantities.get("beams", {})
        slabs = quantities.get("slabs", {})
        
        # Generate reinforcement for each element type
        
        # 1. Foundation reinforcement
        if self.project.floor_area:
            all_items.extend(
                self.generate_foundation_reinforcement(self.project.floor_area)
            )
        
        # 2. Column reinforcement
        if columns.get("count", 0) > 0:
            all_items.extend(
                self.generate_column_reinforcement(columns, columns["count"])
            )
        
        # 3. Beam reinforcement
        if beams.get("net_length", 0) > 0:
            all_items.extend(
                self.generate_beam_reinforcement(beams, beams["net_length"])
            )
        
        # 4. Slab reinforcement
        if slabs.get("net_area", 0) > 0:
            all_items.extend(
                self.generate_slab_reinforcement(slabs, slabs["net_area"])
            )
        
        # Save all items to database
        for item in all_items:
            self.db.add(item)
        
        self.db.commit()
        
        # Calculate total steel weight
        total_steel_weight = sum(item.total_weight for item in all_items)
        
        return {
            "success": True,
            "total_items": len(all_items),
            "total_steel_weight_kg": total_steel_weight,
            "steel_types": {
                "high_tensile": sum(
                    item.total_weight for item in all_items 
                    if item.bar_type == "T"
                ),
                "mild_steel": sum(
                    item.total_weight for item in all_items 
                    if item.bar_type == "R"
                )
            },
            "message": "BBS generated successfully (BS 8666:2005 compliant)"
        }
