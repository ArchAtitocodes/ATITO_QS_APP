# backend/app/services/costing_scraping_engine.py
"""
Web Scraping Service for Material Rates
Scrapes from IQSK, NCA, KIPPRA, Integrum, and hardware stores
Author: Eng. STEPHEN ODHIAMBO
"""

from typing import Dict, List, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import requests
import re
import time
import statistics
from datetime import datetime

from app.config import settings
from app.models.material import Material
from sqlalchemy.orm import Session


class ScraperService:
    """
    Web scraping service for material rates
    Implements rate normalization and averaging
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.scraped_data = []
        
        # Setup Selenium with headless Chrome
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={settings.SCRAPING_USER_AGENT}")
        
        self.driver = None  # Initialize when needed
    
    def init_driver(self):
        """Initialize Selenium WebDriver"""
        if not self.driver:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            self.driver = webdriver.Chrome(options=chrome_options)
    
    def close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def extract_price_from_text(self, text: str) -> Optional[float]:
        """
        Extract price from text string
        Handles formats: KES 1,200, KSh 1200, 1,200.00, etc.
        """
        # Remove currency symbols and common text
        text = re.sub(r'(KES|KSh|Ksh|KES\.)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[^\d,.]', '', text)
        
        # Remove commas
        text = text.replace(',', '')
        
        # Extract number
        match = re.search(r'\d+\.?\d*', text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None
    
    def extract_unit_from_text(self, text: str) -> str:
        """
        Extract unit from text
        Common units: bag, m3, sqm, kg, liter, piece, etc.
        """
        text = text.lower()
        
        unit_patterns = {
            'bag': r'\b(bag|bags)\b',
            'tonne': r'\b(tonne|tonnes|ton|tons|mt)\b',
            'kg': r'\b(kg|kgs|kilogram)\b',
            'm3': r'\b(m3|cubic meter|cu\.m)\b',
            'sqm': r'\b(sqm|m2|square meter|sq\.m)\b',
            'liter': r'\b(liter|litre|litres|l)\b',
            'piece': r'\b(piece|pieces|pcs|pc|no\.)\b',
            'meter': r'\b(meter|metre|m)\b',
            'lorry': r'\b(lorry|truck)\b'
        }
        
        for unit, pattern in unit_patterns.items():
            if re.search(pattern, text):
                return unit
        
        return 'unit'
    
    def scrape_iqsk(self) -> List[Dict[str, Any]]:
        """
        Scrape material rates from IQSK (Institute of Quantity Surveyors of Kenya)
        Note: This is a placeholder - actual implementation depends on site structure
        """
        results = []
        
        try:
            # IQSK typically publishes quarterly rates
            url = f"{settings.IQSK_BASE_URL}/rates"
            
            response = requests.get(url, headers={
                'User-Agent': settings.SCRAPING_USER_AGENT
            }, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find rate tables (structure varies)
                # This is a generic example - adjust based on actual HTML
                tables = soup.find_all('table', class_='rates-table')
                
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows[1:]:  # Skip header
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            material_desc = cells[0].get_text(strip=True)
                            unit = cells[1].get_text(strip=True)
                            price_text = cells[2].get_text(strip=True)
                            
                            price = self.extract_price_from_text(price_text)
                            
                            if price:
                                results.append({
                                    'source': 'IQSK',
                                    'description': material_desc,
                                    'unit': self.extract_unit_from_text(unit),
                                    'price': price,
                                    'currency': 'KES',
                                    'date_scraped': datetime.utcnow()
                                })
            
            time.sleep(settings.SCRAPING_RATE_LIMIT)
            
        except Exception as e:
            print(f"Error scraping IQSK: {str(e)}")
        
        return results
    
    def scrape_nca(self) -> List[Dict[str, Any]]:
        """
        Scrape from National Construction Authority
        """
        results = []
        
        try:
            url = f"{settings.NCA_BASE_URL}/construction-rates"
            
            # Use Selenium for dynamic content
            self.init_driver()
            self.driver.get(url)
            
            # Wait for content to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rates-container"))
            )
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract rates (adjust selectors based on actual site)
            rate_items = soup.find_all('div', class_='rate-item')
            
            for item in rate_items:
                try:
                    material = item.find('h3').get_text(strip=True)
                    price_elem = item.find('span', class_='price')
                    unit_elem = item.find('span', class_='unit')
                    
                    if price_elem and unit_elem:
                        price = self.extract_price_from_text(price_elem.get_text())
                        unit = self.extract_unit_from_text(unit_elem.get_text())
                        
                        if price:
                            results.append({
                                'source': 'NCA',
                                'description': material,
                                'unit': unit,
                                'price': price,
                                'currency': 'KES',
                                'date_scraped': datetime.utcnow()
                            })
                except Exception as e:
                    continue
            
            time.sleep(settings.SCRAPING_RATE_LIMIT)
            
        except Exception as e:
            print(f"Error scraping NCA: {str(e)}")
        
        return results
    
    def scrape_hardware_stores(self) -> List[Dict[str, Any]]:
        """
        Scrape from major hardware stores
        - Bamburi Cement
        - Simba Cement
        - Hardware stores
        """
        results = []
        
        # Bamburi Cement
        try:
            url = "https://www.bamburicement.com/products"
            response = requests.get(url, headers={
                'User-Agent': settings.SCRAPING_USER_AGENT
            }, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                products = soup.find_all('div', class_='product-item')
                for product in products:
                    try:
                        name = product.find('h3').get_text(strip=True)
                        price_elem = product.find('span', class_='price')
                        
                        if price_elem:
                            price = self.extract_price_from_text(price_elem.get_text())
                            if price:
                                results.append({
                                    'source': 'Bamburi Cement',
                                    'description': name,
                                    'unit': 'bag',
                                    'price': price,
                                    'currency': 'KES',
                                    'date_scraped': datetime.utcnow()
                                })
                    except Exception:
                        continue
            
            time.sleep(settings.SCRAPING_RATE_LIMIT)
            
        except Exception as e:
            print(f"Error scraping Bamburi: {str(e)}")
        
        return results
    
    def normalize_material_name(self, description: str) -> str:
        """
        Normalize material names for matching
        E.g., "Portland Cement 50kg" -> "cement"
        """
        desc_lower = description.lower()
        
        # Common material keywords
        if 'cement' in desc_lower:
            return 'cement'
        elif 'sand' in desc_lower:
            if 'river' in desc_lower:
                return 'river_sand'
            return 'sand'
        elif 'ballast' in desc_lower:
            return 'ballast'
        elif 'brick' in desc_lower:
            return 'bricks'
        elif 'steel' in desc_lower or 'reinforcement' in desc_lower:
            return 'reinforcement_steel'
        elif 'timber' in desc_lower or 'wood' in desc_lower:
            return 'timber'
        elif 'paint' in desc_lower:
            return 'paint'
        elif 'tile' in desc_lower:
            return 'tiles'
        elif 'sheet' in desc_lower and 'iron' in desc_lower:
            return 'iron_sheets'
        
        return 'other'
    
    def aggregate_rates(self, scraped_data: List[Dict]) -> Dict[str, Any]:
        """
        Aggregate rates from multiple sources
        Calculate median, mean, and weighted average
        """
        # Group by material type
        grouped = {}
        
        for item in scraped_data:
            material_key = self.normalize_material_name(item['description'])
            
            if material_key not in grouped:
                grouped[material_key] = {
                    'prices': [],
                    'sources': [],
                    'units': []
                }
            
            grouped[material_key]['prices'].append(item['price'])
            grouped[material_key]['sources'].append(item['source'])
            grouped[material_key]['units'].append(item['unit'])
        
        # Calculate statistics for each material
        aggregated = {}
        
        for material, data in grouped.items():
            prices = data['prices']
            
            if prices:
                aggregated[material] = {
                    'mean_price': statistics.mean(prices),
                    'median_price': statistics.median(prices),
                    'min_price': min(prices),
                    'max_price': max(prices),
                    'std_dev': statistics.stdev(prices) if len(prices) > 1 else 0,
                    'sample_size': len(prices),
                    'sources': list(set(data['sources'])),
                    'common_unit': max(set(data['units']), key=data['units'].count),
                    'confidence': self._calculate_confidence(prices)
                }
        
        return aggregated
    
    def _calculate_confidence(self, prices: List[float]) -> float:
        """
        Calculate confidence score based on price variance
        Lower variance = higher confidence
        """
        if len(prices) < 2:
            return 0.5
        
        mean = statistics.mean(prices)
        std_dev = statistics.stdev(prices)
        
        # Coefficient of variation
        cv = (std_dev / mean) * 100 if mean > 0 else 100
        
        # Confidence score (inverse of CV)
        # CV < 10% = High confidence (0.9)
        # CV > 30% = Low confidence (0.5)
        if cv < 10:
            return 0.95
        elif cv < 20:
            return 0.85
        elif cv < 30:
            return 0.70
        else:
            return 0.50
    
    def update_materials_database(self, aggregated_rates: Dict[str, Any]):
        """
        Update materials database with scraped rates
        """
        for material_key, rate_data in aggregated_rates.items():
            # Find or create material
            material = self.db.query(Material).filter(
                Material.material_code == material_key
            ).first()
            
            if material:
                # Update existing material
                material.unit_price = rate_data['median_price']
                material.price_sources = rate_data['sources']
                material.last_scraped = datetime.utcnow()
                material.price_confidence = rate_data['confidence']
            else:
                # Create new material
                material = Material(
                    material_code=material_key,
                    description=material_key.replace('_', ' ').title(),
                    category='Construction Materials',
                    unit=rate_data['common_unit'],
                    unit_price=rate_data['median_price'],
                    price_sources=rate_data['sources'],
                    last_scraped=datetime.utcnow(),
                    price_confidence=rate_data['confidence']
                )
                self.db.add(material)
        
        self.db.commit()
    
    def run_full_scrape(self) -> Dict[str, Any]:
        """
        Run complete scraping process from all sources
        """
        all_data = []
        
        print("Starting web scraping...")
        
        # Scrape from all sources
        print("Scraping IQSK...")
        all_data.extend(self.scrape_iqsk())
        
        print("Scraping NCA...")
        all_data.extend(self.scrape_nca())
        
        print("Scraping hardware stores...")
        all_data.extend(self.scrape_hardware_stores())
        
        self.close_driver()
        
        print(f"Total items scraped: {len(all_data)}")
        
        # Aggregate rates
        print("Aggregating rates...")
        aggregated = self.aggregate_rates(all_data)
        
        # Update database
        print("Updating database...")
        self.update_materials_database(aggregated)
        
        return {
            'success': True,
            'items_scraped': len(all_data),
            'materials_updated': len(aggregated),
            'timestamp': datetime.utcnow()
        }


# backend/app/services/costing_engine.py
"""
Costing Engine
Applies material rates, location factors, and calculates final project cost
Author: Eng. STEPHEN ODHIAMBO
"""

from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.config import settings, COUNTY_LOCATION_FACTORS
from app.models.boq import BOQItem
from app.models.bbs import BBSItem
from app.models.material import Material
from app.models.project import Project


class CostingEngine:
    """
    Project costing engine
    Applies rates, location factors, and calculates total costs
    """
    
    def __init__(self, project: Project, db: Session):
        self.project = project
        self.db = db
        self.cost_breakdown = {}
    
    def get_material_rate(
        self,
        material_code: str,
        apply_location_factor: bool = True
    ) -> float:
        """
        Get material unit rate with location factor
        """
        material = self.db.query(Material).filter(
            Material.material_code == material_code
        ).first()
        
        if not material:
            return 0.0
        
        base_rate = material.unit_price
        
        if apply_location_factor and self.project.county:
            location_factor = COUNTY_LOCATION_FACTORS.get(
                self.project.county,
                1.0
            )
            return base_rate * location_factor
        
        return base_rate
    
    def cost_boq_items(self) -> Dict[str, Any]:
        """
        Apply costing to all BoQ items
        """
        boq_items = self.db.query(BOQItem).filter(
            BOQItem.project_id == self.project.id
        ).all()
        
        total_cost = 0.0
        category_totals = {}
        
        for item in boq_items:
            # Get rate for material
            # For items with material breakdown, cost each material
            if item.materials_breakdown:
                item_cost = 0.0
                for material_code, data in item.materials_breakdown.items():
                    rate = self.get_material_rate(material_code)
                    quantity = data['total_quantity']
                    item_cost += rate * quantity
                
                item.total_cost = item_cost
            else:
                # Simple costing
                item.total_cost = item.unit_rate * item.gross_quantity
            
            total_cost += item.total_cost
            
            # Track by category
            if item.category not in category_totals:
                category_totals[item.category] = 0.0
            category_totals[item.category] += item.total_cost
        
        self.db.commit()
        
        return {
            'subtotal': total_cost,
            'category_totals': category_totals
        }
    
    def cost_bbs_items(self) -> Dict[str, Any]:
        """
        Cost Bar Bending Schedule items
        Steel rates per kg
        """
        bbs_items = self.db.query(BBSItem).filter(
            BBSItem.project_id == self.project.id
        ).all()
        
        # Get steel rates
        high_tensile_rate = self.get_material_rate('reinforcement_steel_high_tensile')
        mild_steel_rate = self.get_material_rate('reinforcement_steel_mild')
        
        total_steel_cost = 0.0
        high_tensile_cost = 0.0
        mild_steel_cost = 0.0
        
        for item in bbs_items:
            if item.bar_type == 'T':  # High tensile
                cost = item.total_weight * high_tensile_rate
                high_tensile_cost += cost
            else:  # Mild steel (R, Y)
                cost = item.total_weight * mild_steel_rate
                mild_steel_cost += cost
            
            total_steel_cost += cost
        
        return {
            'total_steel_cost': total_steel_cost,
            'high_tensile_cost': high_tensile_cost,
            'mild_steel_cost': mild_steel_cost
        }
    
    def calculate_final_cost(self) -> Dict[str, Any]:
        """
        Calculate final project cost with all markups
        
        Final Cost Structure:
        1. Subtotal (BoQ + BBS)
        2. + Preliminary Cost (5% of subtotal)
        3. + Provisional Sum (10% of subtotal)
        4. + Labor & Overheads (50% of subtotal)
        5. = Total Project Cost (Excl. VAT & Contingency)
        6. + Contingency (5-15%, default 10%)
        7. + VAT (16%)
        8. = Grand Total
        """
        # Cost BoQ items
        boq_costs = self.cost_boq_items()
        boq_subtotal = boq_costs['subtotal']
        
        # Cost BBS items
        bbs_costs = self.cost_bbs_items()
        steel_cost = bbs_costs['total_steel_cost']
        
        # Materials subtotal
        materials_subtotal = boq_subtotal + steel_cost
        
        # Apply markups
        preliminary_cost = materials_subtotal * settings.PRELIMINARY_COST_PERCENTAGE
        provisional_sum = materials_subtotal * settings.PROVISIONAL_SUM_PERCENTAGE
        labor_overheads = materials_subtotal * settings.LABOR_OVERHEADS_PERCENTAGE
        
        # Total before contingency and VAT
        subtotal_before_contingency = (
            materials_subtotal +
            preliminary_cost +
            provisional_sum +
            labor_overheads
        )
        
        # Contingency
        contingency_percentage = self.project.contingency_percentage or settings.DEFAULT_CONTINGENCY_PERCENTAGE
        contingency_amount = subtotal_before_contingency * contingency_percentage
        
        # Subtotal before VAT
        subtotal_before_vat = subtotal_before_contingency + contingency_amount
        
        # VAT
        vat_amount = subtotal_before_vat * settings.VAT_PERCENTAGE
        
        # Grand Total
        grand_total = subtotal_before_vat + vat_amount
        
        # Update project estimated cost
        self.project.estimated_cost = grand_total
        self.db.commit()
        
        cost_breakdown = {
            'materials_subtotal': materials_subtotal,
            'boq_cost': boq_subtotal,
            'steel_cost': steel_cost,
            'preliminary_cost': preliminary_cost,
            'provisional_sum': provisional_sum,
            'labor_overheads': labor_overheads,
            'subtotal_before_contingency': subtotal_before_contingency,
            'contingency_percentage': contingency_percentage * 100,
            'contingency_amount': contingency_amount,
            'subtotal_before_vat': subtotal_before_vat,
            'vat_percentage': settings.VAT_PERCENTAGE * 100,
            'vat_amount': vat_amount,
            'grand_total': grand_total,
            'category_breakdown': boq_costs['category_totals']
        }
        
        return cost_breakdown
    
    def generate_cost_summary(self) -> Dict[str, Any]:
        """
        Generate comprehensive cost summary
        """
        final_costs = self.calculate_final_cost()
        
        return {
            'project_name': self.project.name,
            'location': f"{self.project.location}, {self.project.county}",
            'location_factor': COUNTY_LOCATION_FACTORS.get(
                self.project.county,
                1.0
            ),
            'costs': final_costs,
            'currency': 'KES',
            'date_generated': datetime.utcnow()
        }
